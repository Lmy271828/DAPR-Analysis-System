import { state } from '../state.js';

let messageHandlers = {};

export function setMessageHandlers(handlers) {
    messageHandlers = handlers;
}

export function connectWebSocket() {
    if (state.ws && (state.ws.readyState === WebSocket.OPEN || state.ws.readyState === WebSocket.CONNECTING)) {
        return;
    }

    const wsUrl = `ws://${window.location.host}/ws/therapist`;
    state.ws = new WebSocket(wsUrl);

    state.ws.onopen = () => {
        console.log('WebSocket 已连接');
        updateConnectionStatus(true);
        state.wsReconnectAttempts = 0;
        if (state.wsReconnectTimer) {
            clearTimeout(state.wsReconnectTimer);
            state.wsReconnectTimer = null;
        }
        // 请求会话列表
        state.ws.send(JSON.stringify({ type: 'list_sessions' }));
    };

    state.ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        handleMessage(message);
    };

    state.ws.onclose = () => {
        console.log('WebSocket 已断开');
        updateConnectionStatus(false);
        if (state.wsManuallyClosed) return;
        scheduleReconnect();
    };

    state.ws.onerror = (error) => {
        console.error('WebSocket 错误:', error);
        updateConnectionStatus(false);
    };
}

export function scheduleReconnect() {
    state.wsReconnectAttempts += 1;
    const base = 1000;
    const max = 30000;
    const jitter = Math.floor(Math.random() * 300);
    const delay = Math.min(base * (2 ** (state.wsReconnectAttempts - 1)), max) + jitter;

    console.log(`[WebSocket] 第${state.wsReconnectAttempts}次重连，${delay}ms 后重试`);
    if (state.wsReconnectTimer) {
        clearTimeout(state.wsReconnectTimer);
    }
    state.wsReconnectTimer = setTimeout(connectWebSocket, delay);
}

// 更新连接状态
export function updateConnectionStatus(connected) {
    const dot = document.getElementById('ws-status');
    const text = document.getElementById('ws-text');
    dot.classList.toggle('disconnected', !connected);
    text.textContent = connected ? '已连接' : '已断开';
}

// 处理消息
export function handleMessage(message) {
    if (message.type === 'ping') {
        if (state.ws && state.ws.readyState === WebSocket.OPEN) {
            state.ws.send(JSON.stringify({ type: 'pong', data: { ts: message?.data?.ts || null } }));
        }
        return;
    }

    switch (message.type) {
        case 'sessions_list':
            if (messageHandlers.onSessionsList) {
                messageHandlers.onSessionsList(message.data);
            }
            break;
        case 'log':
            if (messageHandlers.onLog) {
                messageHandlers.onLog(message.data);
            }
            break;
    }
}
