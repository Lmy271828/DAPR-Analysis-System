import asyncio

from fastapi import APIRouter, HTTPException

from config import SESSIONS_DIR
from models import Session
from schemas import ChatAnswerRequest
from agent.interview_agent import InterviewAgent
from dependencies import manager, orchestrator, interview_agents

router = APIRouter(prefix="/api/session")


@router.post("/{session_id}/chat-answer")
async def submit_chat_answer(session_id: str, request: ChatAnswerRequest):
    """
    自主访谈阶段：用户逐条回答 Agent 的问题。
    
    回答后，InterviewAgent 继续评估 → 追问 或 进入生图。
    """
    session = Session.load(session_id, SESSIONS_DIR)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    agent = interview_agents.get(session_id)
    if not agent:
        # 尝试从持久化状态恢复
        if session.interview_state:
            agent = InterviewAgent.from_dict(session_id, session.interview_state)
            agent.set_manager(manager)
            agent.set_orchestrator(orchestrator)
            interview_agents[session_id] = agent
            # 如果状态是 waiting，需要重新启动 run 循环
            if agent.state == "waiting":
                asyncio.create_task(agent.run(), name=f"interview-{session_id[:8]}")
        else:
            raise HTTPException(status_code=400, detail="访谈未开始")
    
    agent.receive_answer(request.answer)
    return {"status": "received", "turn": agent.turn_count}


@router.post("/{session_id}/skip-interview")
async def skip_interview(session_id: str):
    """跳过自主访谈，直接进入生图阶段"""
    session = Session.load(session_id, SESSIONS_DIR)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    agent = interview_agents.get(session_id)
    if not agent:
        # 尝试从持久化状态恢复
        if session.interview_state:
            agent = InterviewAgent.from_dict(session_id, session.interview_state)
            agent.set_manager(manager)
            agent.set_orchestrator(orchestrator)
            interview_agents[session_id] = agent
            # 如果状态是 waiting，需要重新启动 run 循环
            if agent.state == "waiting":
                asyncio.create_task(agent.run(), name=f"interview-{session_id[:8]}")
        else:
            raise HTTPException(status_code=400, detail="访谈未开始")
    
    agent.skip()
    return {"status": "skipped"}
