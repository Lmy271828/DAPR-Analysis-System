"""
数据模型定义
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import json
import uuid


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
    
    def save(self, sessions_dir: str):
        """保存会话到文件"""
        filepath = f"{sessions_dir}/{self.id}.json"
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
    
    @classmethod
    def load(cls, session_id: str, sessions_dir: str) -> Optional['Session']:
        """从文件加载会话"""
        filepath = f"{sessions_dir}/{session_id}.json"
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            session = cls(
                id=data['id'],
                created_at=data['created_at'],
                status=SessionStatus(data['status']),
                age_group=data.get('age_group'),
                gender=data.get('gender'),
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
                final_analysis=data.get('final_analysis'),
            )
            return session
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
