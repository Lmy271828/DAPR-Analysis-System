import asyncio
import base64
import subprocess
import time
from datetime import datetime

from fastapi import APIRouter, HTTPException

from config import SESSIONS_DIR
from models import Session, SessionStatus, TherapistLog
from schemas import DrawingRequest
from image_service import get_image_service
from agent.plan import plan_after_drawing
from agent.interview_agent import InterviewAgent
from main import manager, orchestrator, interview_agents

router = APIRouter(prefix="/api/session")


@router.post("/{session_id}/drawing")
async def submit_drawing(
    session_id: str,
    request: DrawingRequest
):
    """提交绘画作品和视频"""
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
    if request.canvas_video:
        screen_path = session_dir / "screen.webm"
        canvas_video = request.canvas_video
        if ',' in canvas_video:
            canvas_video = canvas_video.split(',')[1]
        video_data = base64.b64decode(canvas_video)
        with open(screen_path, 'wb') as f:
            f.write(video_data)
        session.canvas_video = str(screen_path)
        
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


@router.post("/{session_id}/analyze")
async def start_analysis(session_id: str):
    """开始分析绘画"""
    session = Session.load(session_id, SESSIONS_DIR)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    # 异步执行分析（Agent Plan 编排）
    plan = plan_after_drawing(session_id)
    asyncio.create_task(orchestrator.submit_plan(session_id, plan))
    
    return {"status": "analysis_started"}


async def analyze_drawing_task_stream(session_id: str):
    """后台分析任务 - 流式版本
    
    架构：
    1. 本地 VLM (Qwen3.5) 分析图像+视频（敏感数据不上云）
    2. 卸载本地 VLM 释放显存
    3. 并行启动：InterviewAgent (Kimi 云端文字问答) + ComfyUI FLUX 预热
    """
    try:
        session = Session.load(session_id, SESSIONS_DIR)
        if not session:
            print(f"[Analysis Stream] 会话不存在: {session_id}")
            return
        
        print(f"[Analysis Stream] 开始本地 VLM 流式分析: {session_id}")
        
        # 明确使用本地 VLM 处理敏感的多模态数据
        from services.llm.core import LocalVLMService
        llm = LocalVLMService(session_id)
        
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
        
        # 构建用户画像（用于知识片段选择）
        user_profile = None
        if session.age_group:
            age_map = {
                "under_7": 5,
                "7_12": 10,
                "13_18": 15,
                "19_59": 30,
                "60_plus": 70,
            }
            user_profile = {"age": age_map.get(session.age_group)}

        # 使用 run_in_executor 避免本地 VLM 的同步 generator 阻塞事件循环
        gen = llm.analyze_drawing_stream(
            drawing_path=session.drawing_image,
            webcam_video=session.webcam_video,
            canvas_video=session.canvas_video,
            user_profile=user_profile
        )
        loop = asyncio.get_event_loop()
        while True:
            try:
                chunk, result = await loop.run_in_executor(None, next, gen)
            except StopIteration:
                break
            
            if result is not None:
                # 流式生成完成，收到最终结果
                analysis_result = result
                break
            
            # 流式生成中，发送chunk
            token_count += len(chunk)
            elapsed = time.time() - start_time
            
            # 每30个字符更新一次（节流，减少网络开销）
            if token_count - last_update >= 30:
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
        
        # 显式通知前端流式分析结束（即使 questions 为空也能退出分析态）
        await manager.send_to_subject(session_id, {
            "type": "analysis_stream",
            "data": {
                "status": "complete",
                "total_tokens": token_count,
                "total_time": f"{total_time:.2f}s"
            }
        })
        
        # ── 阶段转换：卸载本地 VLM，释放显存 ──
        LocalVLMService.unload()
        print(f"[Analysis Stream] 本地 VLM 已卸载，显存释放完成")
        
        # ── 同步启动第二阶段（云端问答）和第三阶段（ComfyUI 预热）──
        session.status = SessionStatus.CONVERSING
        session.save(SESSIONS_DIR)
        
        # 2a. 创建 InterviewAgent（使用云端 Kimi，纯文字问答）
        agent = InterviewAgent(session_id)
        agent.set_manager(manager)
        agent.set_orchestrator(orchestrator)
        agent.set_analysis_result(analysis_result)  # 注入本地 VLM 文字分析结果
        interview_agents[session_id] = agent
        
        # 尝试从持久化状态恢复（页面刷新场景）
        if session.interview_state:
            print(f"[InterviewAgent] 从持久化状态恢复: session={session_id[:8]}...")
            restored = InterviewAgent.from_dict(session_id, session.interview_state)
            restored.set_manager(manager)
            restored.set_orchestrator(orchestrator)
            restored.set_analysis_result(analysis_result)
            interview_agents[session_id] = restored
            agent = restored
        
        # 2b. 预加载 ComfyUI FLUX 权重（GPU 显存已释放，可立即加载）
        warmup_task = None
        if session.drawing_image:
            image_service = get_image_service()
            warmup_task = asyncio.create_task(
                image_service.warmup_with_image(session.drawing_image),
                name=f"warmup-{session_id[:8]}"
            )
        
        # 后台启动访谈循环
        interview_task = asyncio.create_task(agent.run(), name=f"interview-{session_id[:8]}")
        print(f"[Analysis Stream] 分析完成，已并行启动 InterviewAgent + ComfyUI 预热: {token_count} chars, {total_time:.2f}s")
        
    except Exception as e:
        print(f"[Analysis Stream Error] {e}")
        import traceback
        traceback.print_exc()
