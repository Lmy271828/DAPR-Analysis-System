import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from config import SESSIONS_DIR
from models import Session
from dependencies import manager

router = APIRouter()


@router.websocket("/ws/subject/{session_id}")
async def subject_websocket(websocket: WebSocket, session_id: str):
    """受试者 WebSocket 连接"""
    await manager.connect_subject(session_id, websocket)
    
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            if msg_type == "pong":
                manager.mark_subject_pong(session_id)
            elif msg_type == "resume_context":
                context_messages = await manager._load_subject_context(session_id)
                await websocket.send_json({
                    "type": "restore_context",
                    "data": {"session_id": session_id, "messages": context_messages}
                })
            
    except WebSocketDisconnect:
        manager.disconnect_subject(session_id)
    except RuntimeError as e:
        # 服务器端主动关闭旧连接时可能出现的边界异常（如心跳超时误杀）
        print(f"[WebSocket] 受试者连接异常断开: session={session_id[:8]}..., err={e}")
        manager.disconnect_subject(session_id)
    except Exception as e:
        print(f"[WebSocket] 受试者连接未预期异常: session={session_id[:8]}..., err={e}")
        manager.disconnect_subject(session_id)


@router.websocket("/ws/therapist")
async def therapist_websocket(websocket: WebSocket):
    """咨询师 WebSocket 连接"""
    client_id = str(uuid.uuid4())
    await manager.connect_therapist(client_id, websocket)
    
    try:
        while True:
            data = await websocket.receive_json()
            # 处理咨询师消息（如查询会话列表等）
            msg_type = data.get("type")
            if msg_type == "pong":
                manager.mark_therapist_pong(client_id)
                continue
            
            if msg_type == "list_sessions":
                # 返回所有会话列表
                sessions = []
                for f in SESSIONS_DIR.glob("*.json"):
                    session = Session.load(f.stem, SESSIONS_DIR)
                    if session:
                        sessions.append({
                            "id": session.id,
                            "status": session.status.value,
                            "created_at": session.created_at
                        })
                
                await websocket.send_json({
                    "type": "sessions_list",
                    "data": sessions
                })
                
    except WebSocketDisconnect:
        manager.disconnect_therapist(client_id)
    except RuntimeError as e:
        print(f"[WebSocket] 咨询师连接异常断开: client={client_id[:8]}..., err={e}")
        manager.disconnect_therapist(client_id)
    except Exception as e:
        print(f"[WebSocket] 咨询师连接未预期异常: client={client_id[:8]}..., err={e}")
        manager.disconnect_therapist(client_id)
