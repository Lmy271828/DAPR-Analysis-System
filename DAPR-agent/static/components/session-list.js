import { state } from '../state.js';
import { fetchHistorySessions, startHistoryAnalysis } from '../services/api.js';

export function updateSessionList(sessions) {
    state.sessions = sessions;
    const container = document.getElementById('session-list');

    if (sessions.length === 0) {
        container.innerHTML = '<div style="padding: 20px; text-align: center; color: #666;">暂无会话</div>';
        return;
    }

    container.innerHTML = sessions.map(session => `
        <div class="session-item ${session.id === state.selectedSession ? 'active' : ''}" 
             data-id="${session.id}"
             onclick="selectSession('${session.id}')">
            <div class="session-id">${session.id.substring(0, 8)}...</div>
            <span class="session-status status-${session.status}">${session.status}</span>
            <div style="margin-top: 8px; font-size: 0.8rem; color: #666;">
                ${new Date(session.created_at).toLocaleString()}
            </div>
        </div>
    `).join('');
}

// ==================== 历史会话导入功能 ====================

export function showHistoryModal() {
    document.getElementById('history-modal').style.display = 'block';
    loadHistorySessions();
}

export function closeHistoryModal() {
    document.getElementById('history-modal').style.display = 'none';
}

export async function loadHistorySessions() {
    const loadingEl = document.getElementById('history-loading');
    const listEl = document.getElementById('history-list');
    const emptyEl = document.getElementById('history-empty');

    loadingEl.style.display = 'block';
    listEl.style.display = 'none';
    emptyEl.style.display = 'none';

    try {
        const data = await fetchHistorySessions();

        loadingEl.style.display = 'none';

        if (data.sessions.length === 0) {
            emptyEl.style.display = 'block';
            return;
        }

        renderHistorySessions(data.sessions);
        listEl.style.display = 'block';

    } catch (error) {
        console.error('加载历史会话失败:', error);
        loadingEl.innerHTML = `<p style="color: #e94560;">加载失败: ${error.message}</p>`;
    }
}

export function renderHistorySessions(sessions) {
    const container = document.getElementById('history-list');

    container.innerHTML = sessions.map(session => {
        const hasWebcam = session.files.webcam ? '✅' : '❌';
        const hasScreen = session.files.screen ? '✅' : '❌';
        const hasJson = session.files.json ? '✅' : '❌';
        const createdAt = session.created_at ? new Date(session.created_at).toLocaleString() : '未知时间';

        const hasAnalysis = session.session_data?.has_analysis;
        const analysisBadge = hasAnalysis ? 
            '<span style="background: #28a745; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem;">已分析</span>' :
            '<span style="background: #ffc107; color: #000; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem;">未分析</span>';

        return `
            <div class="history-item" style="background: #16213e; border: 1px solid #0f3460; border-radius: 8px; padding: 15px; margin-bottom: 15px; display: flex; gap: 15px;">
                <div class="history-preview" style="width: 120px; height: 120px; background: #1a1a2e; border-radius: 8px; overflow: hidden; flex-shrink: 0;">
                    <img src="/api/history/session/${session.id}/preview" 
                         style="width: 100%; height: 100%; object-fit: contain;"
                         onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2280%22>🎨</text></svg>'">
                </div>
                <div class="history-info" style="flex: 1;">
                    <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 10px;">
                        <div>
                            <h4 style="margin: 0 0 5px 0; color: #eee;">会话 ${session.id.substring(0, 8)}...</h4>
                            <p style="margin: 0; font-size: 0.85rem; color: #888;">${createdAt}</p>
                        </div>
                        ${analysisBadge}
                    </div>
                    <div style="display: flex; gap: 15px; font-size: 0.8rem; color: #aaa; margin-bottom: 10px;">
                        <span title="摄像头视频">📹 ${hasWebcam}</span>
                        <span title="屏幕录制">🖥️ ${hasScreen}</span>
                        <span title="会话数据">💾 ${hasJson}</span>
                    </div>
                    <div style="display: flex; gap: 10px;">
                        <button onclick="analyzeHistorySession('${session.id}', false)" 
                                style="flex: 1; padding: 8px 16px; background: #e94560; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 0.85rem;"
                                title="在原始会话上重新进行分析，会覆盖之前的分析结果">
                            🔍 重新分析
                        </button>
                        <button onclick="analyzeHistorySession('${session.id}', true)" 
                                style="flex: 1; padding: 8px 16px; background: #0f3460; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 0.85rem;"
                                title="创建一个新会话，复制该会话的绘画和视频文件进行独立分析，不会修改原始会话数据">
                            📋 复制为新会话
                        </button>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

export async function analyzeHistorySession(sessionId, createNew) {
    const action = createNew ? '复制为新会话' : '重新分析';
    console.log(`[History] ${action}: ${sessionId}`);

    try {
        const response = await startHistoryAnalysis(sessionId, createNew);
        const data = await response.json();

        if (response.ok) {
            console.log(`[History] 分析已启动:`, data);
            closeHistoryModal();

            setTimeout(() => {
                if (state.ws && state.ws.readyState === WebSocket.OPEN) {
                    state.ws.send(JSON.stringify({ type: 'list_sessions' }));
                }
            }, 500);
        } else {
            throw new Error(data.detail || '启动分析失败');
        }

    } catch (error) {
        console.error('[History] 分析失败:', error);
        alert(`❌ 分析失败: ${error.message}`);
    }
}
