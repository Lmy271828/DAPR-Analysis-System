"""
数据模型定义
"""
import os
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import json
import uuid
from cryptography.fernet import Fernet


class SessionStatus(Enum):
    """会话状态"""
    GUIDANCE = "guidance"           # 引导阶段
    PERMISSION = "permission"           # 权限申请
    DRAWING = "drawing"                 # 绘画阶段
    ANALYZING = "analyzing"             # 分析阶段
    QUESTIONING = "questioning"         # 提问阶段
    GENERATING = "generating"           # 图像生成阶段
    SELECTING = "selecting"             # 选择阶段
    FINAL_QUESTIONS = "final_questions" # 最终问题阶段
    FINAL_ANALYSIS = "final"            # 最终分析
    COMPLETED = "completed"             # 完成


@dataclass
class Session:
    """用户会话"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: SessionStatus = SessionStatus.GUIDANCE
    
    # 用户基本信息
    age_group: Optional[str] = None
    gender: Optional[str] = None
    
    # 知情同意
    consent_given: bool = False  # 用户是否已确认知情同意
    
    # 文件路径
    drawing_image: Optional[str] = None        # 绘画成品
    webcam_video: Optional[str] = None         # 摄像头录像
    screen_video: Optional[str] = None         # 录屏
    
    # 分析结果
    initial_analysis: Optional[Dict] = None    # 初步分析
    questions_asked: List[Dict] = field(default_factory=list)
    user_answers: List[str] = field(default_factory=list)
    hypotheses: List[Dict] = field(default_factory=list)
    
    # 图像生成
    generated_images: List[Dict] = field(default_factory=list)
    selected_image_id: Optional[str] = None
    selection_behavior: Optional[Dict] = None  # 选择行为数据（犹豫指标等）
    
    # 最终问题阶段
    final_questions: List[str] = field(default_factory=list)
    final_answers: List[str] = field(default_factory=list)
    
    # 最终分析
    final_analysis: Optional[Dict] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['status'] = self.status.value
        return data
    
    def save(self, sessions_dir: str = None):
        """保存会话到数据库（sessions_dir 参数保留用于向后兼容）"""
        try:
            from db_models import get_session_local, _encrypt_field, SessionModel
            db = get_session_local()()
            try:
                data = self.to_dict()
                row = SessionModel(
                    id=self.id,
                    created_at=self.created_at if isinstance(self.created_at, str) else datetime.now().isoformat(),
                    status=self.status.value,
                    age_group=self.age_group,
                    gender=self.gender,
                    consent_given=self.consent_given,
                    drawing_image=self.drawing_image,
                    webcam_video=self.webcam_video,
                    screen_video=self.screen_video,
                    initial_analysis=self.initial_analysis,
                    questions_asked=self.questions_asked or [],
                    user_answers=_encrypt_field(self.user_answers),
                    hypotheses=self.hypotheses or [],
                    generated_images=self.generated_images or [],
                    selected_image_id=self.selected_image_id,
                    selection_behavior=self.selection_behavior,
                    final_questions=self.final_questions or [],
                    final_answers=_encrypt_field(self.final_answers),
                    final_analysis=self.final_analysis,
                )
                db.merge(row)
                db.commit()
            finally:
                db.close()
        except Exception as e:
            print(f"[Session] 数据库保存失败，回退到本地 JSON: {e}")
            self._save_fallback(sessions_dir)
    
    def _save_fallback(self, sessions_dir: str = None):
        """数据库失败时的本地 JSON 回退"""
        if sessions_dir is None:
            from config import SESSIONS_DIR
            sessions_dir = str(SESSIONS_DIR)
        filepath = f"{sessions_dir}/{self.id}.json"
        data = self.to_dict()
        fernet = _get_fernet()
        if fernet:
            for field_name in _ENCRYPTED_FIELDS:
                if field_name in data and data[field_name] is not None:
                    raw = json.dumps(data[field_name], ensure_ascii=False)
                    encrypted = fernet.encrypt(raw.encode()).decode()
                    data[field_name] = f"enc:{encrypted}"
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def load(cls, session_id: str, sessions_dir: str = None) -> Optional['Session']:
        """从数据库加载会话（sessions_dir 参数保留用于向后兼容）"""
        try:
            from db_models import get_session_local, _decrypt_field, SessionModel
            db = get_session_local()()
            try:
                row = db.query(SessionModel).filter(SessionModel.id == session_id).first()
                if not row:
                    return cls._load_fallback(session_id, sessions_dir)
                
                return cls(
                    id=row.id,
                    created_at=row.created_at.isoformat() if hasattr(row.created_at, 'isoformat') else str(row.created_at),
                    status=SessionStatus(row.status),
                    age_group=row.age_group,
                    gender=row.gender,
                    consent_given=row.consent_given,
                    drawing_image=row.drawing_image,
                    webcam_video=row.webcam_video,
                    screen_video=row.screen_video,
                    initial_analysis=row.initial_analysis,
                    questions_asked=row.questions_asked or [],
                    user_answers=_decrypt_field(row.user_answers) or [],
                    hypotheses=row.hypotheses or [],
                    generated_images=row.generated_images or [],
                    selected_image_id=row.selected_image_id,
                    selection_behavior=row.selection_behavior,
                    final_questions=row.final_questions or [],
                    final_answers=_decrypt_field(row.final_answers) or [],
                    final_analysis=row.final_analysis,
                )
            finally:
                db.close()
        except Exception as e:
            print(f"[Session] 数据库加载失败，回退到本地 JSON: {e}")
            return cls._load_fallback(session_id, sessions_dir)
    
    @classmethod
    def _load_fallback(cls, session_id: str, sessions_dir: str = None) -> Optional['Session']:
        """数据库失败时的本地 JSON 回退"""
        if sessions_dir is None:
            from config import SESSIONS_DIR
            sessions_dir = str(SESSIONS_DIR)
        filepath = f"{sessions_dir}/{session_id}.json"
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            fernet = _get_fernet()
            for field_name in _ENCRYPTED_FIELDS:
                if field_name in data and isinstance(data[field_name], str) and data[field_name].startswith("enc:"):
                    if fernet:
                        encrypted = data[field_name][4:]
                        decrypted = fernet.decrypt(encrypted.encode()).decode()
                        data[field_name] = json.loads(decrypted)
                    else:
                        data[field_name] = None
            return cls(
                id=data['id'],
                created_at=data['created_at'],
                status=SessionStatus(data['status']),
                age_group=data.get('age_group'),
                gender=data.get('gender'),
                consent_given=data.get('consent_given', False),
                drawing_image=data.get('drawing_image'),
                webcam_video=data.get('webcam_video'),
                screen_video=data.get('screen_video'),
                initial_analysis=data.get('initial_analysis'),
                questions_asked=data.get('questions_asked', []),
                user_answers=data.get('user_answers', []),
                hypotheses=data.get('hypotheses', []),
                generated_images=data.get('generated_images', []),
                selected_image_id=data.get('selected_image_id'),
                selection_behavior=data.get('selection_behavior'),
                final_questions=data.get('final_questions', []),
                final_answers=data.get('final_answers', []),
                final_analysis=data.get('final_analysis'),
            )
        except (FileNotFoundError, KeyError, ValueError):
            return None


@dataclass
class AnalysisResult:
    """分析结果"""
    timestamp: str
    drawing_features: Dict[str, Any]       # 绘画特征
    process_analysis: Dict[str, Any]        # 过程分析
    expression_analysis: Dict[str, Any]     # 表情分析
    summary: str                            # 总结
    questions: List[str]                    # 要问用户的问题
    hypotheses: List[Dict[str, str]]        # 心理猜想


@dataclass
class GeneratedImage:
    """生成的图像"""
    id: str
    hypothesis_id: str                      # 对应哪个猜想
    name: str                               # 版本名称
    description: str                        # 心理意义
    prompt: str                             # 使用的提示词
    filepath: str                           # 文件路径
    created_at: str


@dataclass
class TherapistLog:
    """心理咨询师日志条目"""
    timestamp: str
    session_id: str
    stage: str
    llm_input: Dict[str, Any] = field(default_factory=dict)               # LLM输入
    llm_output: Dict[str, Any] = field(default_factory=dict)              # LLM输出
    flux2_input: Optional[Dict] = None      # Flux2输入
    flux2_output: Optional[Dict] = None     # Flux2输出
    data: Optional[Dict[str, Any]] = None   # 额外数据（如问题和回答）


# 敏感字段加密
def _get_fernet() -> Optional[Fernet]:
    """获取 Fernet 实例，密钥来自环境变量 DAPR_ENCRYPTION_KEY"""
    key = os.environ.get("DAPR_ENCRYPTION_KEY")
    if not key:
        return None
    try:
        return Fernet(key.encode())
    except Exception:
        return None

# 需要加密的敏感字段列表
_ENCRYPTED_FIELDS = {"user_answers", "final_answers", "webcam_video", "screen_video"}
