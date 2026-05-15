import { state } from './state.js';
import { connectWebSocket, setMessageHandlers } from './services/websocket.js';
import { updateSessionList, showHistoryModal, closeHistoryModal, analyzeHistorySession } from './components/session-list.js';
import { selectSession } from './components/session-detail.js';
import { renderLogs, handleLogMessage, clearLogs, refreshSessions } from './components/log-viewer.js';

// 绑定事件
function bindEvents() {
    document.querySelectorAll('.filter-tag').forEach(tag => {
        tag.addEventListener('click', () => {
            document.querySelectorAll('.filter-tag').forEach(t => t.classList.remove('active'));
            tag.classList.add('active');
            state.filter = tag.dataset.filter;
            renderLogs();
        });
    });
}

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
    bindEvents();
});

// 设置 WebSocket 消息处理器
setMessageHandlers({
    onSessionsList: updateSessionList,
    onLog: handleLogMessage
});

// 定时刷新会话列表
setInterval(refreshSessions, 5000);

// 点击弹窗外部关闭
document.getElementById('history-modal').addEventListener('click', function(e) {
    if (e.target === this) {
        closeHistoryModal();
    }
});

window.addEventListener('beforeunload', () => {
    state.wsManuallyClosed = true;
    if (state.wsReconnectTimer) {
        clearTimeout(state.wsReconnectTimer);
        state.wsReconnectTimer = null;
    }
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.close(1000, 'page unloading');
    }
});

// 暴露全局函数供 HTML inline onclick 使用
window.selectSession = selectSession;
window.refreshSessions = refreshSessions;
window.clearLogs = clearLogs;
window.showHistoryModal = showHistoryModal;
window.closeHistoryModal = closeHistoryModal;
window.analyzeHistorySession = analyzeHistorySession;
