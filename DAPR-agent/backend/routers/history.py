import asyncio
import shutil
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from config import SESSIONS_DIR
from models import Session, SessionStatus
from schemas import HistoryAnalyzeRequest
from agent.plan import plan_after_drawing
from main import orchestrator

router = APIRouter(prefix="/api/history")


@router.get("/sessions")
async def list_history_sessions():
    """
    列出所有历史会话（从sessions目录中扫描）
    返回包含涂鸦和视频的历史会话列表
    """
    history_sessions = []
    
    try:
        # 扫描sessions目录下的所有子目录
        for session_dir in SESSIONS_DIR.iterdir():
            if not session_dir.is_dir():
                continue
                
            session_id = session_dir.name
            
            # 检查必要的文件是否存在
            drawing_path = session_dir / "drawing.png"
            webcam_path = session_dir / "webcam.webm"
            screen_path = session_dir / "screen.webm"
            json_path = session_dir / f"{session_id}.json"
            
            has_drawing = drawing_path.exists()
            has_webcam = webcam_path.exists()
            has_screen = screen_path.exists()
            has_json = json_path.exists()
            
            # 只包含至少包含涂鸦的会话
            if not has_drawing:
                continue
            
            # 获取文件信息
            try:
                drawing_mtime = datetime.fromtimestamp(drawing_path.stat().st_mtime).isoformat()
                drawing_size = drawing_path.stat().st_size
            except:
                drawing_mtime = None
                drawing_size = 0
            
            # 尝试加载现有会话数据
            session_data = None
            if has_json:
                try:
                    session = Session.load(session_id, SESSIONS_DIR)
                    if session:
                        session_data = {
                            "status": session.status.value,
                            "created_at": session.created_at,
                            "has_analysis": session.initial_analysis is not None,
                            "questions_count": len(session.questions_asked),
                            "answers_count": len(session.user_answers)
                        }
                except:
                    pass
            
            history_sessions.append({
                "id": session_id,
                "path": str(session_dir),
                "files": {
                    "drawing": has_drawing,
                    "webcam": has_webcam,
                    "screen": has_screen,
                    "json": has_json
                },
                "drawing_info": {
                    "modified_at": drawing_mtime,
                    "size_bytes": drawing_size
                },
                "session_data": session_data,
                "created_at": session_data["created_at"] if session_data else drawing_mtime
            })
        
        # 按创建时间倒序排列
        history_sessions.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        
        return {
            "status": "success",
            "count": len(history_sessions),
            "sessions": history_sessions
        }
        
    except Exception as e:
        print(f"[History API Error] {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze")
async def analyze_history_session(request: HistoryAnalyzeRequest):
    """
    选择历史会话进行分析
    如果create_new=True，则创建新会话并复制历史文件
    如果create_new=False，则复用历史会话进行分析
    """
    try:
        # 验证历史会话存在
        history_dir = SESSIONS_DIR / request.session_id
        if not history_dir.exists():
            raise HTTPException(status_code=404, detail="历史会话不存在")
        
        drawing_path = history_dir / "drawing.png"
        webcam_path = history_dir / "webcam.webm"
        screen_path = history_dir / "screen.webm"
        
        if not drawing_path.exists():
            raise HTTPException(status_code=400, detail="历史会话缺少涂鸦文件")
        
        if request.create_new:
            # 创建新会话
            new_session = Session()
            new_session.status = SessionStatus.ANALYZING
            
            # 复制文件到新会话目录
            new_session_dir = SESSIONS_DIR / new_session.id
            new_session_dir.mkdir(exist_ok=True)
            
            shutil.copy2(drawing_path, new_session_dir / "drawing.png")
            if webcam_path.exists():
                shutil.copy2(webcam_path, new_session_dir / "webcam.webm")
            if screen_path.exists():
                shutil.copy2(screen_path, new_session_dir / "screen.webm")
            
            # 更新会话路径
            new_session.drawing_image = str(new_session_dir / "drawing.png")
            if webcam_path.exists():
                new_session.webcam_video = str(new_session_dir / "webcam.webm")
            if screen_path.exists():
                new_session.canvas_video = str(new_session_dir / "screen.webm")
            
            new_session.save(SESSIONS_DIR)
            
            target_session_id = new_session.id
            print(f"[History] 创建新会话 {target_session_id} 分析历史会话 {request.session_id}")
        else:
            # 复用历史会话
            session = Session.load(request.session_id, SESSIONS_DIR)
            if not session:
                # 创建新会话记录但使用现有文件
                session = Session(id=request.session_id)
                session.status = SessionStatus.ANALYZING
                session.drawing_image = str(drawing_path)
                if webcam_path.exists():
                    session.webcam_video = str(webcam_path)
                if screen_path.exists():
                    session.canvas_video = str(screen_path)
                session.save(SESSIONS_DIR)
            else:
                # 重置会话状态为分析中
                session.status = SessionStatus.ANALYZING
                session.initial_analysis = None
                session.questions_asked = []
                session.user_answers = []
                session.save(SESSIONS_DIR)
            
            target_session_id = request.session_id
            print(f"[History] 复用历史会话 {target_session_id} 进行分析")
        
        # 启动流式分析任务（Agent Plan 编排）
        plan = plan_after_drawing(target_session_id)
        asyncio.create_task(orchestrator.submit_plan(target_session_id, plan))
        
        return {
            "status": "analysis_started",
            "session_id": target_session_id,
            "original_session_id": request.session_id,
            "is_new_session": request.create_new
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[History Analyze Error] {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{session_id}/preview")
async def preview_history_session(session_id: str):
    """
    预览历史会话的文件（涂鸦图像）
    """
    try:
        history_dir = SESSIONS_DIR / session_id
        if not history_dir.exists():
            raise HTTPException(status_code=404, detail="历史会话不存在")
        
        drawing_path = history_dir / "drawing.png"
        if not drawing_path.exists():
            raise HTTPException(status_code=404, detail="涂鸦文件不存在")
        
        return FileResponse(drawing_path)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[History Preview Error] {e}")
        raise HTTPException(status_code=500, detail=str(e))
