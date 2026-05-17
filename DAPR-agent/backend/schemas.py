from typing import List, Optional, Dict
from pydantic import BaseModel


class CreateSessionRequest(BaseModel):
    pass


class DrawingRequest(BaseModel):
    drawing_data: str  # base64 图像数据
    webcam_video: Optional[str] = None  # base64 视频数据
    canvas_video: Optional[str] = None


class SelectImageRequest(BaseModel):
    session_id: str
    image_id: str
    selection_behavior: Optional[Dict] = None  # 选择行为数据


class FinalAnswerRequest(BaseModel):
    session_id: str
    answers: List[str]


class ChatAnswerRequest(BaseModel):
    session_id: str
    answer: str


class HistoryAnalyzeRequest(BaseModel):
    """历史会话分析请求"""
    session_id: str
    create_new: bool = False  # 是否创建新会话分析（复用视频和涂鸦）
