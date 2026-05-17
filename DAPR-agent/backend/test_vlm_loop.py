#!/usr/bin/env python3
"""
VLM 循环输出检测脚本
使用 test.jpeg 运行多次图像分析，检测是否存在重复/循环生成。
"""
import sys
import json
from pathlib import Path

# 将 backend 加入路径
sys.path.insert(0, str(Path(__file__).parent))

from config import LOCAL_VLM_CONFIG
from services.llm.core import LocalVLMService
from services.llm.prompts.multimodal import build_image_analysis_prompt
from services.llm.schemas import IMAGE_ANALYSIS_SCHEMA
from services.llm import parsers

TEST_IMAGE = Path(__file__).parent.parent.parent / "test.jpeg"
NUM_RUNS = 3


def detect_repetition(text: str) -> dict:
    """简单启发式检测重复模式。"""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    
    # 检测连续重复行
    consecutive_repeats = 0
    for i in range(1, len(lines)):
        if lines[i] == lines[i - 1]:
            consecutive_repeats += 1
    
    # 检测整体重复率（去重后 / 总行数）
    unique_lines = set(lines)
    repeat_ratio = 1 - len(unique_lines) / max(len(lines), 1)
    
    # 检测子串重复（如 "..., " 重复多次）
    substr_repeat = False
    for length in [20, 30, 50]:
        if len(text) > length * 3:
            for i in range(len(text) - length * 3):
                chunk = text[i:i + length]
                if text.count(chunk) >= 3:
                    substr_repeat = True
                    break
        if substr_repeat:
            break
    
    return {
        "total_chars": len(text),
        "total_lines": len(lines),
        "unique_lines": len(unique_lines),
        "repeat_ratio": round(repeat_ratio, 3),
        "consecutive_repeats": consecutive_repeats,
        "substr_repeat": substr_repeat,
        "has_loop": consecutive_repeats > 2 or repeat_ratio > 0.5 or substr_repeat,
    }


def main():
    print("=" * 60)
    print("VLM 循环输出检测")
    print("=" * 60)
    print(f"测试图片: {TEST_IMAGE} (exists={TEST_IMAGE.exists()})")
    print(f"采样参数: do_sample={LOCAL_VLM_CONFIG.get('do_sample')}, "
          f"temperature={LOCAL_VLM_CONFIG.get('temperature')}, "
          f"top_p={LOCAL_VLM_CONFIG.get('top_p')}, "
          f"repetition_penalty={LOCAL_VLM_CONFIG.get('repetition_penalty')}")
    print(f"max_new_tokens: {LOCAL_VLM_CONFIG.get('max_new_tokens')}")
    print(f"运行次数: {NUM_RUNS}")
    print("=" * 60)

    if not TEST_IMAGE.exists():
        print(f"错误: 测试图片不存在: {TEST_IMAGE}")
        sys.exit(1)

    print("\n[1/2] 加载模型中...")
    vlm = LocalVLMService()
    print("[2/2] 模型加载完成\n")

    prompt = build_image_analysis_prompt(user_profile=None)
    schema = IMAGE_ANALYSIS_SCHEMA

    results = []
    for run in range(1, NUM_RUNS + 1):
        print(f"\n{'─' * 60}")
        print(f"Run {run}/{NUM_RUNS}")
        print("─" * 60)

        response = vlm.generate(
            prompt=prompt,
            images=[str(TEST_IMAGE)],
            force_json=True,
            json_schema=schema,
            max_new_tokens=256,  # 图像分析不需要 512，限制重复空间
        )

        rep = detect_repetition(response)
        results.append(rep)

        # 打印前 800 字符预览
        preview = response[:800]
        if len(response) > 800:
            preview += f"\n... ({len(response) - 800} more chars)"
        print(f"\n输出预览:\n{preview}")
        print(f"\n重复检测: {json.dumps(rep, indent=2, ensure_ascii=False)}")

        if rep["has_loop"]:
            print("⚠️  检测到循环/重复输出！")
        else:
            print("✅ 未检测到明显循环")

    # 总结
    print(f"\n{'=' * 60}")
    print("总结")
    print("=" * 60)
    loop_count = sum(1 for r in results if r["has_loop"])
    print(f"总运行次数: {NUM_RUNS}")
    print(f"检测到循环: {loop_count} 次")
    print(f"平均输出长度: {sum(r['total_chars'] for r in results) / len(results):.0f} 字符")
    print(f"平均重复率: {sum(r['repeat_ratio'] for r in results) / len(results):.3f}")

    if loop_count == 0:
        print("\n✅ 所有运行均未检测到循环，采样参数有效。")
    else:
        print(f"\n⚠️  {loop_count}/{NUM_RUNS} 次运行检测到循环，建议进一步调参或升级模型。")


if __name__ == "__main__":
    main()
