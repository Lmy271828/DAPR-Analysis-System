/**
 * 绘画页面：画布操作、录制、权限、提交
 */

import { state, CONFIG } from '../config.js';
import { elements, showPage } from '../utils/dom.js';
import { blobToBase64 } from '../utils/common.js';

// 初始化画布
export function initCanvas() {
    const canvas = elements['drawing-canvas'];
    const container = elements['canvas-container'];
    
    // 设置画布尺寸
    canvas.width = CONFIG.CANVAS_WIDTH;
    canvas.height = CONFIG.CANVAS_HEIGHT;
    
    // 设置显示尺寸
    resizeCanvas();
    
    state.canvas = canvas;
    state.ctx = canvas.getContext('2d');
    
    // 设置画布背景为白色
    state.ctx.fillStyle = 'white';
    state.ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    // 绑定绘画事件
    canvas.addEventListener('mousedown', startDrawing);
    canvas.addEventListener('mousemove', draw);
    canvas.addEventListener('mouseup', stopDrawing);
    canvas.addEventListener('mouseout', stopDrawing);
    
    // 触摸事件支持
    canvas.addEventListener('touchstart', handleTouch);
    canvas.addEventListener('touchmove', handleTouch);
    canvas.addEventListener('touchend', stopDrawing);
}

// 调整画布大小以适应容器
export function resizeCanvas() {
    const canvas = elements['drawing-canvas'];
    const container = elements['canvas-container'];
    const containerRect = container.getBoundingClientRect();
    
    // 计算缩放比例
    const scaleX = (containerRect.width - 80) / CONFIG.CANVAS_WIDTH;
    const scaleY = (containerRect.height - 80) / CONFIG.CANVAS_HEIGHT;
    const scale = Math.min(scaleX, scaleY, 1);
    
    canvas.style.width = `${CONFIG.CANVAS_WIDTH * scale}px`;
    canvas.style.height = `${CONFIG.CANVAS_HEIGHT * scale}px`;
}

// 绘画功能
function getCoordinates(e) {
    const canvas = state.canvas;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    
    return {
        x: (e.clientX - rect.left) * scaleX,
        y: (e.clientY - rect.top) * scaleY
    };
}

function startDrawing(e) {
    state.isDrawing = true;
    const coords = getCoordinates(e);
    state.ctx.beginPath();
    state.ctx.moveTo(coords.x, coords.y);
}

function draw(e) {
    if (!state.isDrawing) return;
    
    const coords = getCoordinates(e);
    
    state.ctx.lineWidth = state.brushSize;
    state.ctx.lineCap = 'round';
    state.ctx.lineJoin = 'round';
    
    if (state.currentTool === 'pen') {
        state.ctx.strokeStyle = '#000000';
        state.ctx.globalCompositeOperation = 'source-over';
    } else {
        // 橡皮擦：使用白色绘制（与背景一致），避免产生透明区域
        state.ctx.strokeStyle = '#ffffff';
        state.ctx.globalCompositeOperation = 'source-over';
    }
    
    state.ctx.lineTo(coords.x, coords.y);
    state.ctx.stroke();
}

function stopDrawing() {
    state.isDrawing = false;
    state.ctx.beginPath();
}

function handleTouch(e) {
    e.preventDefault();
    const touch = e.touches[0];
    const mouseEvent = new MouseEvent(e.type === 'touchstart' ? 'mousedown' : 
                                       e.type === 'touchmove' ? 'mousemove' : 'mouseup', {
        clientX: touch.clientX,
        clientY: touch.clientY
    });
    state.canvas.dispatchEvent(mouseEvent);
}

// 工具功能
export function setTool(tool) {
    state.currentTool = tool;
    elements['pen-btn'].classList.toggle('active', tool === 'pen');
    elements['eraser-btn'].classList.toggle('active', tool === 'eraser');
}

export function clearCanvas() {
    if (confirm('确定要清空画布吗？')) {
        state.ctx.fillStyle = 'white';
        state.ctx.fillRect(0, 0, state.canvas.width, state.canvas.height);
    }
}

export function rotateCanvas() {
    state.canvasRotation = (state.canvasRotation + 90) % 360;
    state.canvas.style.transform = `rotate(${state.canvasRotation}deg)`;
}

// 请求摄像头权限
export async function requestCameraPermission() {
    try {
        state.webcamStream = await navigator.mediaDevices.getUserMedia({
            video: { width: 640, height: 480 },
            audio: false
        });
        
        elements['webcam-video'].srcObject = state.webcamStream;
        
        elements['camera-status'].textContent = '已授权';
        elements['camera-status'].className = 'status granted';
        
        // 监听摄像头断开（重要：录制过程中可能被中断）
        state.webcamStream.getVideoTracks()[0].onended = () => {
            console.warn('[摄像头] 摄像头流已断开');
            elements['camera-status'].textContent = '已断开';
            elements['camera-status'].className = 'status denied';
            state.webcamStream = null;
            
            // 如果正在录制，警告用户
            if (state.mediaRecorder.webcam && state.mediaRecorder.webcam.state === 'recording') {
                console.error('[摄像头] 录制过程中摄像头断开！');
                alert('警告：摄像头在录制过程中断开，录制可能不完整');
            }
            
            checkPermissions();
        };
        
        checkPermissions();
    } catch (error) {
        console.error('摄像头权限被拒绝:', error);
        elements['camera-status'].textContent = '被拒绝';
        elements['camera-status'].className = 'status denied';
        alert('请允许使用摄像头，这是分析过程的重要部分');
    }
}

// 请求屏幕录制权限
export async function requestScreenPermission() {
    // 不再请求系统录屏权限，改为记录画布变化
    state.canvasRecordingEnabled = true;
    elements['screen-status'].textContent = '已启用（记录画布变化）';
    elements['screen-status'].className = 'status granted';
    checkPermissions();
}

// 检查权限状态
export function checkPermissions() {
    const hasCamera = state.webcamStream !== null;
    const hasScreen = state.canvasRecordingEnabled;
    
    elements['enter-drawing-btn'].disabled = !(hasCamera && hasScreen);
}

// 开始录制
export async function startRecording() {
    if (!state.webcamStream || !state.canvasRecordingEnabled) {
        alert('请先授权摄像头并启用画布录制');
        return;
    }
    
    // 初始化画布
    initCanvas();
    
    // 隐藏覆盖层
    elements['start-drawing-overlay'].classList.add('hidden');
    
    // 显示工具栏和录制指示器
    elements['toolbar'].style.display = 'flex';
    elements['canvas-hint'].style.display = 'none';
    elements['recording-indicator'].classList.add('active');
    
    // 清空之前的录制数据
    state.recordedChunks.webcam = [];
    state.recordedChunks.screen = [];
    
    // 启动摄像头录制
    try {
        state.mediaRecorder.webcam = new MediaRecorder(state.webcamStream, {
            mimeType: 'video/webm;codecs=vp9'
        });
        state.mediaRecorder.webcam.ondataavailable = (e) => {
            if (e.data.size > 0) {
                state.recordedChunks.webcam.push(e.data);
                console.log(`[录制] 摄像头数据块: ${e.data.size} bytes, 总计: ${state.recordedChunks.webcam.length} 块`);
            }
        };
        state.mediaRecorder.webcam.onerror = (e) => {
            console.error('[录制] 摄像头录制错误:', e);
            alert('摄像头录制出现问题，请刷新页面重试');
        };
        state.mediaRecorder.webcam.onstop = () => {
            console.log(`[录制] 摄像头录制停止，共 ${state.recordedChunks.webcam.length} 个数据块`);
        };
        state.mediaRecorder.webcam.start(1000);
        console.log('[录制] 摄像头录制已启动');
    } catch (e) {
        console.error('[录制] 摄像头录制启动失败:', e);
        alert('摄像头录制启动失败');
        return;
    }
    
    // 启动画布录制（替代屏幕录制）
    try {
        // 记录画布内容变化（包含绘制过程）
        state.canvasStream = state.canvas.captureStream(15);
        state.mediaRecorder.screen = new MediaRecorder(state.canvasStream, {
            mimeType: 'video/webm;codecs=vp9'
        });
        state.mediaRecorder.screen.ondataavailable = (e) => {
            if (e.data.size > 0) {
                state.recordedChunks.screen.push(e.data);
                console.log(`[录制] 屏幕数据块: ${e.data.size} bytes, 总计: ${state.recordedChunks.screen.length} 块`);
            }
        };
        state.mediaRecorder.screen.onerror = (e) => {
            console.error('[录制] 屏幕录制错误:', e);
        };
        state.mediaRecorder.screen.onstop = () => {
            console.log(`[录制] 屏幕录制停止，共 ${state.recordedChunks.screen.length} 个数据块`);
        };
        state.mediaRecorder.screen.start(1000);
        console.log('[录制] 画布录制已启动');
    } catch (e) {
        console.error('[录制] 画布录制启动失败:', e);
        alert('画布录制启动失败');
        return;
    }
}

// 同时停止多个录制器并等待完成
export function stopRecordersSimultaneously() {
    return new Promise((resolve) => {
        const recorders = [];
        let stoppedCount = 0;
        
        // 检查并准备要停止的录制器
        if (state.mediaRecorder.webcam && state.mediaRecorder.webcam.state === 'recording') {
            recorders.push({ recorder: state.mediaRecorder.webcam, name: 'webcam' });
        } else {
            console.warn(`[录制] 摄像头录制器状态: ${state.mediaRecorder.webcam?.state || '未初始化'}`);
        }
        
        if (state.mediaRecorder.screen && state.mediaRecorder.screen.state === 'recording') {
            recorders.push({ recorder: state.mediaRecorder.screen, name: 'screen' });
        } else {
            console.warn(`[录制] 屏幕录制器状态: ${state.mediaRecorder.screen?.state || '未初始化'}`);
        }
        
        if (recorders.length === 0) {
            console.warn('[录制] 没有正在运行的录制器');
            resolve();
            return;
        }
        
        console.log(`[录制] 准备停止 ${recorders.length} 个录制器`);
        
        const checkAllStopped = () => {
            stoppedCount++;
            console.log(`[录制] 已停止 ${stoppedCount}/${recorders.length} 个录制器`);
            if (stoppedCount >= recorders.length) {
                // 额外等待一小段时间确保数据写入
                setTimeout(() => {
                    console.log(`[录制] 所有录制器已停止，摄像头数据块: ${state.recordedChunks.webcam.length}, 屏幕数据块: ${state.recordedChunks.screen.length}`);
                    if (state.canvasStream) {
                        state.canvasStream.getTracks().forEach(track => track.stop());
                        state.canvasStream = null;
                    }
                    resolve();
                }, 200);
            }
        };
        
        // 为每个录制器添加 onstop 监听器
        recorders.forEach(({ recorder, name }) => {
            const originalOnStop = recorder.onstop;
            recorder.onstop = (e) => {
                console.log(`[录制] ${name} 录制器触发了 onstop 事件`);
                if (originalOnStop) originalOnStop(e);
                checkAllStopped();
            };
        });
        
        // 同时停止所有录制器（时间戳尽可能接近）
        recorders.forEach(({ recorder, name }) => {
            try {
                recorder.stop();
                console.log(`[录制] ${name} 录制器 stop() 已调用`);
            } catch (e) {
                console.error(`[录制] ${name} 录制器 stop() 失败:`, e);
                checkAllStopped(); // 即使失败也算作已停止
            }
        });
    });
}

// 提交绘画
export async function submitDrawing() {
    console.log('[提交] 开始停止录制...');
    // 同时停止录制并等待完成
    await stopRecordersSimultaneously();
    console.log('[提交] 录制已停止');
    
    elements['recording-indicator'].classList.remove('active');
    
    // 获取画布数据
    const drawingData = state.canvas.toDataURL('image/png');
    
    // 创建视频 Blob
    const webcamBlob = new Blob(state.recordedChunks.webcam, { type: 'video/webm' });
    const screenBlob = new Blob(state.recordedChunks.screen, { type: 'video/webm' });
    
    console.log(`[提交] 摄像头视频: ${webcamBlob.size} bytes (${state.recordedChunks.webcam.length} 块), 屏幕视频: ${screenBlob.size} bytes (${state.recordedChunks.screen.length} 块)`);
    
    // 检查视频大小差异是否过大（超过50%）
    const webcamDuration = state.recordedChunks.webcam.length;
    const screenDuration = state.recordedChunks.screen.length;
    if (webcamDuration > 0 && screenDuration > 0) {
        const ratio = Math.abs(webcamDuration - screenDuration) / Math.max(webcamDuration, screenDuration);
        if (ratio > 0.5) {
            console.warn(`[提交] 警告：两个视频数据块数量差异过大 (${webcamDuration} vs ${screenDuration})`);
        }
    }
    
    // 检查是否有空视频
    if (webcamBlob.size < 1000) {
        console.error('[提交] 摄像头视频数据过小，可能录制失败');
        alert('摄像头视频录制似乎出现问题，请检查摄像头权限后重试');
        return;
    }
    if (screenBlob.size < 1000) {
        console.error('[提交] 屏幕视频数据过小，可能录制失败');
        alert('屏幕录制似乎出现问题，请重试');
        return;
    }
    
    // 转换为 base64
    console.log('[提交] 开始转换为 base64...');
    const [webcamBase64, screenBase64] = await Promise.all([
        blobToBase64(webcamBlob),
        blobToBase64(screenBlob)
    ]);
    console.log('[提交] base64 转换完成');
    
    // 提交数据
    showPage('analyzing-page');
    
    try {
        console.log('[提交] 发送数据到服务器...');
        const response = await fetch(`/api/session/${state.sessionId}/drawing`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                drawing_data: drawingData,
                webcam_video: webcamBase64,
                canvas_video: screenBase64
            })
        });
        
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`提交失败: ${errorText}`);
        }
        
        console.log('[提交] 数据提交成功，启动分析...');
        // 启动分析
        await fetch(`/api/session/${state.sessionId}/analyze`, { method: 'POST' });
        console.log('[提交] 分析已启动');
        
    } catch (error) {
        console.error('提交绘画失败:', error);
        alert('提交失败，请重试: ' + error.message);
    }
}
