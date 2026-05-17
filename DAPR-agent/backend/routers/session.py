from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import SESSIONS_DIR, GUIDANCE_TEXT
from models import Session, SessionStatus

router = APIRouter(prefix="/api/session")


class ConsentRequest(BaseModel):
    age_group: str = None  # 可选：用户年龄段


@router.post("/create")
async def create_session():
    """创建新会话"""
    session = Session()
    session.status = SessionStatus.GUIDANCE
    session.save(SESSIONS_DIR)
    
    return {
        "session_id": session.id,
        "status": session.status.value,
        "guidance_text": GUIDANCE_TEXT,
        "consent_given": session.consent_given
    }


@router.get("/{session_id}")
async def get_session(session_id: str):
    """获取会话信息"""
    session = Session.load(session_id, SESSIONS_DIR)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    return session.to_dict()


@router.post("/{session_id}/consent")
async def submit_consent(session_id: str, request: ConsentRequest = None):
    """提交用户知情同意及可选基本信息"""
    session = Session.load(session_id, SESSIONS_DIR)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    session.consent_given = True
    if request and request.age_group:
        session.age_group = request.age_group
    session.save(SESSIONS_DIR)
    return {"status": "success"}
