"""
数据库初始化与管理
使用 SQLite + SQLAlchemy
"""
import os
from pathlib import Path

from db_models import init_db, get_engine, get_session_local


DB_PATH = os.environ.get("DAPR_DB_PATH", "./data/dapr.db")


def setup_database():
    """应用启动时调用：初始化数据库引擎和表结构"""
    # 确保数据目录存在
    db_dir = Path(DB_PATH).parent
    db_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建表
    init_db(DB_PATH)
    
    # 尝试迁移现有 JSON 数据
    migrate_json_to_db()


def migrate_json_to_db():
    """将现有的本地 JSON 会话文件迁移到数据库"""
    from pathlib import Path
    from models import Session, SESSIONS_DIR
    from db_models import get_session_local, SessionModel, _encrypt_field
    
    sessions_dir = Path(SESSIONS_DIR)
    if not sessions_dir.exists():
        return
    
    json_files = list(sessions_dir.glob("*.json"))
    if not json_files:
        return
    
    print(f"[DB] 发现 {len(json_files)} 个本地 JSON 会话，开始迁移...")
    
    db = get_session_local(DB_PATH)()
    migrated = 0
    skipped = 0
    
    try:
        for json_file in json_files:
            session_id = json_file.stem
            # 检查是否已存在于数据库
            existing = db.query(SessionModel).filter(SessionModel.id == session_id).first()
            if existing:
                skipped += 1
                continue
            
            # 从 JSON 加载
            session = Session.load(session_id, str(sessions_dir))
            if not session:
                continue
            
            # 写入数据库
            row = SessionModel(
                id=session.id,
                created_at=session.created_at if isinstance(session.created_at, str) else session.created_at.isoformat(),
                status=session.status.value,
                age_group=session.age_group,
                gender=session.gender,
                consent_given=session.consent_given,
                drawing_image=session.drawing_image,
                webcam_video=session.webcam_video,
                screen_video=session.screen_video,
                initial_analysis=session.initial_analysis,
                questions_asked=session.questions_asked or [],
                user_answers=_encrypt_field(session.user_answers),
                hypotheses=session.hypotheses or [],
                generated_images=session.generated_images or [],
                selected_image_id=session.selected_image_id,
                selection_behavior=session.selection_behavior,
                final_questions=session.final_questions or [],
                final_answers=_encrypt_field(session.final_answers),
                final_analysis=session.final_analysis,
            )
            db.add(row)
            migrated += 1
        
        db.commit()
        print(f"[DB] 迁移完成: {migrated} 个已导入, {skipped} 个已存在")
    except Exception as e:
        db.rollback()
        print(f"[DB] 迁移失败: {e}")
    finally:
        db.close()
