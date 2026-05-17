/**
 * 最终问题与报告页面
 */

import { state } from '../config.js';
import { elements, showPage } from '../utils/dom.js';
import { escapeHtml } from '../utils/common.js';

// 显示最终问题
export function showFinalQuestions(data) {
    showPage('final-question-page');
    
    const container = elements['final-questions-container'];
    container.innerHTML = '';
    
    // 显示用户选择的图像信息
    if (data.selected_image) {
        const selectionInfo = document.createElement('div');
        selectionInfo.className = 'selection-info';
        selectionInfo.innerHTML = `
            <h3>您的选择</h3>
            <p><strong>${data.selected_image.name}</strong></p>
            <p>${data.selected_image.description}</p>
        `;
        container.appendChild(selectionInfo);
    }
    
    // 显示问题
    data.questions.forEach((question, index) => {
        const item = document.createElement('div');
        item.className = 'question-item';
        item.innerHTML = `
            <label>${question}</label>
            <textarea data-index="${index}" placeholder="请详细描述..."></textarea>
        `;
        container.appendChild(item);
    });
}

// 提交最终回答
export async function submitFinalAnswers() {
    const answers = [];
    document.querySelectorAll('#final-questions-container textarea').forEach(textarea => {
        answers.push(textarea.value);
    });
    
    // 显示加载页面
    showPage('final-report-page');
    
    await fetch(`/api/session/${state.sessionId}/final-answers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: state.sessionId, answers: answers })
    });
}

// 显示最终报告
export function showFinalReport(data) {
    showPage('result-page');
    
    const container = elements['report-content'];
    const analysis = data.final_analysis || data;
    
    // 向后兼容：新字段优先，旧字段兜底
    const creativeInsights = analysis.creative_insights || analysis.key_insights || [];
    const suggestedExplorations = analysis.suggested_explorations || analysis.recommendations || analysis.follow_up || [];
    
    container.innerHTML = `
        <div class="report-header">
            <h3>创作回顾</h3>
            <div class="report-summary-box">
                <p>${analysis.summary || '本次绘画探索已完成，感谢你的参与。'}</p>
            </div>
        </div>
        
        ${creativeInsights.length > 0 ? `
        <div class="report-section">
            <h3>💡 创作发现</h3>
            <ul class="insights-list">
                ${creativeInsights.map(insight => `
                    <li>
                        <span class="insight-bullet">●</span>
                        <span class="insight-text">${insight}</span>
                    </li>
                `).join('')}
            </ul>
        </div>
        ` : ''}
        
        ${analysis.selection_interpretation ? `
        <div class="report-section">
            <h3>🎯 选择背后的感受</h3>
            <p class="selection-analysis">${analysis.selection_interpretation}</p>
        </div>
        ` : ''}
        
        ${suggestedExplorations.length > 0 ? `
        <div class="report-section">
            <h3>🌟 建议探索方向</h3>
            <div class="recommendations-list">
                ${suggestedExplorations.map((item, i) => `
                    <div class="recommendation-item">
                        <span class="rec-number">${i + 1}</span>
                        <p>${item}</p>
                    </div>
                `).join('')}
            </div>
        </div>
        ` : ''}
        
        <div class="report-footer">
            <p class="disclaimer">本创作回顾基于 AI 观察生成，仅供艺术探索参考，不构成任何医疗或心理诊断。</p>
        </div>
    `;
}
