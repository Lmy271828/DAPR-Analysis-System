"""简化诊断脚本：仅测试 warmup"""
import sys
sys.path.insert(0, str(__file__).rsplit('/tests/', 1)[0])

import asyncio
from image_service import ComfyUIService

async def main():
    service = ComfyUIService()
    print("Calling warmup(force=True)...")
    ok = await service.warmup(force=True)
    print(f"warmup result: {ok}")
    await service.close()

asyncio.run(main())
