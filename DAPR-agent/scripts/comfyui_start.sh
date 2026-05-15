#!/bin/bash
# ComfyUI 启动脚本 - 高显存模式（模型常驻显存）
# 适用于 RTX 5060 8GB + FLUX2-klein-4B-FP8 + Qwen3-4B-FP4

cd "$(dirname "$0")"

# 高显存模式：模型常驻显存，避免反复加载卸载
# --listen: 仅监听本地，避免外部访问
# --port: 默认 8188
python main.py \
    --highvram \
    --listen 127.0.0.1 \
    --port 8188 \
    "$@"
