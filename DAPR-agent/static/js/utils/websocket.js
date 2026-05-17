/**
 * WebSocket 连接管理
 */

import { state, CONFIG } from '../config.js';

let messageHandler = null;

// 连接 WebSocket
export function connectWebSocket(onMessage) {
    if (onMessage) messageHandler = onMessage;
    if (!state.sessionId) return;
    if (state.ws && (state.ws.readyState === WebSocket.OPEN || state.ws.readyState === WebSocket.CONNECTING)) {
        return;
    }

    const ws = new WebSocket(CONFIG.WS_URL());
    state.ws = ws;
    
    ws.onopen = () => {
        console.log('WebSocket 已连接');
        state.wsReconnectAttempts = 0;
        if (state.wsReconnectTimer) {
            clearTimeout(state.wsReconnectTimer);
            state.wsReconnectTimer = null;
        }
        // 主动请求恢复上下文，避免中间短断线丢失进度
        ws.send(JSON.stringify({ type: 'resume_context' }));
    };
    
    ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        if (messageHandler) {
            messageHandler(message);
        }
    };
    
    ws.onclose = () => {
        console.log('WebSocket 已断开');
        if (state.wsManuallyClosed) return;
        scheduleReconnect();
    };
    
    ws.onerror = (error) => {
        console.error('WebSocket 错误:', error);
    };
}

export function scheduleReconnect() {
    state.wsReconnectAttempts += 1;
    const expBackoff = Math.min(
        CONFIG.WS_RECONNECT_BASE_MS * (2 ** (state.wsReconnectAttempts - 1)),
        CONFIG.WS_RECONNECT_MAX_MS
    );
    const jitter = Math.floor(Math.random() * CONFIG.WS_RECONNECT_JITTER_MS);
    const delay = expBackoff + jitter;
    console.log(`[WebSocket] 第${state.wsReconnectAttempts}次重连，${delay}ms 后重试`);

    if (state.wsReconnectTimer) {
        clearTimeout(state.wsReconnectTimer);
    }
    state.wsReconnectTimer = setTimeout(() => {
        connectWebSocket();
    }, delay);
}
