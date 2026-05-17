import { state } from '../state.js';
import { fetchSessionDetail } from '../services/api.js';

export function selectSession(sessionId) {
    state.selectedSession = sessionId;

    document.querySelectorAll('.session-item').forEach(item => {
        item.classList.toggle('active', item.dataset.id === sessionId);
    });

    document.getElementById('detail-panel').classList.add('active');
    loadSessionDetail(sessionId);
}

export async function loadSessionDetail(sessionId) {
    try {
        const session = await fetchSessionDetail(sessionId);
        renderSessionDetail(session);
    } catch (error) {
        console.error('加载会话详情失败:', error);
    }
}

export function renderSessionDetail(session) {
    const container = document.getElementById('detail-content');

    container.innerHTML = `
        <div class="detail-section">
            <h3>基本信息</h3>
            <div class="detail-item">
                <div class="detail-label">会话ID</div>
                <div class="detail-value">${session.id}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">状态</div>
                <div class="detail-value">${session.status}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">创建时间</div>
                <div class="detail-value">${new Date(session.created_at).toLocaleString()}</div>
            </div>
            ${session.age_group ? `
            <div class="detail-item">
                <div class="detail-label">年龄段</div>
                <div class="detail-value">${session.age_group}</div>
            </div>
            ` : ''}
            ${session.gender ? `
            <div class="detail-item">
                <div class="detail-label">性别</div>
                <div class="detail-value">${session.gender}</div>
            </div>
            ` : ''}
        </div>
        
        ${session.drawing_image ? `
        <div class="detail-section">
            <h3>绘画作品</h3>
            <div class="detail-item">
                <img src="/api/image/${session.id}/drawing.png" style="max-width: 100%; border-radius: 4px;">
            </div>
        </div>
        ` : ''}
        
        ${session.initial_analysis ? `
        <div class="detail-section">
            <h3>初步分析</h3>
            <div class="detail-item">
                <div class="detail-label">分析摘要</div>
                <div class="detail-value">${session.initial_analysis.analysis_summary || '无'}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">猜想</div>
                <div class="detail-value">
                    ${(session.hypotheses || []).map(h => `• ${h.description} (${h.confidence})`).join('<br>')}
                </div>
            </div>
        </div>
        ` : ''}
        
        ${session.conversation_history && session.conversation_history.length > 0 ? `
        <div class="detail-section">
            <h3>自主访谈对话 (${session.conversation_history.length} 轮)</h3>
            <div class="interview-chat-history">
                ${session.conversation_history.map(msg => `
                <div class="interview-msg ${msg.role}">
                    <div class="interview-msg-role">${msg.role === 'agent' ? 'Agent' : '用户'}</div>
                    <div class="interview-msg-content">${msg.content}</div>
                </div>
                `).join('')}
            </div>
        </div>
        ` : ''}
        
        ${session.user_answers && session.user_answers.length > 0 && (!session.conversation_history || session.conversation_history.length === 0) ? `
        <div class="detail-section">
            <h3>用户回答</h3>
            ${session.user_answers.map((ans, i) => `
            <div class="detail-item">
                <div class="detail-label">问题 ${i + 1}</div>
                <div class="detail-value">${ans}</div>
            </div>
            `).join('')}
        </div>
        ` : ''}
        
        ${session.generated_images && session.generated_images.length > 0 ? `
        <div class="detail-section">
            <h3>生成的图像</h3>
            ${session.generated_images.map(img => `
            <div class="detail-item">
                <div class="detail-label">${img.name}</div>
                <img src="${img.url || img.filepath}" style="max-width: 100%; border-radius: 4px; margin-top: 8px;">
                <div style="margin-top: 8px; font-size: 0.85rem; color: #888;">${img.description}</div>
            </div>
            `).join('')}
        </div>
        ` : ''}
        
        ${session.final_analysis ? `
        <div class="detail-section">
            <h3>创作回顾</h3>
            <div class="detail-item">
                <div class="detail-label">整体感受</div>
                <div class="detail-value" style="white-space: pre-wrap; line-height: 1.6;">${session.final_analysis.summary || '无'}</div>
            </div>
            ${(session.final_analysis.creative_insights && session.final_analysis.creative_insights.length > 0) ? `
            <div class="detail-item">
                <div class="detail-label">创作洞察</div>
                <div class="detail-value">
                    <ul style="margin: 0; padding-left: 18px;">
                        ${session.final_analysis.creative_insights.map(i => `<li style="margin: 6px 0; white-space: pre-wrap; line-height: 1.5;">${i}</li>`).join('')}
                    </ul>
                </div>
            </div>
            ` : ''}
            ${(session.final_analysis.suggested_explorations && session.final_analysis.suggested_explorations.length > 0) ? `
            <div class="detail-item">
                <div class="detail-label">探索建议</div>
                <div class="detail-value">
                    <ul style="margin: 0; padding-left: 18px;">
                        ${session.final_analysis.suggested_explorations.map(i => `<li style="margin: 6px 0; white-space: pre-wrap; line-height: 1.5;">${i}</li>`).join('')}
                    </ul>
                </div>
            </div>
            ` : ''}
        </div>
        ` : ''}
    `;
}
