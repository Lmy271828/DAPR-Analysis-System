"""
DAPR Agent 系统配置
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 加载 .env 文件（如果存在）
load_dotenv(Path(__file__).parent.parent / ".env")

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

# 本地 VLM 配置 (Qwen3.5 AWQ INT4)
# 显存优化说明见 docs/VLM_VRAM_OPTIMIZATION.md
LOCAL_VLM_CONFIG = {
    "model_path": str(PROJECT_ROOT / "model"),
    "torch_dtype": "bfloat16",
    "device_map": "cuda",
    "max_new_tokens": 512,           # 分析/问答 512 tokens 足够，降低峰值显存
    "video_max_frames": 10,          # 每个视频均匀提取 10 帧（去掉首尾）
    "video_fps": 0.5,
    "image_max_size": 448,           # 图像最长边限制（processor 默认不限制，需手动 resize）
    # === 显存节流关键参数：限制 processor 的像素预算 ===
    # 默认 max_pixels=6,291,456 对视频过大，易导致 OOM
    "video_max_pixels": 4_000_000,   # 视频总像素预算（帧数×高×宽），4M 对应 10 帧画布(346×448)+摄像头(448×448)
    "image_max_pixels": 1_000_000,   # 图像总像素预算
    "use_local_vlm": os.environ.get("USE_LOCAL_VLM", "true").lower() in ("true", "1", "yes"),
    # === Attention 实现选择 ===
    # Flash Attention 2 在长序列（>2k tokens）下显存优势显著，但本系统生成序列短
    #（图像分析 <500 tokens，视频分析 <1k tokens），SDPA 开销更小且无需额外依赖。
    # 如需启用 flash-attn-2，设为 True 并确保已安装 flash-attn 包。
    "use_flash_attn": os.environ.get("USE_FLASH_ATTN", "false").lower() in ("true", "1", "yes"),
    # === 采样参数：防止小模型循环输出 ===
    # Qwen3.5-2B 在贪婪解码(do_sample=False)下容易陷入重复，建议启用低温度采样
    "do_sample": True,               # False=贪婪解码（易循环）；True=采样（推荐）
    "temperature": 0.1,              # 低温度保持高确定性，同时打破贪婪陷阱
    "top_p": 0.9,                    # nucleus sampling 阈值
    "repetition_penalty": 1.08,      # 重复惩罚（1.0=无惩罚，1.05~1.15 对 Qwen 效果较好）
}

# ComfyUI 配置
COMFYUI_CONFIG = {
    "server_address": "127.0.0.1:8188",
    "workflow_path": str(PROJECT_ROOT / "color_the_dapr_doodle_api.json"),
    "timeout": 300,
}

# DAPR 引导词
GUIDANCE_TEXT = """请你找一个舒服的姿势坐下，让自己放松。轻轻闭上眼睛，把注意力集中在呼吸上，深呼吸。每一次呼吸都让你更加放松，现在想象一幅雨中人的画面。将你的注意力集中在这个画面上，直到它越来越清晰。那是怎样的画面，是什么样的氛围，人物在做什么，情绪是怎样的？注意这个形象，好，现在睁开眼睛，把你想象中的形象在纸上画出来。"""
