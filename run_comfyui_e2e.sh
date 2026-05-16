#!/bin/bash
# ComfyUI 环境配置 + 启动 + 端到端测试
set -e

cd /home/lenovo/pynoob/DAPR-Analysis-System/ComfyUI

echo "=== Step 1: 安装 PyTorch (CUDA 13.0) ==="
source .venv/bin/activate
uv pip install torch==2.9.1 torchvision==0.24.1 torchaudio --index-url https://download.pytorch.org/whl/cu130

echo "=== Step 2: 安装 ComfyUI 依赖 ==="
uv pip install -r requirements.txt

echo "=== Step 3: 启动 ComfyUI ==="
python main.py --highvram --listen 127.0.0.1 --port 8188 &
COMFY_PID=$!
echo "ComfyUI PID: $COMFY_PID"

# 等待 ComfyUI 就绪
echo "=== Step 4: 等待 ComfyUI 就绪 (最多 60 秒) ==="
for i in $(seq 1 60); do
    if curl -s http://127.0.0.1:8188/system_stats > /dev/null 2>&1; then
        echo "ComfyUI 已就绪!"
        break
    fi
    echo "  等待中... ($i/60)"
    sleep 1
done

echo "=== Step 5: 运行端到端测试 ==="
cd /home/lenovo/pynoob/DAPR-Analysis-System/DAPR-agent
source .venv/bin/activate
python backend/tests/test_comfyui_e2e.py

echo "=== 测试完成，关闭 ComfyUI ==="
kill $COMFY_PID 2>/dev/null || true
