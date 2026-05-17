#!/bin/bash
# =============================================================================
# DAPR-Analysis-System 一键停止脚本
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC}  $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }

COMFYUI_PID_FILE="/tmp/dapr_comfyui.pid"
BACKEND_PID_FILE="/tmp/dapr_backend.pid"
COMFYUI_PORT=8188
BACKEND_PORT=8000

# ── 停止后端服务 ──
if [[ -f "$BACKEND_PID_FILE" ]]; then
    pid=$(cat "$BACKEND_PID_FILE" 2>/dev/null)
    if kill -0 "$pid" 2>/dev/null; then
        info "停止后端服务 (PID=$pid)..."
        kill "$pid" 2>/dev/null || true
        sleep 1
        ok "后端服务已停止"
    else
        warn "后端进程已不存在"
    fi
    rm -f "$BACKEND_PID_FILE"
else
    # 尝试通过端口查找
    pids=$(lsof -ti:"$BACKEND_PORT" 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        info "通过端口 $BACKEND_PORT 停止后端..."
        echo "$pids" | xargs kill -9 2>/dev/null || true
        ok "后端服务已停止"
    fi
fi

# ── 停止 ComfyUI ──
if [[ -f "$COMFYUI_PID_FILE" ]]; then
    pid=$(cat "$COMFYUI_PID_FILE" 2>/dev/null)
    if kill -0 "$pid" 2>/dev/null; then
        info "停止 ComfyUI (PID=$pid)..."
        kill "$pid" 2>/dev/null || true
        sleep 2
        if kill -0 "$pid" 2>/dev/null; then
            warn "强制终止 ComfyUI..."
            kill -9 "$pid" 2>/dev/null || true
        fi
        ok "ComfyUI 已停止"
    else
        warn "ComfyUI 进程已不存在"
    fi
    rm -f "$COMFYUI_PID_FILE"
else
    # 尝试通过端口查找
    pids=$(lsof -ti:"$COMFYUI_PORT" 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        info "通过端口 $COMFYUI_PORT 停止 ComfyUI..."
        echo "$pids" | xargs kill -9 2>/dev/null || true
        ok "ComfyUI 已停止"
    fi
fi

# ── 清理临时数据库 ──
rm -f /tmp/dapr_comfyui.db /tmp/dapr_comfyui.db-journal 2>/dev/null || true

ok "所有服务已清理"
