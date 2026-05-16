"""
ComfyUI 单任务端到端测试（用于验证修复）
"""
import os
import sys
import time
import json
import asyncio
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

TEST_IMAGE = str(Path(__file__).parent.parent.parent.parent / "test.jpeg")
OUTPUT_DIR = str(Path(__file__).parent / "outputs" / "comfyui_single")

async def run_test():
    from image_service import ComfyUIService
    
    print("=" * 60)
    print("ComfyUI 单任务端到端测试")
    print("=" * 60)
    
    service = ComfyUIService()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 上传
    print("\n[1/4] 上传图像...")
    upload_result = await service.upload_image_async(TEST_IMAGE, name="test_single.jpeg")
    print(f"  上传结果: {upload_result}")
    
    # 预热
    print("\n[2/4] 模型预热...")
    t0 = time.time()
    warmup_ok = await service.warmup(force=True)
    print(f"  预热结果: {warmup_ok} ({time.time()-t0:.1f}s)")
    
    # 提交单个任务
    print("\n[3/4] 提交单任务...")
    variations = [{
        "id": "single-test",
        "name": "单任务测试",
        "edit_prompt": "Add warm golden sunlight",
        "color_prompt": "warm amber, soft gold",
    }]
    
    t0 = time.time()
    submitted = await service.submit_batch("test_single.jpeg", variations)
    print(f"  提交耗时: {time.time()-t0:.2f}s")
    print(f"  prompt_id: {submitted[0]['prompt_id']}")
    
    # 轮询
    print("\n[4/4] 轮询等待...")
    t0 = time.time()
    completed, failed = await service.poll_batch(submitted, poll_interval=0.5)
    print(f"  轮询耗时: {time.time()-t0:.1f}s")
    print(f"  完成: {len(completed)} | 失败: {len(failed)}")
    
    # 下载
    if completed:
        results = await service.download_results(completed, OUTPUT_DIR)
        for r in results:
            size = os.path.getsize(r["filepath"])
            print(f"  ✅ {r['filename']} ({size/1024:.1f} KB)")
    
    await service.close()
    
    print("\n" + "=" * 60)
    print(f"测试结果: {'通过' if len(completed)>0 else '失败'}")
    print("=" * 60)
    return len(completed) > 0

if __name__ == "__main__":
    success = asyncio.run(run_test())
    sys.exit(0 if success else 1)
