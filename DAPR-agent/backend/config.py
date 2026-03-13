"""
DAPR Agent 系统配置
"""
import os
from pathlib import Path

# 基础路径
BASE_DIR = Path(__file__).parent.parent
PROJECT_ROOT = BASE_DIR.parent  # flux2 项目根目录
SESSIONS_DIR = BASE_DIR / "sessions"
OUTPUTS_DIR = BASE_DIR / "outputs"
STATIC_DIR = BASE_DIR / "static"

# 确保目录存在
SESSIONS_DIR.mkdir(exist_ok=True)
OUTPUTS_DIR.mkdir(exist_ok=True)

# 服务器配置
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8000

# LLM 配置 - Kimi-K2.5 API (Moonshot AI)
# 通过 OpenAI 兼容接口调用
LLM_CONFIG = {
    "api_key": os.environ.get("MOONSHOT_API_KEY", ""),  # 从环境变量读取 API Key
    "base_url": "https://api.moonshot.cn/v1",           # Moonshot API 基础 URL
    "model": "kimi-k2.5",                                # 模型名称
    "temperature": 1,
    "max_tokens": 4096,      # Kimi API 支持的最大 tokens
    "max_context": 32000,    # 上下文窗口大小
}

# ComfyUI 配置
COMFYUI_CONFIG = {
    "server_address": "127.0.0.1:8188",
    "workflow_path": str(PROJECT_ROOT / "color_the_dapr_doodle_api.json"),
    "timeout": 300,
}

# 绘画界面配置
CANVAS_CONFIG = {
    "width": 850,  # 8.5 inches * 100 DPI
    "height": 1100,  # 11 inches * 100 DPI
    "dpi": 100,
    "stroke_color": "#000000",
    "stroke_width": 3,
    "eraser_width": 20,
}

# 视频录制配置
VIDEO_CONFIG = {
    "fps": 30,
    "codec": "vp8",  # WebM 格式
    "webcam_resolution": (640, 480),
}

# DAPR 引导词
GUIDANCE_TEXT = """请你找一个舒服的姿势坐下，让自己放松。轻轻闭上眼睛，把注意力集中在呼吸上，深呼吸。每一次呼吸都让你更加放松，现在想象一幅雨中人的画面。将你的注意力集中在这个画面上，直到它越来越清晰。那是怎样的画面，是什么样的氛围，人物在做什么，情绪是怎样的？注意这个形象，好，现在睁开眼睛，把你想象中的形象在纸上画出来。"""

# 年龄段选项
AGE_GROUPS = [
    "儿童 (6-12岁)",
    "青少年 (13-17岁)",
    "青年 (18-35岁)",
    "中年 (36-55岁)",
    "老年 (56岁以上)"
]

# 性别选项
GENDER_OPTIONS = ["男", "女", "其他", "不愿透露"]
