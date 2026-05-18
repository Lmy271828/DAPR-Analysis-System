import { state } from './state.js';
import { connectWebSocket, setMessageHandlers } from './services/websocket.js';
import { updateSessionList, showHistoryModal, closeHistoryModal, analyzeHistorySession } from './components/session-list.js';
import { selectSession } from './components/session-detail.js';
import { renderLogs, handleLogMessage, clearLogs, refreshSessions, addLog } from './components/log-viewer.js';
import { fetchHistorySessions, fetchSessionDetail } from './services/api.js';

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

// 设置 WebSocket 消息处理器
setMessageHandlers({
    onSessionsList: updateSessionList,
    onLog: handleLogMessage
});

// 定时刷新会话列表
setInterval(refreshSessions, 5000);

// 从历史会话恢复已完成的分析结果到日志面板
async function loadHistoricalAnalysisLogs() {
    try {
        const history = await fetchHistorySessions();
        if (!history.sessions || history.sessions.length === 0) return;

        // 只恢复有分析结果的会话（最多最近 20 个，避免过多）
        const sessionsWithAnalysis = history.sessions
            .filter(s => s.session_data?.has_analysis)
            .slice(0, 20);

        for (const hist of sessionsWithAnalysis) {
            try {
                const session = await fetchSessionDetail(hist.id);
                if (!session || !session.initial_analysis) continue;

                // 构造一个模拟的 analysis_stream_complete 日志条目
                const logEntry = {
                    timestamp: session.created_at || new Date().toISOString(),
                    session_id: session.id,
                    stage: 'analysis_stream_complete',
                    llm_input: {},
                    llm_output: {
                        result: session.initial_analysis,
                        total_tokens: 0,
                        total_time: '0s',
                        avg_speed: '0 chars/s'
                    }
                };
                addLog(logEntry);

                // 如果有最终报告，也构造一个日志条目
                if (session.final_analysis) {
                    addLog({
                        timestamp: session.created_at || new Date().toISOString(),
                        session_id: session.id,
                        stage: 'final_report',
                        llm_input: {},
                        llm_output: session.final_analysis
                    });
                }
            } catch (e) {
                console.warn(`[Therapist] 恢复会话 ${hist.id} 失败:`, e);
            }
        }

        console.log(`[Therapist] 从历史会话恢复了 ${state.logs.length} 条日志`);
    } catch (e) {
        console.error('[Therapist] 加载历史分析日志失败:', e);
    }
}

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
    bindEvents();
    // 刷新前先加载历史会话的已完成分析，避免刷新后空白
    loadHistoricalAnalysisLogs();

    // 点击弹窗外部关闭
    document.getElementById('history-modal').addEventListener('click', function(e) {
        if (e.target === this) {
            closeHistoryModal();
        }
    });
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
