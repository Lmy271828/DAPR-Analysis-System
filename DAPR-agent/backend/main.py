"""
DAPR Agent 主服务
FastAPI + WebSocket
"""
import os
import sys
import json
import asyncio
import base64
import time
from datetime import datetime
from typing import List, Optional, Dict
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
import uvicorn

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    BASE_DIR, SESSIONS_DIR, OUTPUTS_DIR, STATIC_DIR,
    SERVER_HOST, SERVER_PORT, GUIDANCE_TEXT,
    AGE_GROUPS, GENDER_OPTIONS
)
from models import Session, SessionStatus, TherapistLog
from llm_service import get_llm_service
from image_service import get_image_service



# FastAPI 应用
app = FastAPI(title="DAPR Agent", version="1.0.0")

# 静态文件服务
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# WebSocket 连接管理
class ConnectionManager:
    """连接管理器"""
    
    def __init__(self):
        # 受试者连接
        self.subject_connections: dict[str, WebSocket] = {}
        # 咨询师连接
        self.therapist_connections: dict[str, WebSocket] = {}
    
    async def connect_subject(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        self.subject_connections[session_id] = websocket
    
    async def connect_therapist(self, client_id: str, websocket: WebSocket):
        await websocket.accept()
        self.therapist_connections[client_id] = websocket
    
    def disconnect_subject(self, session_id: str):
        if session_id in self.subject_connections:
            del self.subject_connections[session_id]
    
    def disconnect_therapist(self, client_id: str):
        if client_id in self.therapist_connections:
            del self.therapist_connections[client_id]
    
    async def send_to_subject(self, session_id: str, message: dict):
        if session_id in self.subject_connections:
            await self.subject_connections[session_id].send_json(message)
    
    async def send_to_therapist(self, message: dict):
        """发送给所有咨询师"""
        disconnected = []
        for client_id, ws in self.therapist_connections.items():
            try:
                await ws.send_json(message)
            except:
                disconnected.append(client_id)
        
        # 清理断开的连接
        for client_id in disconnected:
            self.disconnect_therapist(client_id)
    
    async def broadcast_log(self, log: TherapistLog):
        """广播日志给所有咨询师"""
        await self.send_to_therapist({
            "type": "log",
            "data": {
                "timestamp": log.timestamp,
                "session_id": log.session_id,
                "stage": log.stage,
                "llm_input": log.llm_input,
                "llm_output": log.llm_output,
                "flux2_input": log.flux2_input,
                "flux2_output": log.flux2_output,
            }
        })


manager = ConnectionManager()


# 请求模型
class CreateSessionRequest(BaseModel):
    pass


class DrawingRequest(BaseModel):
    drawing_data: str  # base64 图像数据
    webcam_video: Optional[str] = None  # base64 视频数据
    screen_video: Optional[str] = None


class UserInfoRequest(BaseModel):
    session_id: str
    age_group: str
    gender: str


class AnswerRequest(BaseModel):
    session_id: str
    answers: List[str]


class SelectImageRequest(BaseModel):
    session_id: str
    image_id: str
    selection_behavior: Optional[Dict] = None  # 选择行为数据


class FinalAnswerRequest(BaseModel):
    session_id: str
    answers: List[str]


# 工具函数
def log_to_therapist(log: TherapistLog):
    """异步发送日志给咨询师"""
    print(f"[Log] 广播日志: stage={log.stage}, session={log.session_id[:8]}...")
    asyncio.create_task(manager.broadcast_log(log))


# API 路由
@app.get("/")
async def root():
    """重定向到引导页"""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/therapist")
async def therapist_dashboard():
    """咨询师监控界面"""
    return FileResponse(STATIC_DIR / "therapist.html")


@app.post("/api/session/create")
async def create_session():
    """创建新会话"""
    session = Session()
    session.status = SessionStatus.GUIDANCE
    session.save(SESSIONS_DIR)
    
    return {
        "session_id": session.id,
        "status": session.status.value,
        "guidance_text": GUIDANCE_TEXT
    }


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    """获取会话信息"""
    session = Session.load(session_id, SESSIONS_DIR)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    return session.to_dict()


@app.post("/api/session/{session_id}/drawing")
async def submit_drawing(
    session_id: str,
    request: DrawingRequest
):
    """提交绘画作品和视频"""
    import subprocess
    
    session = Session.load(session_id, SESSIONS_DIR)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    # 创建会话目录
    session_dir = SESSIONS_DIR / session_id
    session_dir.mkdir(exist_ok=True)
    
    # 保存绘画
    if request.drawing_data:
        drawing_path = session_dir / "drawing.png"
        # 移除 base64 前缀
        drawing_data = request.drawing_data
        if ',' in drawing_data:
            drawing_data = drawing_data.split(',')[1]
        with open(drawing_path, 'wb') as f:
            f.write(base64.b64decode(drawing_data))
        session.drawing_image = str(drawing_path)
        print(f"[Drawing] 绘画已保存: {drawing_path}, 大小: {drawing_path.stat().st_size} bytes")
    
    # 保存摄像头视频
    if request.webcam_video:
        webcam_path = session_dir / "webcam.webm"
        webcam_video = request.webcam_video
        if ',' in webcam_video:
            webcam_video = webcam_video.split(',')[1]
        video_data = base64.b64decode(webcam_video)
        with open(webcam_path, 'wb') as f:
            f.write(video_data)
        session.webcam_video = str(webcam_path)
        
        file_size_mb = len(video_data) / 1024 / 1024
        print(f"[Drawing] 摄像头视频已保存: {webcam_path}, 大小: {file_size_mb:.2f} MB")
        
        # 使用 ffprobe 验证视频
        try:
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 
                 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(webcam_path)],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                duration_str = result.stdout.strip()
                if duration_str.upper() != 'N/A':
                    duration = float(duration_str)
                    print(f"[Drawing] 摄像头视频时长: {duration:.1f}s")
                else:
                    print(f"[Drawing] 摄像头视频已保存（时长信息不可用）")
            else:
                print(f"[Drawing] 摄像头视频已保存（ffprobe 无法解析）")
        except Exception as e:
            print(f"[Drawing] 摄像头视频验证警告: {e}")
    
    # 保存录屏
    if request.screen_video:
        screen_path = session_dir / "screen.webm"
        screen_video = request.screen_video
        if ',' in screen_video:
            screen_video = screen_video.split(',')[1]
        video_data = base64.b64decode(screen_video)
        with open(screen_path, 'wb') as f:
            f.write(video_data)
        session.screen_video = str(screen_path)
        
        file_size_mb = len(video_data) / 1024 / 1024
        print(f"[Drawing] 屏幕视频已保存: {screen_path}, 大小: {file_size_mb:.2f} MB")
        
        # 使用 ffprobe 验证视频
        try:
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 
                 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(screen_path)],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                duration_str = result.stdout.strip()
                if duration_str.upper() != 'N/A':
                    duration = float(duration_str)
                    print(f"[Drawing] 屏幕视频时长: {duration:.1f}s")
                else:
                    print(f"[Drawing] 屏幕视频已保存（时长信息不可用）")
            else:
                print(f"[Drawing] 屏幕视频已保存（ffprobe 无法解析）")
        except Exception as e:
            print(f"[Drawing] 屏幕视频验证警告: {e}")
    
    session.status = SessionStatus.ANALYZING
    session.save(SESSIONS_DIR)
    
    return {"status": "success", "next_stage": "analyzing"}


@app.post("/api/session/{session_id}/analyze")
async def start_analysis(session_id: str, background_tasks: BackgroundTasks):
    """开始分析绘画"""
    session = Session.load(session_id, SESSIONS_DIR)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    # 异步执行分析（使用流式版本）
    background_tasks.add_task(analyze_drawing_task_stream, session_id)
    
    return {"status": "analysis_started"}


async def analyze_drawing_task_stream(session_id: str):
    """后台分析任务 - 流式版本"""
    try:
        session = Session.load(session_id, SESSIONS_DIR)
        if not session:
            print(f"[Analysis Stream] 会话不存在: {session_id}")
            return
        
        print(f"[Analysis Stream] 开始流式分析: {session_id}")
        llm = get_llm_service()
        
        # 发送开始消息
        await manager.broadcast_log(TherapistLog(
            timestamp=datetime.now().isoformat(),
            session_id=session_id,
            stage="analysis_stream_start",
            llm_input={},
            llm_output={"status": "started"}
        ))
        await manager.send_to_subject(session_id, {
            "type": "analysis_stream",
            "data": {"status": "started"}
        })
        
        token_count = 0
        start_time = time.time()
        last_update = 0
        analysis_result = None
        
        for chunk, result in llm.analyze_drawing_stream(
            drawing_path=session.drawing_image,
            webcam_video=session.webcam_video,
            screen_video=session.screen_video
        ):
            if result is not None:
                # 流式生成完成，收到最终结果
                analysis_result = result
                break
            
            # 流式生成中，发送chunk
            token_count += len(chunk)
            elapsed = time.time() - start_time
            
            # 每5个字符更新一次
            if token_count - last_update >= 5:
                speed = token_count / elapsed if elapsed > 0 else 0
                
                # 发送给咨询师面板
                await manager.broadcast_log(TherapistLog(
                    timestamp=datetime.now().isoformat(),
                    session_id=session_id,
                    stage="analysis_stream_chunk",
                    llm_input={},
                    llm_output={
                        "chunk": chunk,
                        "token_count": token_count,
                        "speed": f"{speed:.2f} chars/s"
                    }
                ))
                
                # 发送给受试者界面
                await manager.send_to_subject(session_id, {
                    "type": "analysis_stream",
                    "data": {
                        "status": "chunk",
                        "chunk": chunk,
                        "speed": f"{speed:.2f} chars/s",
                        "total_chars": token_count
                    }
                })
                
                last_update = token_count
        
        # 保存结果
        if analysis_result:
            session.initial_analysis = analysis_result
            session.questions_asked = [{"question": q} for q in analysis_result.get("questions", [])]
            session.hypotheses = analysis_result.get("hypotheses", [])
            session.status = SessionStatus.QUESTIONING
            session.save(SESSIONS_DIR)
        else:
            print(f"[Analysis Stream] 警告: 未收到分析结果")
            return
        
        # 发送完成消息
        total_time = time.time() - start_time
        await manager.broadcast_log(TherapistLog(
            timestamp=datetime.now().isoformat(),
            session_id=session_id,
            stage="analysis_stream_complete",
            llm_input={},
            llm_output={
                "result": analysis_result,
                "total_tokens": token_count,
                "total_time": f"{total_time:.2f}s",
                "avg_speed": f"{token_count/total_time:.2f} chars/s"
            }
        ))
        
        # 发送给用户的问题
        await manager.send_to_subject(session_id, {
            "type": "questions",
            "data": {
                "questions": analysis_result.get("questions", []),
                "age_groups": AGE_GROUPS,
                "gender_options": GENDER_OPTIONS
            }
        })
        
        print(f"[Analysis Stream] 流式分析完成: {token_count} chars, {total_time:.2f}s")
        
    except Exception as e:
        print(f"[Analysis Stream Error] {e}")
        import traceback
        traceback.print_exc()


@app.post("/api/session/{session_id}/info")
async def submit_user_info(request: UserInfoRequest):
    """提交用户基本信息"""
    session = Session.load(request.session_id, SESSIONS_DIR)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    session.age_group = request.age_group
    session.gender = request.gender
    session.save(SESSIONS_DIR)
    
    return {"status": "success"}


@app.post("/api/session/{session_id}/answers")
async def submit_answers(request: AnswerRequest, background_tasks: BackgroundTasks):
    """提交用户回答，开始生成图像"""
    session = Session.load(request.session_id, SESSIONS_DIR)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    session.user_answers = request.answers
    session.status = SessionStatus.GENERATING
    session.save(SESSIONS_DIR)
    
    # 提取问题列表（从 questions_asked 中提取问题文本）
    questions = [q.get("question", "") for q in session.questions_asked] if session.questions_asked else []
    
    # 保存问答到LLM对话历史（用于最终报告生成）
    llm = get_llm_service()
    qa_text = "\n\n".join([f"Q: {q}\nA: {a}" for q, a in zip(questions, request.answers)])
    llm.conversation.add_message("user", f"【用户回答】\n{qa_text}")
    
    # 记录日志到咨询师面板（包含问题和回答）
    log = TherapistLog(
        timestamp=datetime.now().isoformat(),
        session_id=request.session_id,
        stage="user_answers",
        llm_input={},
        llm_output={},
        flux2_input=None,
        flux2_output=None,
        data={
            "questions": questions,
            "answers": request.answers,
            "age_group": session.age_group,
            "gender": session.gender
        }
    )
    log_to_therapist(log)
    print(f"[Answers] 记录用户回答: session={request.session_id[:8]}..., 问题数={len(questions)}, 回答数={len(request.answers)}")
    
    # 异步生成图像
    background_tasks.add_task(generate_images_task, request.session_id)
    
    return {"status": "generating_started"}


async def generate_images_task(session_id: str):
    """后台生成图像任务"""
    session = Session.load(session_id, SESSIONS_DIR)
    if not session:
        return
    
    llm = get_llm_service()
    image_service = get_image_service()
    
    # 生成编辑指令（传入绘画分析以实现自适应风格）
    variations = llm.generate_edit_instructions(
        hypotheses=session.hypotheses,
        drawing_path=session.drawing_image,
        drawing_analysis=session.initial_analysis
    )
    
    # 记录日志
    log = TherapistLog(
        timestamp=datetime.now().isoformat(),
        session_id=session_id,
        stage="generate_instructions",
        llm_input={
            "hypotheses": session.hypotheses,
            "drawing": session.drawing_image
        },
        llm_output={"variations": variations}
    )
    log_to_therapist(log)
    
    # 生成图像
    output_dir = OUTPUTS_DIR / session_id
    generated = image_service.generate_variations(
        input_image_path=session.drawing_image,
        variations=variations,
        output_dir=str(output_dir)
    )
    
    session.generated_images = generated
    session.status = SessionStatus.SELECTING
    session.save(SESSIONS_DIR)
    
    # 发送给受试者
    await manager.send_to_subject(session_id, {
        "type": "generated_images",
        "data": {
            "images": [
                {
                    "id": img["id"],
                    "name": img["name"],
                    "description": img["description"],
                    "url": f"/api/image/{session_id}/{img['filename']}"
                }
                for img in generated
            ]
        }
    })
    
    # 记录日志
    log = TherapistLog(
        timestamp=datetime.now().isoformat(),
        session_id=session_id,
        stage="image_generation",
        llm_input={"variations": variations},
        llm_output={"status": "success", "count": len(generated)},
        flux2_input={"workflow": "color_the_dapr_doodle"},
        flux2_output={"generated_images": generated}
    )
    log_to_therapist(log)


@app.get("/api/image/{session_id}/{filename}")
async def get_image(session_id: str, filename: str):
    """获取生成的图像"""
    image_path = OUTPUTS_DIR / session_id / filename
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="图像不存在")
    
    return FileResponse(image_path)


@app.post("/api/session/{session_id}/select")
async def select_image(session_id: str, request: SelectImageRequest, background_tasks: BackgroundTasks):
    """用户选择图像"""
    # 验证路径参数和请求体中的 session_id 一致
    if session_id != request.session_id:
        raise HTTPException(status_code=400, detail="会话ID不匹配")
    
    session = Session.load(request.session_id, SESSIONS_DIR)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    session.selected_image_id = request.image_id
    session.selection_behavior = request.selection_behavior  # 保存选择行为数据
    session.status = SessionStatus.FINAL_ANALYSIS
    session.save(SESSIONS_DIR)
    
    # 记录选择行为日志
    if request.selection_behavior:
        log = TherapistLog(
            timestamp=datetime.now().isoformat(),
            session_id=session_id,
            stage="image_selection",
            llm_input={},
            llm_output={},
            data={
                "selected_image_id": request.image_id,
                "selection_behavior": request.selection_behavior
            }
        )
        log_to_therapist(log)
        print(f"[Selection] 记录选择行为: session={session_id[:8]}..., 犹豫指标数={len(request.selection_behavior.get('hesitationIndicators', []))}")
    
    # 异步进行最终分析
    background_tasks.add_task(final_analysis_task, request.session_id)
    
    return {"status": "final_analysis_started"}


async def final_analysis_task(session_id: str):
    """后台最终分析问题生成任务（第5步第1阶段）"""
    session = Session.load(session_id, SESSIONS_DIR)
    if not session:
        return
    
    print(f"[Final Analysis] 开始生成最终问题: {session_id}")
    llm = get_llm_service()
    
    # 找到选中的图像
    selected_image = None
    for img in session.generated_images:
        if str(img.get("id")) == session.selected_image_id:
            selected_image = img
            break
    
    if not selected_image:
        selected_image = session.generated_images[0] if session.generated_images else {}
    
    print(f"[Final Analysis] 用户选择图像: {selected_image.get('name', 'unknown')}")
    
    # 根据选择生成深入问题
    follow_up_questions = llm.generate_follow_up_questions(
        selected_image=selected_image,
        hypotheses=session.hypotheses,
        user_answers=session.user_answers
    )
    
    # 保存待问的问题
    session.final_questions = follow_up_questions
    session.status = SessionStatus.FINAL_QUESTIONS  # 新状态：等待回答最终问题
    session.save(SESSIONS_DIR)
    
    # 发送问题给用户
    await manager.send_to_subject(session_id, {
        "type": "final_questions",
        "data": {
            "questions": follow_up_questions,
            "selected_image": {
                "name": selected_image.get("name"),
                "description": selected_image.get("description")
            }
        }
    })
    
    print(f"[Final Analysis] 已发送最终问题: {follow_up_questions}")
    
    # 记录日志
    log = TherapistLog(
        timestamp=datetime.now().isoformat(),
        session_id=session_id,
        stage="final_questions_generated",
        llm_input={
            "selected_image": selected_image,
            "hypotheses": session.hypotheses
        },
        llm_output={"questions": follow_up_questions}
    )
    log_to_therapist(log)


async def generate_final_report_task(session_id: str):
    """生成最终报告任务（第5步第2阶段）"""
    session = Session.load(session_id, SESSIONS_DIR)
    if not session:
        return
    
    print(f"[Final Report] 开始生成最终报告: {session_id}")
    llm = get_llm_service()
    
    # 找到选中的图像
    selected_image = None
    for img in session.generated_images:
        if str(img.get("id")) == session.selected_image_id:
            selected_image = img
            break
    
    # 从 conversation manager 获取完整的对话历史（包含分析结果）
    conversation_history = llm.conversation.get_messages(include_summary=True)
    print(f"[Final Report] 对话历史: {len(conversation_history)} 条消息")
    
    # 构建用户信息
    user_info = {
        "age_group": session.age_group,
        "gender": session.gender
    }
    
    # 生成最终分析报告（传入更多上下文）
    final_result = llm.generate_final_report(
        selected_image=selected_image,
        previous_hypotheses=session.hypotheses,
        conversation_history=conversation_history,
        final_answers=session.final_answers,
        drawing_analysis=session.initial_analysis,
        selection_behavior=session.selection_behavior,
        user_info=user_info
    )
    
    session.final_analysis = final_result
    session.status = SessionStatus.COMPLETED
    session.save(SESSIONS_DIR)
    
    # 发送最终报告给用户
    await manager.send_to_subject(session_id, {
        "type": "final_report",
        "data": final_result
    })
    
    print(f"[Final Report] 最终报告已生成")
    
    # 记录日志
    log = TherapistLog(
        timestamp=datetime.now().isoformat(),
        session_id=session_id,
        stage="final_report",
        llm_input={
            "selected_image": selected_image,
            "hypotheses": session.hypotheses,
            "final_answers": session.final_answers
        },
        llm_output=final_result
    )
    log_to_therapist(log)


@app.post("/api/session/{session_id}/final-answers")
async def submit_final_answers(request: FinalAnswerRequest, background_tasks: BackgroundTasks):
    """提交最终回答，生成完整报告"""
    session = Session.load(request.session_id, SESSIONS_DIR)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    # 保存最终答案
    session.final_answers = request.answers
    session.save(SESSIONS_DIR)
    
    print(f"[Final Answers] 收到最终回答: {request.answers}")
    
    # 保存最终问答到对话历史
    llm = get_llm_service()
    final_qa_text = "\n\n".join([f"Q: {q}\nA: {a}" for q, a in zip(session.final_questions, request.answers)])
    llm.conversation.add_message("user", f"【最终问题回答】\n{final_qa_text}")
    
    # 保存选择行为到对话历史
    if session.selection_behavior:
        sel = session.selection_behavior
        behavior_text = f"【图像选择行为】\n查看顺序: {sel.get('viewOrder', [])}\n"
        behavior_text += f"最终选择: 第{sel.get('finalSelection', {}).get('viewOrder', 'N/A')}个查看的图像\n"
        behavior_text += f"犹豫指标: {len(sel.get('hesitationIndicators', []))}个"
        llm.conversation.add_message("system", behavior_text)
    
    # 异步生成最终报告
    background_tasks.add_task(generate_final_report_task, request.session_id)
    
    return {"status": "final_report_generating"}


# WebSocket 路由
@app.websocket("/ws/subject/{session_id}")
async def subject_websocket(websocket: WebSocket, session_id: str):
    """受试者 WebSocket 连接"""
    await manager.connect_subject(session_id, websocket)
    
    try:
        while True:
            data = await websocket.receive_json()
            # 处理受试者消息（如果需要）
            
    except WebSocketDisconnect:
        manager.disconnect_subject(session_id)


@app.websocket("/ws/therapist")
async def therapist_websocket(websocket: WebSocket):
    """咨询师 WebSocket 连接"""
    import uuid
    client_id = str(uuid.uuid4())
    await manager.connect_therapist(client_id, websocket)
    
    try:
        while True:
            data = await websocket.receive_json()
            # 处理咨询师消息（如查询会话列表等）
            
            if data.get("type") == "list_sessions":
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


# ==================== 历史会话导入与分析 API ====================

@app.get("/api/history/sessions")
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


class HistoryAnalyzeRequest(BaseModel):
    """历史会话分析请求"""
    session_id: str
    create_new: bool = False  # 是否创建新会话分析（复用视频和涂鸦）


@app.post("/api/history/analyze")
async def analyze_history_session(request: HistoryAnalyzeRequest, background_tasks: BackgroundTasks):
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
            
            import shutil
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
                new_session.screen_video = str(new_session_dir / "screen.webm")
            
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
                    session.screen_video = str(screen_path)
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
        
        # 启动流式分析任务
        background_tasks.add_task(analyze_drawing_task_stream, target_session_id)
        
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


@app.get("/api/history/session/{session_id}/preview")
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


# ==================== 主程序入口 ====================

if __name__ == "__main__":
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
