#!/bin/bash
# =============================================================================
# DAPR-Analysis-System 一键启动脚本
# =============================================================================
# 功能：
#   1. 检查 conda py312 环境
#   2. 启动 ComfyUI 后台服务（模型预热）
#   3. 等待 ComfyUI 就绪
#   4. 启动 DAPR-Agent 后端服务
#
# 使用：
#   ./start.sh              # 前台启动后端（ComfyUI 在后台）
#   ./start.sh --daemon     # 全部后台启动
#   ./start.sh --comfy-only # 只启动 ComfyUI
# =============================================================================

set -e

# ── 配置 ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMFYUI_DIR="$SCRIPT_DIR/ComfyUI"
BACKEND_DIR="$SCRIPT_DIR/DAPR-agent/backend"
CONDA_ENV="py312"
CONDA_PYTHON="/home/lenovo/miniconda3/envs/py312/bin/python"
COMFYUI_PORT=8188
BACKEND_PORT=8000
COMFYUI_LOG="/tmp/dapr_comfyui.log"
BACKEND_LOG="/tmp/dapr_backend.log"
COMFYUI_PID_FILE="/tmp/dapr_comfyui.pid"
BACKEND_PID_FILE="/tmp/dapr_backend.pid"

# ── 颜色输出 ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()  { echo -e "${BLUE}[INFO]${NC}  $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ── 参数解析 ──
DAEMON_MODE=false
COMFY_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --daemon) DAEMON_MODE=true; shift ;;
        --comfy-only) COMFY_ONLY=true; shift ;;
        --help|-h)
            echo "用法: ./start.sh [选项]"
            echo ""
            echo "选项:"
            echo "  --daemon       全部后台启动"
            echo "  --comfy-only   只启动 ComfyUI"
            echo "  --help, -h     显示此帮助"
            exit 0
            ;;
        *) error "未知参数: $1"; exit 1 ;;
    esac
done

# ── 检查 conda 环境 ──
info "检查 conda 环境: $CONDA_ENV"
if ! conda info --envs 2>/dev/null | grep -q "^$CONDA_ENV "; then
    error "conda 环境 '$CONDA_ENV' 不存在"
    error "请执行: conda create -n $CONDA_ENV python=3.12"
    exit 1
fi

if [[ ! -f "$CONDA_PYTHON" ]]; then
    error "找不到 Python 解释器: $CONDA_PYTHON"
    exit 1
fi

PYTHON_VERSION=$($CONDA_PYTHON --version 2>&1)
ok "conda 环境就绪: $PYTHON_VERSION"

# ── 检查模型文件 ──
info "检查 FLUX.2 模型..."
MODEL_NVFP4="$COMFYUI_DIR/models/diffusion_models/flux-2-klein-4b-nvfp4.safetensors"
MODEL_FP8="$COMFYUI_DIR/models/diffusion_models/flux-2-klein-4b-fp8.safetensors"
TEXTENC="$COMFYUI_DIR/models/text_encoders/qwen_3_4b_fp4_flux2.safetensors"
VAE="$COMFYUI_DIR/models/vae/flux2-vae.safetensors"

if [[ -f "$MODEL_NVFP4" ]]; then
    ok "模型: flux-2-klein-4b-nvfp4.safetensors (NVFP4)"
elif [[ -f "$MODEL_FP8" ]]; then
    warn "模型: flux-2-klein-4b-fp8.safetensors (FP8，建议改用 NVFP4)"
else
    error "找不到 FLUX.2 模型文件"
    error "请在 $COMFYUI_DIR/models/diffusion_models/ 目录放置模型"
    exit 1
fi

[[ -f "$TEXTENC" ]] && ok "TextEncoder: qwen_3_4b_fp4_flux2.safetensors" || warn "TextEncoder 缺失"
[[ -f "$VAE" ]] && ok "VAE: flux2-vae.safetensors" || warn "VAE 缺失"

# ── 清理旧进程 ──
info "清理旧进程..."
for pidfile in "$COMFYUI_PID_FILE" "$BACKEND_PID_FILE"; do
    if [[ -f "$pidfile" ]]; then
        old_pid=$(cat "$pidfile" 2>/dev/null)
        if kill -0 "$old_pid" 2>/dev/null; then
            warn "终止旧进程 PID=$old_pid"
            kill "$old_pid" 2>/dev/null || true
            sleep 1
        fi
        rm -f "$pidfile"
    fi
done
lsof -ti:"$COMFYUI_PORT" 2>/dev/null | xargs kill -9 2>/dev/null || true

# ── 启动 ComfyUI ──
info "启动 ComfyUI (端口 $COMFYUI_PORT)..."
cd "$COMFYUI_DIR"
nohup "$CONDA_PYTHON" -u main.py \
    --highvram \
    --listen 127.0.0.1 \
    --port "$COMFYUI_PORT" \
    --database-url /tmp/dapr_comfyui.db \
    > "$COMFYUI_LOG" 2>&1 &
COMFYUI_PID=$!
echo $COMFYUI_PID > "$COMFYUI_PID_FILE"

# ── 等待 ComfyUI 就绪 ──
info "等待 ComfyUI 就绪..."
for i in {1..60}; do
    if curl -s --max-time 2 "http://127.0.0.1:$COMFYUI_PORT/system_stats" >/dev/null 2>&1; then
        ok "ComfyUI 就绪 (PID=$COMFYUI_PID)"
        # 显示 GPU 信息
        gpu_info=$(curl -s --max-time 3 "http://127.0.0.1:$COMFYUI_PORT/system_stats" 2>/dev/null | \
            python3 -c "import sys,json; d=json.load(sys.stdin); g=d['devices'][0]; print(f'{g['name']} ({g['vram_total']/1e9:.1f}GB)')" 2>/dev/null || echo "unknown")
        info "GPU: $gpu_info"
        break
    fi
    if ! kill -0 "$COMFYUI_PID" 2>/dev/null; then
        error "ComfyUI 进程已退出，请检查日志: $COMFYUI_LOG"
        tail -30 "$COMFYUI_LOG"
        exit 1
    fi
    echo -n "."
    sleep 2
done

if ! curl -s --max-time 2 "http://127.0.0.1:$COMFYUI_PORT/system_stats" >/dev/null 2>&1; then
    error "ComfyUI 启动超时"
    tail -30 "$COMFYUI_LOG"
    exit 1
fi

# ── 如果只启动 ComfyUI ──
if [[ "$COMFY_ONLY" == true ]]; then
    ok "ComfyUI 已启动，后台运行中"
    info "日志: tail -f $COMFYUI_LOG"
    info "停止: ./stop.sh"
    exit 0
fi

# ── 启动后端服务 ──
info "启动 DAPR-Agent 后端 (端口 $BACKEND_PORT)..."
cd "$BACKEND_DIR"

if [[ "$DAEMON_MODE" == true ]]; then
    nohup "$CONDA_PYTHON" -u main.py > "$BACKEND_LOG" 2>&1 &
    BACKEND_PID=$!
    echo $BACKEND_PID > "$BACKEND_PID_FILE"
    ok "后端服务已后台启动 (PID=$BACKEND_PID)"
    info "日志: tail -f $BACKEND_LOG"
else
    ok "后端服务即将启动，按 Ctrl+C 停止"
    info "============================================"
    info "ComfyUI:  http://127.0.0.1:$COMFYUI_PORT"
    info "Backend:  http://127.0.0.1:$BACKEND_PORT"
    info "============================================"
    "$CONDA_PYTHON" -u main.py
fi
