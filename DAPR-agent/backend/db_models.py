"""
SQLAlchemy ORM 模型定义
用于替换本地 JSON 文件存储
"""
import os
import json
from datetime import datetime
from typing import Optional, Any

from sqlalchemy import (
    create_engine, Column, String, DateTime, Boolean, JSON, Text
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session as DBSession

from cryptography.fernet import Fernet

Base = declarative_base()


class SessionModel(Base):
    """会话数据表 —— 替代本地 JSON 文件"""
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    status = Column(String(32), default="guidance", nullable=False)

    age_group = Column(String(32), nullable=True)
    gender = Column(String(16), nullable=True)
    consent_given = Column(Boolean, default=False, nullable=False)

    drawing_image = Column(String(512), nullable=True)
    webcam_video = Column(String(512), nullable=True)
    canvas_video = Column(String(512), nullable=True)

    initial_analysis = Column(JSON, nullable=True)
    questions_asked = Column(JSON, default=list)
    user_answers = Column(Text, nullable=True)       # JSON 字符串，加密存储
    hypotheses = Column(JSON, default=list)
    generated_images = Column(JSON, default=list)
    selected_image_id = Column(String(64), nullable=True)
    selection_behavior = Column(JSON, nullable=True)

    final_questions = Column(JSON, default=list)
    final_answers = Column(Text, nullable=True)      # JSON 字符串，加密存储
    final_analysis = Column(JSON, nullable=True)
    
    # 自主访谈 Agent 状态
    interview_state = Column(JSON, nullable=True)    # InterviewAgent 序列化状态
    conversation_history = Column(JSON, default=list)  # 访谈对话历史


class TherapistLogModel(Base):
    """咨询师日志表 —— 可选，用于持久化日志"""
    __tablename__ = "therapist_logs"

    id = Column(String(36), primary_key=True, default=lambda: os.urandom(16).hex())
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    session_id = Column(String(36), nullable=False, index=True)
    stage = Column(String(64), nullable=False)
    llm_input = Column(JSON, nullable=True)
    llm_output = Column(JSON, nullable=True)
    flux2_input = Column(JSON, nullable=True)
    flux2_output = Column(JSON, nullable=True)
    extra_data = Column(JSON, nullable=True)


# ─────────────────────────────────────────────
# 数据库引擎与会话工厂
# ─────────────────────────────────────────────

_engine = None
_SessionLocal = None


def get_engine(db_path: str = None):
    """获取或创建数据库引擎"""
    global _engine
    if _engine is None:
        if db_path is None:
            db_path = os.environ.get("DAPR_DB_PATH", "./data/dapr.db")
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
            echo=False,
        )
    return _engine


def get_session_local(db_path: str = None):
    """获取会话工厂"""
    global _SessionLocal
    if _SessionLocal is None:
        engine = get_engine(db_path)
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _SessionLocal


def init_db(db_path: str = None):
    """初始化数据库（创建表），并自动迁移新增字段"""
    engine = get_engine(db_path)
    Base.metadata.create_all(bind=engine)
    
    # ── 自动迁移：为已有表添加新字段 ──
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    if 'sessions' in inspector.get_table_names():
        columns = [c['name'] for c in inspector.get_columns('sessions')]
        with engine.connect() as conn:
            if 'interview_state' not in columns:
                conn.execute(text("ALTER TABLE sessions ADD COLUMN interview_state JSON"))
                conn.commit()
                print("[DB] 迁移: 添加 interview_state 字段")
            if 'conversation_history' not in columns:
                conn.execute(text("ALTER TABLE sessions ADD COLUMN conversation_history JSON DEFAULT '[]'"))
                conn.commit()
                print("[DB] 迁移: 添加 conversation_history 字段")
            # 重命名 screen_video → canvas_video（字段语义澄清）
            if 'screen_video' in columns and 'canvas_video' not in columns:
                conn.execute(text("ALTER TABLE sessions RENAME COLUMN screen_video TO canvas_video"))
                conn.commit()
                print("[DB] 迁移: screen_video 重命名为 canvas_video")
    
    print(f"[DB] 数据库初始化完成: {db_path or 'data/dapr.db'}")


def get_db(db_path: str = None) -> DBSession:
    """获取数据库会话（用于 FastAPI Depends）"""
    session = get_session_local(db_path)()
    try:
        yield session
    finally:
        session.close()


# ─────────────────────────────────────────────
# 加密辅助（复用 models.py 的逻辑）
# ─────────────────────────────────────────────

def _get_fernet() -> Optional[Fernet]:
    key = os.environ.get("DAPR_ENCRYPTION_KEY")
    if not key:
        return None
    try:
        return Fernet(key.encode())
    except Exception:
        return None


def _encrypt_field(value: Any) -> Optional[str]:
    """加密敏感字段为 JSON 字符串"""
    if value is None:
        return None
    fernet = _get_fernet()
    raw = json.dumps(value, ensure_ascii=False)
    if fernet:
        return f"enc:{fernet.encrypt(raw.encode()).decode()}"
    return raw


def _decrypt_field(value: Optional[str]) -> Any:
    """解密敏感字段"""
    if value is None:
        return None
    if isinstance(value, str) and value.startswith("enc:"):
        fernet = _get_fernet()
        if fernet:
            decrypted = fernet.decrypt(value[4:].encode()).decode()
            return json.loads(decrypted)
        print("[DB] 警告: 检测到加密字段但 DAPR_ENCRYPTION_KEY 未设置")
        return None
    # 兼容未加密的明文 JSON
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value
