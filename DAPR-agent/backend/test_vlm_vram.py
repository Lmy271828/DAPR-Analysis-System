#!/usr/bin/env python3
"""
VLM 图像分析阶段峰值显存测试
使用 test.jpeg + IMAGE_ANALYSIS_SCHEMA + build_image_analysis_prompt
"""
import sys
import gc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import torch
from config import LOCAL_VLM_CONFIG
from services.llm.core import LocalVLMService
from services.llm.prompts.multimodal import build_image_analysis_prompt
from services.llm.schemas import IMAGE_ANALYSIS_SCHEMA

TEST_IMAGE = Path(__file__).parent.parent.parent / "test.jpeg"


def reset_cuda_stats():
    """重置 CUDA 显存统计"""
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    torch.cuda.reset_accumulated_memory_stats()


def get_vram_mb():
    return torch.cuda.max_memory_allocated() / 1024 / 1024


def main():
    print("=" * 60)
    print("VLM 图像分析阶段峰值显存测试")
    print("=" * 60)
    print(f"测试图片: {TEST_IMAGE} (exists={TEST_IMAGE.exists()})")
    print(f"PyTorch: {torch.__version__}")
    print(f"CUDA: {torch.version.cuda}")
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"总显存: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB")
    print("=" * 60)

    # --- 阶段 0：基线 ---
    reset_cuda_stats()
    baseline_mb = get_vram_mb()
    print(f"\n[基线] 空载峰值显存: {baseline_mb:.2f} MB")

    # --- 阶段 1：加载模型 ---
    print("\n[1/3] 加载模型...")
    reset_cuda_stats()
    vlm = LocalVLMService()
    model_loaded_mb = get_vram_mb()
    print(f"模型加载后峰值显存: {model_loaded_mb:.2f} MB")
    print(f"模型权重占用: {model_loaded_mb - baseline_mb:.2f} MB")

    # --- 阶段 2：图像分析前向传播 ---
    print("\n[2/3] 运行图像分析 (Batch A)...")
    prompt = build_image_analysis_prompt(user_profile=None)
    schema = IMAGE_ANALYSIS_SCHEMA

    reset_cuda_stats()
    response = vlm.generate(
        prompt=prompt,
        images=[str(TEST_IMAGE)],
        force_json=True,
        json_schema=schema,
        max_new_tokens=256,
    )
    inference_peak_mb = get_vram_mb()
    print(f"推理峰值显存: {inference_peak_mb:.2f} MB")
    print(f"推理额外占用: {inference_peak_mb - model_loaded_mb:.2f} MB")
    print(f"总峰值显存: {inference_peak_mb:.2f} MB ({inference_peak_mb / 1024:.2f} GB)")

    # --- 阶段 3：显存回收后 ---
    print("\n[3/3] 显存回收...")
    del vlm
    gc.collect()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    _ = torch.randn(1, 1).cuda()  # 触发一次小分配刷新统计
    after_cleanup = torch.cuda.memory_allocated() / 1024 / 1024
    print(f"回收后常驻显存: {after_cleanup:.2f} MB")

    # --- 汇总 ---
    print(f"\n{'=' * 60}")
    print("汇总")
    print("=" * 60)
    print(f"模型权重:     {model_loaded_mb - baseline_mb:>8.2f} MB")
    print(f"推理峰值增量: {inference_peak_mb - model_loaded_mb:>8.2f} MB")
    print(f"总峰值显存:   {inference_peak_mb:>8.2f} MB  ({inference_peak_mb / 1024:.2f} GB)")
    print(f"GPU 总容量:   {torch.cuda.get_device_properties(0).total_memory / 1024**3:>8.2f} GB")
    print(f"利用率:       {inference_peak_mb * 100 / (torch.cuda.get_device_properties(0).total_memory / 1024**2):>8.1f}%")

    # 输出预览
    print(f"\n输出预览 ({len(response)} chars):")
    print(response[:500] + ("..." if len(response) > 500 else ""))


if __name__ == "__main__":
    main()
