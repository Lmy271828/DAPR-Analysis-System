"""诊断脚本：先上传再 warmup"""
import sys
sys.path.insert(0, str(__file__).rsplit('/tests/', 1)[0])

import asyncio
from image_service import ComfyUIService

async def main():
    service = ComfyUIService()
    print("Step 1: upload image...")
    result = await service.upload_image_async(
        "/home/lenovo/pynoob/DAPR-Analysis-System/test.jpeg",
        name="test_image_e2e.jpeg"
    )
    print(f"upload result: {result}")
    
    print("Step 2: warmup...")
    ok = await service.warmup(force=True)
    print(f"warmup result: {ok}")
    
    await service.close()

asyncio.run(main())
