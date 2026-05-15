import { state, streamState } from '../state.js';
import { formatLogContent } from '../utils/formatters.js';

export function addLog(log) {
    state.logs.unshift(log);

    if (state.logs.length > 100) {
        state.logs = state.logs.slice(0, 100);
    }

    renderLogs();
}

export function handleLogMessage(log) {
    if (log.stage === 'analysis_stream_chunk') {
        handleStreamChunk(log);
    } else if (log.stage === 'analysis_stream_complete') {
        handleStreamComplete(log);
    } else if (log.stage === 'analysis_stream_start') {
        handleStreamStart(log);
    } else {
        addLog(log);
    }
}

export function handleStreamStart(log) {
    const sessionId = log.session_id;
    console.log(`[Stream] 开始流式分析: ${sessionId}`);

    let streamEntry = streamState.activeStreams.get(sessionId);
    if (!streamEntry) {
        streamEntry = {
            chunks: [],
            element: createStreamLogElement(log),
            startTime: Date.now()
        };
        streamState.activeStreams.set(sessionId, streamEntry);
    }
}

export function handleStreamChunk(log) {
    const sessionId = log.session_id;
    const output = log.llm_output || {};
    const chunk = output.chunk || '';
    const speed = output.speed || '0.00 chars/s';

    let streamEntry = streamState.activeStreams.get(sessionId);
    if (!streamEntry) {
        handleStreamStart(log);
        streamEntry = streamState.activeStreams.get(sessionId);
    }

    streamEntry.chunks.push(chunk);

    const fullText = streamEntry.chunks.join('');
    updateStreamDisplay(streamEntry.element, fullText, speed, output.token_count || fullText.length);
}

export function handleStreamComplete(log) {
    const sessionId = log.session_id;
    const output = log.llm_output || {};

    console.log(`[Stream] 流式分析完成: ${sessionId}`);

    const streamEntry = streamState.activeStreams.get(sessionId);
    if (streamEntry) {
        markStreamComplete(streamEntry.element, output);
        streamState.activeStreams.delete(sessionId);
    }

    addLog(log);
}

export function createStreamLogElement(log) {
    const container = document.getElementById('log-container');

    const entry = document.createElement('div');
    entry.className = 'log-entry streaming';
    entry.dataset.sessionId = log.session_id;
    entry.innerHTML = `
        <div class="log-header">
            <div>
                <span class="log-session">${log.session_id.substring(0, 8)}...</span>
                <span class="log-time">${new Date(log.timestamp).toLocaleString()}</span>
            </div>
            <span class="log-stage" style="background: #6610f2;">🔴 分析中...</span>
        </div>
        <div class="log-section">
            <div class="log-section-title">⚡ 实时生成中</div>
            <div class="stream-stats" style="font-size: 0.85rem; color: #888; margin-bottom: 10px;">
                速度: <span class="stream-speed">0.00 chars/s</span> | 
                字符数: <span class="stream-tokens">0</span>
            </div>
            <div class="stream-content log-content" style="background: #0f3460; min-height: 100px; max-height: 400px; overflow-y: auto; white-space: pre-wrap; font-family: monospace; font-size: 0.85rem; line-height: 1.5;">
                等待输出...
            </div>
        </div>
    `;

    const emptyState = container.querySelector('.empty-state');
    if (emptyState) {
        emptyState.remove();
    }
    container.insertBefore(entry, container.firstChild);

    return entry;
}

export function updateStreamDisplay(element, text, speed, tokenCount) {
    if (!element) return;

    const contentEl = element.querySelector('.stream-content');
    const speedEl = element.querySelector('.stream-speed');
    const tokenEl = element.querySelector('.stream-tokens');

    if (contentEl) {
        const displayText = text.slice(-1000);
        contentEl.textContent = displayText;
        contentEl.scrollTop = contentEl.scrollHeight;
    }
    if (speedEl) speedEl.textContent = speed;
    if (tokenEl) tokenEl.textContent = tokenCount;
}

export function markStreamComplete(element, output) {
    if (!element) return;

    const stageEl = element.querySelector('.log-stage');
    const statsEl = element.querySelector('.stream-stats');

    if (stageEl) {
        stageEl.textContent = '✅ 分析完成';
        stageEl.style.background = '#28a745';
    }
    if (statsEl) {
        statsEl.innerHTML = `
            <strong>分析完成</strong>  // 统计信息已在终端记录
        `;
    }

    element.classList.remove('streaming');
    element.classList.add('stream-complete');
}

export function renderLogs() {
    const container = document.getElementById('log-container');

    let filteredLogs = state.logs;

    if (state.filter !== 'all') {
        if (state.filter === 'llm') {
            filteredLogs = state.logs.filter(log => log.llm_input || log.llm_output);
        } else if (state.filter === 'flux2') {
            filteredLogs = state.logs.filter(log => log.flux2_input || log.flux2_output);
        }
    }

    if (state.selectedSession) {
        filteredLogs = filteredLogs.filter(log => log.session_id === state.selectedSession);
    }

    if (filteredLogs.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📋</div>
                <p>${state.logs.length === 0 ? '等待新的日志...' : '没有符合条件的日志'}</p>
            </div>
        `;
        return;
    }

    container.innerHTML = filteredLogs.map(log => `
        <div class="log-entry">
            <div class="log-header">
                <div>
                    <span class="log-session">${log.session_id.substring(0, 8)}...</span>
                    <span class="log-time">${new Date(log.timestamp).toLocaleString()}</span>
                </div>
                <span class="log-stage">${log.stage}</span>
            </div>
            ${formatLogContent(log)}
        </div>
    `).join('');
}

export function clearLogs() {
    state.logs = [];
    renderLogs();
}

export function refreshSessions() {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({ type: 'list_sessions' }));
    }
}
