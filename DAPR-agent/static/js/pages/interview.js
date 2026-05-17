/**
 * 自主访谈页面：聊天交互
 */

import { state } from '../config.js';
import { elements, showPage } from '../utils/dom.js';
import { escapeHtml } from '../utils/common.js';

export function handleChatQuestion(data) {
    showPage('questioning-page');
    
    const messagesEl = elements['chat-messages'];
    const inputEl = elements['chat-input'];
    const sendBtn = elements['chat-send-btn'];
    const typingEl = elements['chat-typing'];
    const indicatorEl = elements['chat-turn-indicator'];
    
    // 隐藏 typing 指示器
    typingEl.style.display = 'none';
    
    // 添加 Agent 消息气泡
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble agent';
    bubble.innerHTML = `
        <div class="bubble-role">AI 伙伴</div>
        <div class="bubble-content">${escapeHtml(data.question)}</div>
    `;
    messagesEl.appendChild(bubble);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    
    // 更新轮数指示器
    indicatorEl.textContent = `第 ${data.turn || 1} / ${data.max_turns || 8} 轮`;
    
    // 启用输入
    inputEl.disabled = false;
    sendBtn.disabled = false;
    inputEl.focus();
}

export function submitChatAnswer() {
    const inputEl = elements['chat-input'];
    const sendBtn = elements['chat-send-btn'];
    const messagesEl = elements['chat-messages'];
    const typingEl = elements['chat-typing'];
    
    const answer = inputEl.value.trim();
    if (!answer) return;
    
    // 添加用户消息气泡
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble user';
    bubble.innerHTML = `
        <div class="bubble-role">你</div>
        <div class="bubble-content">${escapeHtml(answer)}</div>
    `;
    messagesEl.appendChild(bubble);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    
    // 清空输入并禁用
    inputEl.value = '';
    inputEl.disabled = true;
    sendBtn.disabled = true;
    
    // 显示 typing 指示器
    typingEl.style.display = 'flex';
    
    // 发送到后端
    fetch(`/api/session/${state.sessionId}/chat-answer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: state.sessionId, answer: answer })
    }).catch(e => {
        console.error('[Chat] 发送失败:', e);
        typingEl.style.display = 'none';
        inputEl.disabled = false;
        sendBtn.disabled = false;
    });
}

export function handleInterviewComplete(data) {
    const messagesEl = elements['chat-messages'];
    const typingEl = elements['chat-typing'];
    const inputEl = elements['chat-input'];
    const sendBtn = elements['chat-send-btn'];
    const skipBtn = elements['skip-interview-btn'];
    
    typingEl.style.display = 'none';
    inputEl.disabled = true;
    sendBtn.disabled = true;
    skipBtn.style.display = 'none';
    
    // 添加系统消息
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble agent';
    bubble.style.background = '#e8f5e9';
    bubble.style.borderColor = '#81c784';
    bubble.innerHTML = `
        <div class="bubble-role">系统</div>
        <div class="bubble-content">对话完成（共 ${data.total_turns || 0} 轮），正在为您生成图像变体...</div>
    `;
    messagesEl.appendChild(bubble);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    
    // 延迟后跳转到生图页面
    setTimeout(() => {
        showPage('generating-page');
    }, 2000);
}

export function skipInterview() {
    if (!confirm('确定要跳过对话吗？系统将根据绘画直接生成图像。')) return;
    
    const inputEl = elements['chat-input'];
    const sendBtn = elements['chat-send-btn'];
    const typingEl = elements['chat-typing'];
    inputEl.disabled = true;
    sendBtn.disabled = true;
    typingEl.style.display = 'flex';
    typingEl.textContent = '准备生成图像...';
    
    fetch(`/api/session/${state.sessionId}/skip-interview`, {
        method: 'POST'
    }).catch(e => {
        console.error('[Skip] 失败:', e);
        typingEl.style.display = 'none';
        inputEl.disabled = false;
        sendBtn.disabled = false;
    });
}
