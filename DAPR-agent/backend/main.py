"""
DAPR Agent 主服务
FastAPI + WebSocket
"""
import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    STATIC_DIR,
    SERVER_HOST, SERVER_PORT,
    LOCAL_VLM_CONFIG,
)
from models import TherapistLog
from image_service import close_image_service
from database import setup_database
from agent import ToolWrapper, NotifyUserTool
from agent.interview_agent import InterviewAgent
from dependencies import manager, orchestrator, interview_agents, log_to_therapist


# FastAPI 应用
app = FastAPI(title="DAPR Agent", version="1.0.0")

# 静态文件服务
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
async def startup_event():
    setup_database()
    await manager.start()
    
    # 注册 Agent Tools
    from routers.drawing import analyze_drawing_task_stream
    from routers.image import generate_images_task, final_analysis_task, generate_final_report_task
    
    orchestrator.set_manager(manager)
    orchestrator.register_tool(ToolWrapper("AnalyzeDrawingTool", analyze_drawing_task_stream, max_retries=2))
    orchestrator.register_tool(ToolWrapper("GenerateImageTool", generate_images_task, max_retries=2))
    orchestrator.register_tool(ToolWrapper("AskFollowUpTool", final_analysis_task, max_retries=2))
    orchestrator.register_tool(ToolWrapper("GenerateReportTool", generate_final_report_task, max_retries=2))
    orchestrator.register_tool(NotifyUserTool(manager))
    print("[Agent] Orchestrator 初始化完成，已注册 5 个 Tools")
    
    # 设置 InterviewAgent 的 WebSocket manager
    InterviewAgent._manager = manager  # 类级别注入
    
    # 预加载本地 VLM 模型（如果启用）
    if LOCAL_VLM_CONFIG.get("use_local_vlm", True):
        from services.llm.core import init_local_vlm
        try:
            init_local_vlm()
            print("[Startup] 本地 VLM 模型预加载完成")
        except Exception as e:
            print(f"[Startup] 本地 VLM 预加载失败: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    await manager.stop()
    await close_image_service()


@app.get("/")
async def root():
    """重定向到引导页"""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/therapist")
async def therapist_dashboard():
    """咨询师监控界面"""
    return FileResponse(STATIC_DIR / "therapist.html")


# 注册路由
from routers.session import router as session_router
from routers.drawing import router as drawing_router
from routers.interview import router as interview_router
from routers.image import router as image_router, file_router as image_file_router
from routers.history import router as history_router
from routers.websocket import router as websocket_router

app.include_router(session_router)
app.include_router(drawing_router)
app.include_router(interview_router)
app.include_router(image_router)
app.include_router(image_file_router)
app.include_router(history_router)
app.include_router(websocket_router)


# ==================== 主程序入口 ====================

if __name__ == "__main__":
    ssl_config = {}
    if os.environ.get("ENABLE_HTTPS", "").lower() in ("true", "1", "yes"):
        cert_file = os.environ.get("SSL_CERT_FILE", "backend/cert/cert.pem")
        key_file = os.environ.get("SSL_KEY_FILE", "backend/cert/key.pem")
        if os.path.exists(cert_file) and os.path.exists(key_file):
            ssl_config = {"ssl_keyfile": key_file, "ssl_certfile": cert_file}
            print(f"[Server] HTTPS 已启用: cert={cert_file}, key={key_file}")
        else:
            print(f"[Server] 警告: ENABLE_HTTPS=true 但证书文件不存在，回退到 HTTP")
            print(f"         生成自签名证书: openssl req -x509 -newkey rsa:4096 -keyout {key_file} -out {cert_file} -days 365 -nodes")
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, **ssl_config)
