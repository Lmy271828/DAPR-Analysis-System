/**
 * DOM 工具函数
 */

import { elements } from '../config.js';

// 初始化DOM元素引用
export function initElements() {
    const ids = [
        'consent-modal', 'consent-checkbox', 'consent-btn',
        'guidance-page', 'permission-page', 'drawing-page', 'analyzing-page',
        'questioning-page', 'generating-page', 'selecting-page', 'image-preview-page', 'final-question-page', 
        'final-report-page', 'result-page',
        'guidance-text', 'start-btn',
        'camera-status', 'screen-status', 'request-camera-btn', 'request-screen-btn', 'enter-drawing-btn',
        'webcam-video', 'recording-indicator',
        'toolbar', 'canvas-container', 'drawing-canvas', 'canvas-hint', 'start-drawing-overlay',
        'start-recording-btn', 'rotate-btn', 'pen-btn', 'eraser-btn', 'clear-btn', 'brush-size', 'submit-drawing-btn',
        // 自主访谈聊天元素
        'chat-messages', 'chat-input', 'chat-send-btn', 'chat-typing', 'chat-turn-indicator', 'skip-interview-btn',
        'images-grid',
        'final-questions-container', 'submit-final-btn',
        'report-content', 'restart-btn',
        // 预览页面元素
        'preview-image', 'preview-actions', 'cancel-preview-btn', 'confirm-preview-btn'
    ];
    
    ids.forEach(id => {
        elements[id] = document.getElementById(id);
    });
}

// 显示页面
export function showPage(pageId) {
    // 如果离开预览页面，清空图像防止在其他页面显示
    const currentPreview = document.getElementById('image-preview-page');
    if (currentPreview && currentPreview.classList.contains('active') && pageId !== 'image-preview-page') {
        const previewImg = document.getElementById('preview-image');
        if (previewImg) {
            previewImg.src = '';
        }
    }
    
    document.querySelectorAll('.page').forEach(page => {
        page.classList.remove('active');
    });
    elements[pageId].classList.add('active');
}
