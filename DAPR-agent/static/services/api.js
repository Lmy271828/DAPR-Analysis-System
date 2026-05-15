export async function fetchSessionDetail(sessionId) {
    const response = await fetch(`/api/session/${sessionId}`);
    if (!response.ok) {
        throw new Error(`Failed to fetch session detail: ${response.status}`);
    }
    return response.json();
}

export async function fetchHistorySessions() {
    const response = await fetch('/api/history/sessions');
    if (!response.ok) {
        throw new Error(`Failed to fetch history sessions: ${response.status}`);
    }
    return response.json();
}

export async function startHistoryAnalysis(sessionId, createNew) {
    const response = await fetch('/api/history/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            session_id: sessionId,
            create_new: createNew
        })
    });
    return response;
}
