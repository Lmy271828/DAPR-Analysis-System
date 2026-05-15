export const state = {
    ws: null,
    wsReconnectAttempts: 0,
    wsReconnectTimer: null,
    wsManuallyClosed: false,
    sessions: [],
    logs: [],
    selectedSession: null,
    filter: 'all'
};

export const streamState = {
    activeStreams: new Map()
};
