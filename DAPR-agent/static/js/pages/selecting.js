/**
 * 图像选择页面
 */

import { state } from '../config.js';
import { elements, showPage } from '../utils/dom.js';

let currentPreviewIndex = -1;

export function showGeneratedImages(data) {
    showPage('selecting-page');
    
    const grid = elements['images-grid'];
    grid.innerHTML = '';
    state.generatedImages = data.images;
    
    // 重置选择行为追踪
    state.selectionBehavior = {
        viewOrder: [],
        viewStartTime: null,
        viewDurations: {},
        hoverCount: {},
        finalSelection: null,
        hesitationIndicators: []
    };
    
    data.images.forEach((image, index) => {
        const card = document.createElement('div');
        card.className = 'image-option';
        card.dataset.id = image.id;
        card.dataset.index = index;
        card.innerHTML = `
            <img src="${image.url}" alt="${image.name}" loading="lazy">
            <div class="image-option-info">
                <h4>${image.name}</h4>
                <p>${image.description}</p>
            </div>
        `;
        card.addEventListener('click', () => previewImage(index));
        
        // 追踪悬停行为
        card.addEventListener('mouseenter', () => {
            const imgId = image.id;
            state.selectionBehavior.hoverCount[imgId] = (state.selectionBehavior.hoverCount[imgId] || 0) + 1;
        });
        
        grid.appendChild(card);
    });
}

// 预览图像（按钮3秒内从虚化渐变到实体）
export function previewImage(index) {
    currentPreviewIndex = index;
    const image = state.generatedImages[index];
    
    // 记录查看行为
    const imgId = image.id;
    if (!state.selectionBehavior.viewDurations[imgId]) {
        state.selectionBehavior.viewOrder.push(imgId);
    }
    state.selectionBehavior.viewStartTime = Date.now();
    
    // 显示预览页面
    elements['preview-image'].src = image.url;
    
    // 重置按钮状态（虚化、不可交互）
    const cancelBtn = elements['cancel-preview-btn'];
    const confirmBtn = elements['confirm-preview-btn'];
    cancelBtn.disabled = true;
    confirmBtn.disabled = true;
    cancelBtn.classList.remove('enabled');
    confirmBtn.classList.remove('enabled');
    
    showPage('image-preview-page');
    
    // 3秒内按钮从虚化渐变到实体
    const duration = 3000; // 3秒
    const startTime = Date.now();
    
    const fadeIn = () => {
        const elapsed = Date.now() - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const opacity = 0.3 + (progress * 0.7); // 从0.3到1.0
        
        cancelBtn.style.opacity = opacity;
        confirmBtn.style.opacity = opacity;
        
        if (progress < 1) {
            requestAnimationFrame(fadeIn);
        } else {
            // 3秒后启用按钮交互
            cancelBtn.disabled = false;
            confirmBtn.disabled = false;
            cancelBtn.classList.add('enabled');
            confirmBtn.classList.add('enabled');
            cancelBtn.style.opacity = '';
            confirmBtn.style.opacity = '';
        }
    };
    
    requestAnimationFrame(fadeIn);
}

// 取消预览
export function cancelPreview() {
    // 记录停留时长
    if (state.selectionBehavior.viewStartTime) {
        const image = state.generatedImages[currentPreviewIndex];
        const duration = Date.now() - state.selectionBehavior.viewStartTime;
        const imgId = image.id;
        state.selectionBehavior.viewDurations[imgId] = (state.selectionBehavior.viewDurations[imgId] || 0) + duration;
        state.selectionBehavior.viewStartTime = null;
        
        // 检测犹豫行为（停留时间超过5秒但取消）
        if (duration > 5000) {
            state.selectionBehavior.hesitationIndicators.push({
                type: 'long_view_but_cancel',
                imageId: imgId,
                duration: duration,
                timestamp: new Date().toISOString()
            });
        }
    }
    
    showPage('selecting-page');
}

// 确认选择
export async function confirmSelection() {
    const image = state.generatedImages[currentPreviewIndex];
    
    // 记录最终选择和停留时长
    if (state.selectionBehavior.viewStartTime) {
        const duration = Date.now() - state.selectionBehavior.viewStartTime;
        state.selectionBehavior.viewDurations[image.id] = (state.selectionBehavior.viewDurations[image.id] || 0) + duration;
    }
    
    state.selectionBehavior.finalSelection = {
        imageId: image.id,
        imageName: image.name,
        viewOrder: state.selectionBehavior.viewOrder.indexOf(image.id) + 1, // 第几个被查看
        totalViews: state.selectionBehavior.viewOrder.length
    };
    
    // 分析犹豫行为
    analyzeHesitation();
    
    console.log('[Select] 选择图像:', image);
    console.log('[Select] 选择行为:', state.selectionBehavior);
    
    try {
        const response = await fetch(`/api/session/${state.sessionId}/select`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                session_id: state.sessionId, 
                image_id: String(image.id),
                selection_behavior: state.selectionBehavior
            })
        });
        
        if (!response.ok) {
            const error = await response.text();
            console.error('[Select] 失败:', error);
            alert('提交失败，请重试');
            return;
        }
        
        console.log('[Select] 成功');
    } catch (error) {
        console.error('[Select] 错误:', error);
        alert('提交失败，请重试');
    }
}

// 分析犹豫行为
function analyzeHesitation() {
    const behavior = state.selectionBehavior;
    
    // 多次查看同一张图
    Object.entries(behavior.viewDurations).forEach(([imgId, duration]) => {
        if (duration > 8000 && imgId !== behavior.finalSelection?.imageId) {
            behavior.hesitationIndicators.push({
                type: 'long_consideration_rejected',
                imageId: imgId,
                duration: duration,
                description: '对该图像长时间考虑但最终未选择'
            });
        }
    });
    
    // 查看多张图片后才决定
    if (behavior.viewOrder.length > 2) {
        behavior.hesitationIndicators.push({
            type: 'multiple_comparisons',
            viewCount: behavior.viewOrder.length,
            description: `查看了${behavior.viewOrder.length}张图像进行对比`
        });
    }
    
    // 最终选择不是第一个查看的
    if (behavior.finalSelection && behavior.finalSelection.viewOrder > 1) {
        behavior.hesitationIndicators.push({
            type: 'not_first_choice',
            firstViewed: behavior.viewOrder[0],
            finalChoice: behavior.finalSelection.imageId,
            description: '最终选择并非首次查看的图像'
        });
    }
}
