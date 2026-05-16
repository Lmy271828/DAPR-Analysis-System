"""
ComfyUI 端到端生成链路测试
================================
测试完整流程：upload → warmup → submit_batch → poll_batch → download_results
输入：test.jpeg（项目根目录）
输出：backend/tests/outputs/comfyui_e2e/

运行前提：
    ComfyUI 必须在 127.0.0.1:8188 运行，且已加载 FLUX.2 Klein 4B FP8 + Qwen3-4B FP4

启动命令（从项目根目录）：
    cd ComfyUI && python main.py --highvram --listen 127.0.0.1 --port 8188
"""
import os
import sys
import time
import json
import asyncio
import tempfile
from pathlib import Path
from datetime import datetime

# 将 backend 加入路径
sys.path.insert(0, str(Path(__file__).parent.parent))


# ═══════════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════════

COMFYUI_HOST = "127.0.0.1"
COMFYUI_PORT = 8188
# test.jpeg 位于项目根目录（DAPR-Analysis-System/），即 backend 的父目录的父目录
TEST_IMAGE = str(Path(__file__).parent.parent.parent.parent / "test.jpeg")
OUTPUT_DIR = str(Path(__file__).parent / "outputs" / "comfyui_e2e")

# 模拟 3 个心理分析场景的图像生成指令
TEST_VARIATIONS = [
    {
        "id": "warmth-test",
        "name": "温暖变体",
        "description": "增加暖色调，象征被试者对人际温暖的渴望",
        "edit_prompt": "Add warm golden sunlight streaming through the scene, enhance warm colors",
        "color_prompt": "warm amber, soft gold, peach tones",
        "hypothesis_id": "hypo-001"
    },
    {
        "id": "cool-test",
        "name": "冷色调变体",
        "description": "转换为冷色调，探索被试者的疏离感",
        "edit_prompt": "Transform into cool blue tones, add misty atmosphere",
        "color_prompt": "cool blue, silver, pale cyan",
        "hypothesis_id": "hypo-002"
    },
    {
        "id": "vibrant-test",
        "name": "高饱和变体",
        "description": "提高饱和度，测试被试者对情绪表达的开放程度",
        "edit_prompt": "Highly saturate all colors, make the image vivid and expressive",
        "color_prompt": "vibrant red, electric blue, bright yellow",
        "hypothesis_id": "hypo-003"
    }
]


# ═══════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════

async def check_comfyui_running() -> bool:
    """检查 ComfyUI 是否在运行"""
    import aiohttp
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as s:
            async with s.get(f"http://{COMFYUI_HOST}:{COMFYUI_PORT}/system_stats") as resp:
                return resp.status == 200
    except Exception:
        return False


def print_banner():
    print("=" * 70)
    print(" ComfyUI 端到端生成链路测试")
    print("=" * 70)
    print(f" 测试图像: {TEST_IMAGE}")
    print(f" 输出目录: {OUTPUT_DIR}")
    print(f" 变体数量: {len(TEST_VARIATIONS)}")
    print(f" 目标地址: http://{COMFYUI_HOST}:{COMFYUI_PORT}")
    print("=" * 70)
    print()


def print_section(name: str):
    print(f"\n{'─' * 70}")
    print(f"▶ {name}")
    print("─" * 70)


def print_result(name: str, success: bool, detail: str = ""):
    icon = "✅" if success else "❌"
    print(f"  {icon} {name}{f' — {detail}' if detail else ''}")


# ═══════════════════════════════════════════════════════════════════
# 核心测试
# ═══════════════════════════════════════════════════════════════════

async def run_e2e_test():
    from image_service import ComfyUIService
    from config import COMFYUI_CONFIG

    passed = 0
    failed = 0
    timing = {}
    overall_start = time.time()

    print_banner()

    # ── 前置检查 ──
    print_section("0. 环境检查")
    if not os.path.exists(TEST_IMAGE):
        print_result("测试图像存在", False, f"找不到 {TEST_IMAGE}")
        return False
    print_result("测试图像存在", True)

    comfyui_ready = await check_comfyui_running()
    if not comfyui_ready:
        print_result("ComfyUI 运行状态", False,
                     f"http://{COMFYUI_HOST}:{COMFYUI_PORT} 无响应")
        print("\n  ⚠️  请先启动 ComfyUI:")
        print(f"     cd ComfyUI && python main.py --highvram --listen {COMFYUI_HOST} --port {COMFYUI_PORT}")
        print(f"     或运行: bash scripts/comfyui_start.sh")
        return False
    print_result("ComfyUI 运行状态", True)

    # ── 初始化服务 ──
    print_section("1. 初始化 ComfyUIService")
    service = ComfyUIService()
    print_result("工作流加载", True, f"{len(service.workflow_template)} 个节点")
    print_result("配置验证", True,
                 f"server={service.server_address}, timeout={service.timeout}s")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ── Step 1: 上传图像 ──
    print_section("2. 上传图像 (upload_image_async)")
    t0 = time.time()
    try:
        upload_result = await service.upload_image_async(
            TEST_IMAGE, name="test_image_e2e.jpeg"
        )
        timing["upload"] = time.time() - t0
        print(f"  上传结果: {upload_result}")
        print_result("图像上传", True, f"{timing['upload']:.2f}s")
        passed += 1
    except Exception as e:
        print_result("图像上传", False, str(e))
        failed += 1
        await service.close()
        return False

    # ── Step 2: 模型预热 ──
    print_section("3. 模型预热 (warmup)")
    t0 = time.time()
    warmup_ok = await service.warmup(force=True)
    timing["warmup"] = time.time() - t0
    if warmup_ok:
        print_result("模型预热", True, f"{timing['warmup']:.2f}s")
        passed += 1
    else:
        print_result("模型预热", False, "超时或失败")
        failed += 1
        # 预热失败不一定阻塞后续，继续尝试

    # ── Step 3: 批量提交（带 WebSocket 错误监控）──
    print_section("4. 批量提交 (submit_batch) + WebSocket 监控")
    import uuid
    client_id = str(uuid.uuid4())
    
    # 启动 WebSocket 监控协程
    ws_task = asyncio.create_task(service.ws_monitor_execution(client_id, timeout=600))
    
    t0 = time.time()
    try:
        submitted = await service.submit_batch(
            "test_image_e2e.jpeg", TEST_VARIATIONS, client_id=client_id
        )
        timing["submit"] = time.time() - t0
        print(f"  已提交 {len(submitted)} 个任务 (client_id={client_id[:8]}):")
        for s in submitted:
            print(f"    [{s['index']}] prompt_id={s['prompt_id'][:16]}... prompt={s['prompt'][:60]}...")
        print_result("批量提交", True, f"{timing['submit']:.2f}s")
        passed += 1
    except Exception as e:
        print_result("批量提交", False, str(e))
        failed += 1
        ws_task.cancel()
        await service.close()
        return False

    # ── Step 4: 并行轮询 ──
    print_section("5. 并行轮询 (poll_batch)")
    print(f"  超时设置: {service.timeout}s，轮询间隔: 0.5s")
    t0 = time.time()
    try:
        completed, failed_items = await service.poll_batch(submitted, poll_interval=0.5)
        timing["poll"] = time.time() - t0
        print(f"  完成: {len(completed)} | 失败: {len(failed_items)}")
        for c in completed:
            info = c["image_info"]
            print(f"    ✅ {info.get('filename')} (subfolder={info.get('subfolder','')})")
        for f in failed_items:
            pid = f.get("prompt_id", "unknown")
            print(f"    ❌ prompt_id={pid[:16] if len(pid)>16 else pid}...")
        print_result("并行轮询", len(failed_items) == 0,
                     f"{timing['poll']:.2f}s ({len(completed)}/{len(submitted)})")
        if len(failed_items) == 0:
            passed += 1
        else:
            failed += 1
    except Exception as e:
        print_result("并行轮询", False, str(e))
        failed += 1
        ws_task.cancel()
        await service.close()
        return False
    
    # ── Step 4.5: 收集 WebSocket 错误日志 ──
    print_section("5.5 WebSocket 错误日志汇总")
    # 给 WebSocket 一点时间接收最后的 execution_complete 消息
    await asyncio.sleep(2)
    ws_task.cancel()
    try:
        ws_errors = await ws_task
    except asyncio.CancelledError:
        ws_errors = []
    
    if ws_errors:
        print(f"  ⚠️  通过 WebSocket 捕获到 {len(ws_errors)} 个执行错误:")
        for err in ws_errors:
            print(f"    ── 错误 ──")
            print(f"    prompt_id: {err.get('prompt_id', 'N/A')[:16]}")
            print(f"    node_id:   {err.get('node_id', 'N/A')}")
            print(f"    type:      {err.get('exception_type', 'N/A')}")
            print(f"    message:   {err.get('exception_message', 'N/A')[:300]}")
            tb = err.get('traceback', [])
            if tb:
                for line in tb[-3:]:
                    print(f"    {line[:150]}")
    else:
        print("  ✅ WebSocket 未捕获到执行错误")

    # ── Step 5: 并行下载 ──
    print_section("6. 并行下载 (download_results)")
    t0 = time.time()
    try:
        results = await service.download_results(completed, OUTPUT_DIR)
        timing["download"] = time.time() - t0
        print(f"  下载完成: {len(results)} 张图像")
        for r in results:
            size = os.path.getsize(r["filepath"])
            print(f"    ✅ {r['filename']} ({size/1024:.1f} KB) — {r['name']}")
        print_result("并行下载", True, f"{timing['download']:.2f}s")
        passed += 1
    except Exception as e:
        print_result("并行下载", False, str(e))
        failed += 1
        await service.close()
        return False

    # ── Step 6: 结果验证 ──
    print_section("7. 结果验证")
    all_valid = True
    for r in results:
        fp = r["filepath"]
        exists = os.path.exists(fp)
        size = os.path.getsize(fp) if exists else 0
        is_png = False
        if exists and size > 0:
            with open(fp, 'rb') as f:
                header = f.read(8)
                is_png = header[:4] == b'\x89PNG'
        ok = exists and size > 1000 and is_png
        print_result(f"{r['filename']}", ok,
                     f"{size/1024:.1f} KB {'PNG' if is_png else 'NOT PNG'}")
        if not ok:
            all_valid = False
            failed += 1
        else:
            passed += 1

    # ── 清理 ──
    await service.close()

    # ── 汇总 ──
    total_time = time.time() - overall_start
    print("\n" + "=" * 70)
    print(" 测试汇总")
    print("=" * 70)
    print(f"  总耗时:     {total_time:.2f}s")
    print(f"  上传:       {timing.get('upload', 0):.2f}s")
    print(f"  预热:       {timing.get('warmup', 0):.2f}s")
    print(f"  批量提交:   {timing.get('submit', 0):.2f}s")
    print(f"  并行轮询:   {timing.get('poll', 0):.2f}s")
    print(f"  并行下载:   {timing.get('download', 0):.2f}s")
    print(f"  测试通过:   {passed}")
    print(f"  测试失败:   {failed}")
    print("=" * 70)

    # 保存测试报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "test_image": TEST_IMAGE,
        "output_dir": OUTPUT_DIR,
        "comfyui_address": f"{COMFYUI_HOST}:{COMFYUI_PORT}",
        "timing": {k: round(v, 3) for k, v in timing.items()},
        "total_time_sec": round(total_time, 3),
        "variations_count": len(TEST_VARIATIONS),
        "results": [
            {"id": r["id"], "name": r["name"], "filename": r["filename"],
             "filepath": r["filepath"], "prompt": r["prompt"]}
            for r in results
        ],
        "passed": passed,
        "failed": failed,
        "success": failed == 0
    }
    report_path = Path(OUTPUT_DIR) / "test_report.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  测试报告已保存: {report_path}")

    return failed == 0


# ═══════════════════════════════════════════════════════════════════
# Entry
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    success = asyncio.run(run_e2e_test())
    sys.exit(0 if success else 1)
