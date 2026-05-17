/**
 * DAPR Agent 全局配置和状态
 */

// 全局状态
export const state = {
    sessionId: null,
    ws: null,
    wsReconnectAttempts: 0,
    wsReconnectTimer: null,
    wsManuallyClosed: false,
    wsMessageIds: new Set(),
    webcamStream: null,
    canvasStream: null,
    canvasRecordingEnabled: false,
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
export const CONFIG = {
    API_BASE: '',
    WS_URL: () => `ws://${window.location.host}/ws/subject/${state.sessionId}`,
    CANVAS_WIDTH: 850,
    CANVAS_HEIGHT: 1100,
    WS_RECONNECT_BASE_MS: 1000,
    WS_RECONNECT_MAX_MS: 30000,
    WS_RECONNECT_JITTER_MS: 300
};

// DOM 元素
export const elements = {};

// 流式分析状态
export const streamAnalysisState = {
    isStreaming: false,
    chunks: [],
    startTime: null
};
