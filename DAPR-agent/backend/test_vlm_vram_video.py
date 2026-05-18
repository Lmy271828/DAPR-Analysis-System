#!/usr/bin/env python3
"""
视频分析阶段峰值显存对比测试：SDPA vs Flash Attention 2

方法：强制重新加载模型两次，分别使用不同 attn_implementation。
注意：每次加载前需销毁旧模型并清空 CUDA cache，否则显存不释放。
"""
import sys
import gc
import time
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import torch
from config import LOCAL_VLM_CONFIG
from services.llm.core import LocalVLMService
from services.llm.prompts.multimodal import build_video_analysis_prompt
from services.llm.schemas import VIDEO_ANALYSIS_SCHEMA

# 使用已有的会话视频
SESSION_DIR = Path(__file__).parent.parent / "sessions" / "7aa7e78e-4d82-4adc-b69c-0c2157663234"
WEBCAM_VIDEO = SESSION_DIR / "webcam.webm"
SCREEN_VIDEO = SESSION_DIR / "screen.webm"

VIDEO_MAX_FRAMES = LOCAL_VLM_CONFIG.get("video_max_frames", 10)


def reset_cuda_stats():
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    torch.cuda.reset_accumulated_memory_stats()


def get_peak_mb():
    return torch.cuda.max_memory_allocated() / 1024 / 1024


def unload_model():
    """强制销毁当前单例模型，释放显存"""
    if LocalVLMService._model is not None:
        del LocalVLMService._model
        LocalVLMService._model = None
    if LocalVLMService._processor is not None:
        del LocalVLMService._processor
        LocalVLMService._processor = None
    gc.collect()
    torch.cuda.empty_cache()
    # 重置 peak stats 以便下一轮准确测量
    torch.cuda.reset_peak_memory_stats()


def build_prompt():
    video_info_text = []
    from services.video import VideoUtils
    info = VideoUtils.get_video_info(str(WEBCAM_VIDEO))
    video_info_text.append(VideoUtils._format_video_info(info, "第一个视频（面部表情）"))
    info2 = VideoUtils.get_video_info(str(SCREEN_VIDEO))
    video_info_text.append(VideoUtils._format_video_info(info2, "第二个视频（绘画过程）"))
    video_info_section = "\n\n【视频信息】\n" + "\n".join(video_info_text)
    return build_video_analysis_prompt(
        has_webcam=True, has_screen=True,
        video_info_section=video_info_section, user_profile=None
    )


def run_video_inference(use_flash: bool) -> dict:
    """加载模型并运行 Batch B 视频分析，返回显存统计"""
    label = "Flash-Attn-2" if use_flash else "SDPA"
    print(f"\n{'='*60}")
    print(f"【{label}】视频推理测试")
    print("=" * 60)

    # 设置配置开关
    LOCAL_VLM_CONFIG["use_flash_attn"] = use_flash

    # 强制重新加载模型
    unload_model()
    LocalVLMService._init_lock = threading.Lock()

    # 创建服务实例（会触发模型加载）
    vlm = LocalVLMService()
    model_loaded_mb = get_peak_mb()
    print(f"模型加载后峰值: {model_loaded_mb:.2f} MB")

    # 构建 prompt
    prompt = build_prompt()
    schema = VIDEO_ANALYSIS_SCHEMA

    # 重置统计开始推理
    reset_cuda_stats()
    t0 = time.perf_counter()
    response = vlm.generate(
        prompt=prompt,
        videos=[str(WEBCAM_VIDEO), str(SCREEN_VIDEO)],
        video_max_frames=VIDEO_MAX_FRAMES,
        force_json=True,
        json_schema=schema,
        max_new_tokens=512,
    )
    elapsed = time.perf_counter() - t0
    inference_peak_mb = get_peak_mb()

    # 计算 token 速率
    token_count = len(vlm._processor.tokenizer.encode(response))
    tokens_per_sec = token_count / elapsed if elapsed > 0 else 0

    print(f"推理峰值显存: {inference_peak_mb:.2f} MB")
    print(f"推理额外占用: {inference_peak_mb - model_loaded_mb:.2f} MB")
    print(f"输出长度: {len(response)} chars, {token_count} tokens")
    print(f"生成时间: {elapsed:.2f}s, 速率: {tokens_per_sec:.1f} tokens/s")

    # 卸载
    unload_model()
    after_mb = torch.cuda.memory_allocated() / 1024 / 1024
    print(f"卸载后常驻: {after_mb:.2f} MB")

    return {
        "label": label,
        "model_loaded_mb": model_loaded_mb,
        "inference_peak_mb": inference_peak_mb,
        "inference_delta_mb": inference_peak_mb - model_loaded_mb,
        "after_cleanup_mb": after_mb,
        "response_len": len(response),
        "token_count": token_count,
        "elapsed_sec": elapsed,
        "tokens_per_sec": tokens_per_sec,
        "chars_per_sec": len(response) / elapsed if elapsed > 0 else 0,
    }


def main():
    print("=" * 60)
    print("视频分析阶段显存对比：SDPA vs Flash Attention 2")
    print("=" * 60)
    print(f"测试视频: {WEBCAM_VIDEO.name} + {SCREEN_VIDEO.name}")
    print(f"video_max_frames: {VIDEO_MAX_FRAMES}")
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"总显存: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB")

    # 确认视频存在
    if not WEBCAM_VIDEO.exists() or not SCREEN_VIDEO.exists():
        print("错误: 测试视频不存在")
        sys.exit(1)

    # 运行 SDPA
    result_sdpa = run_video_inference(use_flash=False)

    # 运行 Flash Attention 2
    result_flash = run_video_inference(use_flash=True)

    # 汇总
    print(f"\n{'='*60}")
    print("汇总对比")
    print("=" * 60)
    print(f"{'指标':<30} {'SDPA':>12} {'Flash-Attn-2':>14} {'差值':>10}")
    print("-" * 66)
    for key, label in [
        ("model_loaded_mb", "模型加载峰值(MB)"),
        ("inference_peak_mb", "推理总峰值(MB)"),
        ("inference_delta_mb", "推理增量(MB)"),
        ("elapsed_sec", "生成时间(s)"),
        ("token_count", "输出 tokens"),
        ("tokens_per_sec", "token 速率(tok/s)"),
        ("chars_per_sec", "字符速率(char/s)*"),
    ]:
        sdpa_v = result_sdpa[key]
        flash_v = result_flash[key]
        diff = sdpa_v - flash_v
        print(f"{label:<30} {sdpa_v:>12.2f} {flash_v:>14.2f} {diff:>+10.2f}")

    print("-" * 66)
    delta_sdpa = result_sdpa["inference_delta_mb"]
    delta_flash = result_flash["inference_delta_mb"]
    saving = (delta_sdpa - delta_flash) / delta_sdpa * 100 if delta_sdpa > 0 else 0
    print(f"\n推理增量显存节省: {saving:.1f}%")
    if saving > 10:
        print("✅ Flash Attention 2 显著降低视频推理显存")
    elif saving > 0:
        print("⚠️ Flash Attention 2 有轻微显存优势，但可能不明显")
    else:
        print("❌ Flash Attention 2 未带来显存优势（或开销更大）")

    print("\n* 字符速率 = 响应字符串长度 / 生成时间，为近似值；")
    print("  token 速率 = tokenizer.encode(response) 长度 / 生成时间，更准确。")


if __name__ == "__main__":
    main()
