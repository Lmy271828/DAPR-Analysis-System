/**
 * DAPR Agent 前端应用入口
 */

import { state, elements, streamAnalysisState } from './config.js';
import { initElements, showPage } from './utils/dom.js';
import { connectWebSocket } from './utils/websocket.js';
import {
    requestCameraPermission,
    requestScreenPermission,
    startRecording,
    submitDrawing,
    rotateCanvas,
    setTool,
    clearCanvas,
    resizeCanvas
} from './pages/drawing.js';
import {
    handleChatQuestion,
    submitChatAnswer,
    handleInterviewComplete,
    skipInterview
} from './pages/interview.js';
import {
    showGeneratedImages,
    cancelPreview,
    confirmSelection
} from './pages/selecting.js';
import {
    showFinalQuestions,
    submitFinalAnswers,
    showFinalReport
} from './pages/final.js';

// 初始化
 document.addEventListener('DOMContentLoaded', () => {
    initElements();
    bindEvents();
    createSession();
});

// 安全绑定事件辅助函数
function safeAddEventListener(elementName, event, handler) {
    const el = elements[elementName];
    if (el) {
        el.addEventListener(event, handler);
    } else {
        console.warn(`[BindEvents] 元素 '${elementName}' 未找到，跳过事件绑定`);
    }
}

// 绑定事件
function bindEvents() {
    console.log('[App] bindEvents 开始执行');

    // 知情同意弹窗
    const cb = elements['consent-checkbox'];
    const btn = elements['consent-btn'];
    if (!cb || !btn) {
        console.error('[BindEvents] consent-checkbox 或 consent-btn 元素未找到', { cb, btn });
        return;
    }
    cb.addEventListener('change', (e) => {
        console.log('[Consent] checkbox changed:', e.target.checked);
        btn.disabled = !e.target.checked;
    });
    btn.addEventListener('click', async () => {
        const ageGroup = elements['age-group-select']?.value || '';
        try {
            await fetch(`/api/session/${state.sessionId}/consent`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(ageGroup ? { age_group: ageGroup } : {})
            });
        } catch (e) {
            console.warn('[Consent] 发送同意状态失败:', e);
        }
        elements['consent-modal'].classList.remove('active');
        showPage('guidance-page');
        window.scrollTo({ top: 0, behavior: 'smooth' });
        sessionStorage.setItem('dapr_consent_given', 'true');
    });

    // 引导页
    safeAddEventListener('start-btn', 'click', () => showPage('permission-page'));
    
    // 权限页
    safeAddEventListener('request-camera-btn', 'click', requestCameraPermission);
    safeAddEventListener('request-screen-btn', 'click', requestScreenPermission);
    safeAddEventListener('enter-drawing-btn', 'click', () => {
        showPage('drawing-page');
        // 延迟初始化画布，确保 DOM 已渲染
        setTimeout(() => {
            import('./pages/drawing.js').then(m => {
                if (m.initCanvas) m.initCanvas();
            });
        }, 100);
    });
    
    // 绘画页
    safeAddEventListener('start-recording-btn', 'click', startRecording);
    safeAddEventListener('submit-drawing-btn', 'click', submitDrawing);
    
    // 工具栏
    safeAddEventListener('rotate-btn', 'click', rotateCanvas);
    safeAddEventListener('pen-btn', 'click', () => setTool('pen'));
    safeAddEventListener('eraser-btn', 'click', () => setTool('eraser'));
    safeAddEventListener('clear-btn', 'click', clearCanvas);
    safeAddEventListener('brush-size', 'input', (e) => {
        state.brushSize = parseInt(e.target.value);
    });
    
    // 问答页（自主访谈聊天）
    safeAddEventListener('chat-send-btn', 'click', submitChatAnswer);
    safeAddEventListener('chat-input', 'keypress', (e) => {
        if (e.key === 'Enter') submitChatAnswer();
    });
    safeAddEventListener('skip-interview-btn', 'click', skipInterview);
    
    // 选择页
    safeAddEventListener('cancel-preview-btn', 'click', cancelPreview);
    safeAddEventListener('confirm-preview-btn', 'click', confirmSelection);
    
    // 最终问题页
    safeAddEventListener('submit-final-btn', 'click', submitFinalAnswers);
    
    // 结果页：重新开始时清除会话存储，避免恢复到已完成的旧会话
    safeAddEventListener('restart-btn', 'click', () => {
        sessionStorage.removeItem('dapr_session_id');
        location.reload();
    });

    console.log('[App] bindEvents 执行完成');
}

// 创建会话（支持浏览器刷新后恢复）
async function createSession() {
    try {
        // 检查是否有未完成的历史会话（浏览器刷新/Ctrl+R 恢复）
        const savedId = sessionStorage.getItem('dapr_session_id');
        if (savedId) {
            try {
                const checkResp = await fetch(`/api/session/${savedId}`);
                if (checkResp.ok) {
                    const sessionData = await checkResp.json();
                    const resumableStatuses = ['analyzing', 'conversing', 'questioning', 'generating', 'selecting', 'final_analysis', 'final_questions'];
                    if (resumableStatuses.includes(sessionData.status)) {
                        console.log(`[Session] 恢复旧会话: ${savedId}, 状态: ${sessionData.status}`);
                        state.sessionId = savedId;
                        connectWebSocket(handleWebSocketMessage); // restore_context 会负责恢复页面状态
                        return;
                    }
                }
            } catch (e) {
                console.warn('[Session] 检查旧会话失败，将创建新会话:', e);
            }
            sessionStorage.removeItem('dapr_session_id');
        }

        // 创建新会话
        const response = await fetch('/api/session/create', { method: 'POST' });
        const data = await response.json();
        state.sessionId = data.session_id;
        sessionStorage.setItem('dapr_session_id', state.sessionId);

        connectWebSocket(handleWebSocketMessage);
        elements['guidance-text'].textContent = data.guidance_text;

        // 检查是否已同意（同一会话刷新场景）
        const consentGiven = sessionStorage.getItem('dapr_consent_given') === 'true';
        const savedSessionId = sessionStorage.getItem('dapr_session_id');
        if (consentGiven && savedSessionId === state.sessionId) {
            elements['consent-modal'].classList.remove('active');
            showPage('guidance-page');
        }

    } catch (error) {
        console.error('创建会话失败:', error);
        alert('系统初始化失败，请刷新页面重试');
    }
}

// 处理 WebSocket 消息
function handleWebSocketMessage(message) {
    if (message.type === 'ping') {
        if (state.ws && state.ws.readyState === WebSocket.OPEN) {
            state.ws.send(JSON.stringify({ type: 'pong', data: { ts: message?.data?.ts || null } }));
        }
        return;
    }

    if (message.type === 'connection_status') {
        // WebSocket 建立/重建确认，不需要额外处理
        return;
    }

    if (message.type === 'restore_context') {
        const restored = message?.data?.messages || [];
        restored.forEach((restoredMessage) => {
            const messageId = restoredMessage?._message_id;
            if (messageId) {
                state.wsMessageIds.add(messageId);
            }
            if (restoredMessage?.type && restoredMessage.type !== 'ping') {
                handleWebSocketMessage(restoredMessage);
            }
        });
        return;
    }

    const messageId = message._message_id;
    if (messageId) {
        if (state.wsMessageIds.has(messageId)) {
            return;
        }
        state.wsMessageIds.add(messageId);
    }

    switch (message.type) {
        case 'generated_images':
            showGeneratedImages(message.data);
            break;
        case 'final_questions':
            showFinalQuestions(message.data);
            break;
        case 'final_report':
            showFinalReport(message.data);
            break;
        case 'analysis_stream':
            // 流式分析进度
            handleStreamAnalysis(message.data);
            break;
        case 'chat_question':
            // 自主访谈：Agent 发送问题
            stopStreamDisplay();
            handleChatQuestion(message.data);
            break;
        case 'interview_complete':
            // 自主访谈结束，进入生图
            handleInterviewComplete(message.data);
            break;
        case 'agent_state':
            updateAgentProgress(message.data);
            break;
        case 'agent_error':
            showAgentError(message.data);
            break;
    }
}

// 处理流式分析消息
function handleStreamAnalysis(data) {
    const progressEl = document.getElementById('stream-progress');
    const outputEl = progressEl.querySelector('.stream-output');
    const speedEl = progressEl.querySelector('.stream-speed');
    const statusEl = progressEl.querySelector('.stream-status-text');
    
    if (data.status === 'started') {
        streamAnalysisState.isStreaming = true;
        streamAnalysisState.chunks = [];
        streamAnalysisState.startTime = Date.now();
        progressEl.style.display = 'block';
        outputEl.textContent = 'Agent开始分析您的绘画...';
        statusEl.textContent = 'Agent正在分析绘画特征...';
    } else if (data.status === 'chunk') {
        streamAnalysisState.chunks.push(data.chunk);
        
        // 更新显示（只显示最近500字符）
        const fullText = streamAnalysisState.chunks.join('');
        const displayText = fullText.slice(-500);
        outputEl.textContent = displayText;
        outputEl.scrollTop = outputEl.scrollHeight;
        
        // 更新速度
        if (data.speed) {
            speedEl.textContent = data.speed;
        }
        
        // 根据内容更新状态文本
        if (fullText.includes('绘画特征')) {
            statusEl.textContent = 'Agent正在分析绘画特征...';
        } else if (fullText.includes('表情')) {
            statusEl.textContent = 'Agent正在分析面部表情...';
        } else if (fullText.includes('时序')) {
            statusEl.textContent = 'Agent正在进行时序关联分析...';
        } else if (fullText.includes('问题')) {
            statusEl.textContent = 'Agent正在生成问题...';
        }
    } else if (data.status === 'complete') {
        statusEl.textContent = '分析完成！';
        speedEl.textContent = `总计: ${data.total_tokens} chars, ${data.total_time}`;
        streamAnalysisState.isStreaming = false;
    }
}

// 停止流式显示
function stopStreamDisplay() {
    const progressEl = document.getElementById('stream-progress');
    if (progressEl) {
        progressEl.style.display = 'none';
    }
    streamAnalysisState.isStreaming = false;
}

// ── Agent 执行状态更新（进度条 + 步骤文本）──
function updateAgentProgress(data) {
    const fillEl = document.getElementById('progress-fill');
    const statusEl = document.getElementById('generating-status');
    const subStatusEl = document.getElementById('generating-sub-status');
    if (!fillEl) return;

    const progress = data.progress || 0;
    const stepName = data.step_name || '';
    const stepStatus = data.step_status || '';

    // 更新进度条宽度
    fillEl.style.width = `${Math.round(progress * 100)}%`;

    // 根据步骤更新状态文本
    if (statusEl && subStatusEl) {
        const stepLabels = {
            'AnalyzeDrawingTool': '正在分析您的绘画...',
            'GenerateImageTool': '正在生成图像变体...',
            'AskFollowUpTool': '正在生成后续问题...',
            'GenerateReportTool': '正在生成最终报告...',
        };
        const label = stepLabels[stepName] || '正在处理...';
        statusEl.textContent = label;
        subStatusEl.textContent = stepStatus === 'running' ? '请稍候，AI 正在工作中...' : '处理完成';
    }
}

// ── Agent 执行错误提示 ──
function showAgentError(data) {
    const statusEl = document.getElementById('generating-status');
    const subStatusEl = document.getElementById('generating-sub-status');
    if (statusEl) {
        statusEl.textContent = '处理出错，请重试';
        statusEl.style.color = '#B8704B';
    }
    if (subStatusEl) {
        subStatusEl.textContent = data.message || data.error || '未知错误';
    }
    console.error('[Agent Error]', data);
}

// 窗口大小改变时调整画布
window.addEventListener('resize', () => {
    if (state.canvas) {
        resizeCanvas();
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
