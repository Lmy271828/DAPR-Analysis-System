/**
 * DAPR Agent 前端应用
 */

// 全局状态
const state = {
    sessionId: null,
    ws: null,
    webcamStream: null,
    screenStream: null,
    mediaRecorder: {
        webcam: null,
        screen: null
    },
    recordedChunks: {
        webcam: [],
        screen: []
    },
    canvas: null,
    ctx: null,
    isDrawing: false,
    currentTool: 'pen',
    brushSize: 3,
    canvasRotation: 0,
    generatedImages: [],
    // 选择行为追踪
    selectionBehavior: {
        viewOrder: [],          // 查看图像的顺序
        viewStartTime: null,    // 当前查看开始时间
        viewDurations: {},      // 每张图像的停留时长（毫秒）
        hoverCount: {},         // 每张图像的悬停次数
        finalSelection: null,   // 最终选择
        hesitationIndicators: [] // 犹豫行为指标
    }
};

// 配置
const CONFIG = {
    API_BASE: '',
    WS_URL: () => `ws://${window.location.host}/ws/subject/${state.sessionId}`,
    CANVAS_WIDTH: 850,
    CANVAS_HEIGHT: 1100
};

// DOM 元素
const elements = {};

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    initElements();
    bindEvents();
    createSession();
});

// 初始化DOM元素引用
function initElements() {
    const ids = [
        'guidance-page', 'permission-page', 'drawing-page', 'analyzing-page',
        'questioning-page', 'generating-page', 'selecting-page', 'image-preview-page', 'final-question-page', 
        'final-report-page', 'result-page',
        'guidance-text', 'start-btn',
        'camera-status', 'screen-status', 'request-camera-btn', 'request-screen-btn', 'enter-drawing-btn',
        'webcam-video', 'screen-video', 'recording-indicator',
        'toolbar', 'canvas-container', 'drawing-canvas', 'canvas-hint', 'start-drawing-overlay',
        'start-recording-btn', 'rotate-btn', 'pen-btn', 'eraser-btn', 'clear-btn', 'brush-size', 'submit-drawing-btn',
        'questions-container', 'age-select', 'gender-select', 'submit-answers-btn',
        'images-grid', 'confirm-selection-btn',
        'final-questions-container', 'submit-final-btn',
        'report-content', 'restart-btn',
        // 预览页面元素
        'preview-image', 'preview-actions', 'cancel-preview-btn', 'confirm-preview-btn'
    ];
    
    ids.forEach(id => {
        elements[id] = document.getElementById(id);
    });
}

// 绑定事件
function bindEvents() {
    // 引导页
    elements['start-btn'].addEventListener('click', () => showPage('permission-page'));
    
    // 权限页
    elements['request-camera-btn'].addEventListener('click', requestCameraPermission);
    elements['request-screen-btn'].addEventListener('click', requestScreenPermission);
    elements['enter-drawing-btn'].addEventListener('click', () => showPage('drawing-page'));
    
    // 绘画页
    elements['start-recording-btn'].addEventListener('click', startRecording);
    elements['submit-drawing-btn'].addEventListener('click', submitDrawing);
    
    // 工具栏
    elements['rotate-btn'].addEventListener('click', rotateCanvas);
    elements['pen-btn'].addEventListener('click', () => setTool('pen'));
    elements['eraser-btn'].addEventListener('click', () => setTool('eraser'));
    elements['clear-btn'].addEventListener('click', clearCanvas);
    elements['brush-size'].addEventListener('input', (e) => {
        state.brushSize = parseInt(e.target.value);
    });
    
    // 问答页
    elements['submit-answers-btn'].addEventListener('click', submitAnswers);
    
    // 选择页
    elements['cancel-preview-btn'].addEventListener('click', cancelPreview);
    elements['confirm-preview-btn'].addEventListener('click', confirmSelection);
    
    // 最终问题页
    elements['submit-final-btn'].addEventListener('click', submitFinalAnswers);
    
    // 结果页
    elements['restart-btn'].addEventListener('click', () => location.reload());
}

// 显示页面
function showPage(pageId) {
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

// 创建会话
async function createSession() {
    try {
        const response = await fetch('/api/session/create', { method: 'POST' });
        const data = await response.json();
        state.sessionId = data.session_id;
        
        // 连接 WebSocket
        connectWebSocket();
        
        // 显示引导文本
        elements['guidance-text'].textContent = data.guidance_text;
        
    } catch (error) {
        console.error('创建会话失败:', error);
        alert('系统初始化失败，请刷新页面重试');
    }
}

// 连接 WebSocket
function connectWebSocket() {
    const ws = new WebSocket(CONFIG.WS_URL());
    state.ws = ws;
    
    ws.onopen = () => {
        console.log('WebSocket 已连接');
    };
    
    ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        handleWebSocketMessage(message);
    };
    
    ws.onclose = () => {
        console.log('WebSocket 已断开');
        // 尝试重连
        setTimeout(connectWebSocket, 3000);
    };
    
    ws.onerror = (error) => {
        console.error('WebSocket 错误:', error);
    };
}

// 流式分析状态
const streamAnalysisState = {
    isStreaming: false,
    chunks: [],
    startTime: null
};

// 处理 WebSocket 消息
function handleWebSocketMessage(message) {
    switch (message.type) {
        case 'questions':
            // 分析完成，停止流式显示
            stopStreamDisplay();
            showQuestions(message.data);
            break;
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

// 请求摄像头权限
async function requestCameraPermission() {
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
async function requestScreenPermission() {
    try {
        state.screenStream = await navigator.mediaDevices.getDisplayMedia({
            video: { cursor: 'always' },
            audio: false
        });
        
        elements['screen-video'].srcObject = state.screenStream;
        
        elements['screen-status'].textContent = '已授权';
        elements['screen-status'].className = 'status granted';
        
        // 监听用户取消共享
        state.screenStream.getVideoTracks()[0].onended = () => {
            elements['screen-status'].textContent = '已停止';
            elements['screen-status'].className = 'status denied';
            state.screenStream = null;
            checkPermissions();
        };
        
        checkPermissions();
    } catch (error) {
        console.error('屏幕录制权限被拒绝:', error);
        elements['screen-status'].textContent = '被拒绝';
        elements['screen-status'].className = 'status denied';
    }
}

// 检查权限状态
function checkPermissions() {
    const hasCamera = state.webcamStream !== null;
    const hasScreen = state.screenStream !== null;
    
    elements['enter-drawing-btn'].disabled = !(hasCamera && hasScreen);
}

// 初始化画布
function initCanvas() {
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
function resizeCanvas() {
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

// 开始录制
async function startRecording() {
    if (!state.webcamStream || !state.screenStream) {
        alert('请先授权摄像头和屏幕录制');
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
    
    // 启动屏幕录制
    try {
        state.mediaRecorder.screen = new MediaRecorder(state.screenStream, {
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
        console.log('[录制] 屏幕录制已启动');
    } catch (e) {
        console.error('[录制] 屏幕录制启动失败:', e);
        alert('屏幕录制启动失败');
        return;
    }
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
function setTool(tool) {
    state.currentTool = tool;
    elements['pen-btn'].classList.toggle('active', tool === 'pen');
    elements['eraser-btn'].classList.toggle('active', tool === 'eraser');
}

function clearCanvas() {
    if (confirm('确定要清空画布吗？')) {
        state.ctx.fillStyle = 'white';
        state.ctx.fillRect(0, 0, state.canvas.width, state.canvas.height);
    }
}

function rotateCanvas() {
    state.canvasRotation = (state.canvasRotation + 90) % 360;
    state.canvas.style.transform = `rotate(${state.canvasRotation}deg)`;
}

// 同时停止多个录制器并等待完成
function stopRecordersSimultaneously() {
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
async function submitDrawing() {
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
                screen_video: screenBase64
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

// Blob 转 Base64
function blobToBase64(blob) {
    return new Promise((resolve) => {
        const reader = new FileReader();
        reader.onloadend = () => resolve(reader.result);
        reader.readAsDataURL(blob);
    });
}

// 显示问题
function showQuestions(data) {
    showPage('questioning-page');
    
    const container = elements['questions-container'];
    container.innerHTML = '';
    
    data.questions.forEach((question, index) => {
        const item = document.createElement('div');
        item.className = 'question-item';
        item.innerHTML = `
            <label>${question}</label>
            <textarea data-index="${index}" placeholder="请详细描述..."></textarea>
        `;
        container.appendChild(item);
    });
    
    // 填充选项
    const ageSelect = elements['age-select'];
    ageSelect.innerHTML = '<option value="">请选择</option>';
    data.age_groups.forEach(age => {
        const option = document.createElement('option');
        option.value = age;
        option.textContent = age;
        ageSelect.appendChild(option);
    });
    
    const genderSelect = elements['gender-select'];
    genderSelect.innerHTML = '<option value="">请选择</option>';
    data.gender_options.forEach(gender => {
        const option = document.createElement('option');
        option.value = gender;
        option.textContent = gender;
        genderSelect.appendChild(option);
    });
}

// 提交回答
async function submitAnswers() {
    // 收集答案
    const answers = [];
    document.querySelectorAll('#questions-container textarea').forEach(textarea => {
        answers.push(textarea.value);
    });
    
    const age = elements['age-select'].value;
    const gender = elements['gender-select'].value;
    
    if (!age || !gender) {
        alert('请选择年龄段和性别');
        return;
    }
    
    // 提交基本信息
    await fetch(`/api/session/${state.sessionId}/info`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: state.sessionId, age_group: age, gender: gender })
    });
    
    // 提交回答并开始生成图像
    showPage('generating-page');
    
    await fetch(`/api/session/${state.sessionId}/answers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: state.sessionId, answers: answers })
    });
}

// 显示生成的图像
function showGeneratedImages(data) {
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
let currentPreviewIndex = -1;

function previewImage(index) {
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
function cancelPreview() {
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
async function confirmSelection() {
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

// 显示最终问题
function showFinalQuestions(data) {
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
async function submitFinalAnswers() {
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
function showFinalReport(data) {
    showPage('result-page');
    
    const container = elements['report-content'];
    const analysis = data.final_analysis || data;
    
    // 深度分析部分
    const deepAnalysis = analysis.deep_analysis || {};
    
    container.innerHTML = `
        <div class="report-header">
            <h3>📊 综合分析</h3>
            <div class="report-summary-box">
                <p>${analysis.summary || '暂无分析'}</p>
            </div>
        </div>
        
        <div class="report-grid">
            <div class="report-card">
                <h4>😰 压力水平</h4>
                <p>${analysis.stress_level || '未评估'}</p>
            </div>
            
            <div class="report-card">
                <h4>🛡️ 应对方式</h4>
                <p>${analysis.coping_style || '未评估'}</p>
            </div>
            
            <div class="report-card">
                <h4>😊 情绪状态</h4>
                <p>${analysis.emotional_state || '未评估'}</p>
            </div>
        </div>
        
        ${analysis.key_insights && analysis.key_insights.length > 0 ? `
        <div class="report-section">
            <h3>💡 关键发现</h3>
            <ul class="insights-list">
                ${analysis.key_insights.map(insight => `
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
            <h3>🎯 选择行为解读</h3>
            <p class="selection-analysis">${analysis.selection_interpretation}</p>
        </div>
        ` : ''}
        
        ${(deepAnalysis.self_concept || deepAnalysis.interpersonal || deepAnalysis.stress_response || deepAnalysis.underlying_needs) ? `
        <div class="report-section">
            <h3>🔍 深度心理分析</h3>
            <div class="deep-analysis-grid">
                ${deepAnalysis.self_concept ? `
                    <div class="deep-analysis-item">
                        <h5>自我概念</h5>
                        <p>${deepAnalysis.self_concept}</p>
                    </div>
                ` : ''}
                ${deepAnalysis.interpersonal ? `
                    <div class="deep-analysis-item">
                        <h5>人际关系模式</h5>
                        <p>${deepAnalysis.interpersonal}</p>
                    </div>
                ` : ''}
                ${deepAnalysis.stress_response ? `
                    <div class="deep-analysis-item">
                        <h5>压力反应模式</h5>
                        <p>${deepAnalysis.stress_response}</p>
                    </div>
                ` : ''}
                ${deepAnalysis.underlying_needs ? `
                    <div class="deep-analysis-item">
                        <h5>潜在心理需求</h5>
                        <p>${deepAnalysis.underlying_needs}</p>
                    </div>
                ` : ''}
            </div>
        </div>
        ` : ''}
        
        ${analysis.recommendations && analysis.recommendations.length > 0 ? `
        <div class="report-section">
            <h3>💪 专业建议</h3>
            <div class="recommendations-list">
                ${analysis.recommendations.map((rec, i) => `
                    <div class="recommendation-item">
                        <span class="rec-number">${i + 1}</span>
                        <p>${rec}</p>
                    </div>
                `).join('')}
            </div>
        </div>
        ` : ''}
        
        ${analysis.follow_up && analysis.follow_up.length > 0 ? `
        <div class="report-section">
            <h3>📌 后续关注要点</h3>
            <ul class="follow-up-list">
                ${analysis.follow_up.map(item => `<li>${item}</li>`).join('')}
            </ul>
        </div>
        ` : ''}
        
        <div class="report-footer">
            <p class="disclaimer">⚠️ 本报告基于AI分析生成，仅供参考。如有需要，请咨询专业心理咨询师。</p>
        </div>
    `;
}

// 窗口大小改变时调整画布
window.addEventListener('resize', () => {
    if (state.canvas) {
        resizeCanvas();
    }
});
