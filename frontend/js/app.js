/**
 * Document AI Studio V3 - Client Logic
 * Handles 30+ endpoints, WebSocket collaboration (placeholder ready),
 * dynamic UI rendering, and streaming responses.
 */

const STATE = {
    theme: localStorage.getItem('theme') || 'dark',
    isStreaming: true,
    currentSessionId: null,
    isQuerying: false,
    documents: [],
    activeFilter: null
};

// -------------------------------------------------------------
// UI / DOM Helpers
// -------------------------------------------------------------
const getEl = (id) => document.getElementById(id);

const DOM = {
    themeBtn: getEl('themeToggleBtn'),
    pulse: getEl('systemPulse'),
    statusText: getEl('systemStatusText'),
    vectorCount: getEl('globalVectorCount'),
    viewTitle: getEl('currentViewTitle'),
    navBtns: document.querySelectorAll('.nav-btn'),
    views: document.querySelectorAll('.view-panel'),
    toastContainer: getEl('toastContainer'),

    // Chat
    queryInput: getEl('queryInput'),
    sendBtn: getEl('sendQueryBtn'),
    chatStream: getEl('chatStream'),
    emptyState: getEl('chatEmptyState'),
    streamToggle: getEl('streamToggle'),
    sourceFilterSelect: getEl('sourceFilterSelect'),
    resetFilterBtn: getEl('resetFilterBtn'),
    exportChatBtn: getEl('exportChatBtn'),
    clearChatBtn: getEl('clearChatBtn'),

    // Documents
    dropZone: getEl('dropZone'),
    bulkInput: getEl('bulkFileInput'),
    triggerFileBtn: getEl('triggerFileBtn'),
    uploadProgressBox: getEl('uploadProgressBox'),
    docTableBody: getEl('documentTableBody'),
    urlIngestInput: getEl('urlIngestInput'),
    ingestUrlBtn: getEl('ingestUrlBtn'),
    clearIndexBtn: getEl('clearIndexBtn'),
    documentSearchInput: getEl('documentSearchInput'),

    // Compare
    compareSelectA: getEl('compareSelectA'),
    compareSelectB: getEl('compareSelectB'),
    compareInput: getEl('compareQuestionInput'),
    runCompareBtn: getEl('runCompareBtn'),
    compareResult: getEl('compareResultContent'),

    // Extract & Summarize
    extractFields: getEl('extractFieldsInput'),
    extractContext: getEl('extractContextInput'),
    runExtractBtn: getEl('runExtractBtn'),
    extractResult: getEl('extractResultContent'),
    summaryTopic: getEl('summaryTopicInput'),
    runSummaryBtn: getEl('runSummaryBtn'),
    summaryResult: getEl('summaryResultContent'),

    // Dashboards
    analyticsDash: getEl('analyticsDashboard'),
    ragasDash: getEl('ragasDashboard'),
    ragasHistory: getEl('ragasHistoryLog'),

    // Sessions
    sessionList: getEl('sessionList'),
    newSessionBtn: getEl('newSessionBtn'),

    // Modals
    settingsModal: getEl('settingsModal')
};

function showToast(msg, type = 'info') {
    const t = document.createElement('div');
    t.className = `toast ${type}`;
    t.textContent = String(msg);
    DOM.toastContainer.appendChild(t);
    // Trigger animation
    requestAnimationFrame(() => t.classList.add('show'));
    setTimeout(() => {
        t.classList.remove('show');
        setTimeout(() => t.remove(), 400);
    }, 4000);
}

const escapeHtml = (text) => {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
};

// -------------------------------------------------------------
// Core API
// -------------------------------------------------------------
async function apiCall(endpoint, options = {}) {
    try {
        const res = await fetch(endpoint, options);
        if (!res.ok) {
            let errorMsg = `HTTP ${res.status}`;
            try {
                const errData = await res.json();
                errorMsg = errData.detail || errorMsg;
            } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    } catch (err) {
        showToast(`API Error: ${err.message}`, 'error');
        throw err;
    }
}

// -------------------------------------------------------------
// Initialization & Theming
// -------------------------------------------------------------
function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
}

DOM.themeBtn.addEventListener('click', () => {
    STATE.theme = STATE.theme === 'dark' ? 'light' : 'dark';
    applyTheme(STATE.theme);
});

// View Navigation
DOM.navBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        DOM.navBtns.forEach(b => b.classList.remove('active'));
        DOM.views.forEach(v => v.classList.remove('active'));
        
        btn.classList.add('active');
        const targetId = btn.getAttribute('data-target');
        getEl(targetId).classList.add('active');
        DOM.viewTitle.textContent = btn.textContent.trim();

        // Specific view initializers
        if (targetId === 'view-documents') loadDocuments();
        if (targetId === 'view-compare') renderCompareDropdowns();
        if (targetId === 'view-analytics') loadAnalytics();
        if (targetId === 'view-ragas') loadRagas();
    });
});

// -------------------------------------------------------------
// System Status & Background Tasks
// -------------------------------------------------------------
async function refreshStatus() {
    try {
        const data = await apiCall('/status');
        const isOnline = data.ollama === 'connected';
        DOM.statusText.textContent = isOnline ? 'System Online' : 'LLM Offline';
        DOM.pulse.style.backgroundColor = isOnline ? 'var(--success)' : 'var(--danger)';
        DOM.pulse.style.boxShadow = `0 0 10px ${isOnline ? 'var(--success)' : 'var(--danger)'}`;
        DOM.vectorCount.textContent = (data.total_vectors || 0).toLocaleString();
    } catch (e) {
        DOM.statusText.textContent = 'API Unreachable';
        DOM.pulse.style.backgroundColor = 'var(--danger)';
        DOM.pulse.style.boxShadow = `0 0 10px var(--danger)`;
    }
}

// -------------------------------------------------------------
// Sessions
// -------------------------------------------------------------
async function loadSessions() {
    try {
        const sessions = await apiCall('/sessions');
        DOM.sessionList.innerHTML = '';
        if (sessions.length === 0) {
            await createNewSession();
            return;
        }

        sessions.forEach(s => {
            const div = document.createElement('div');
            div.className = 'session-item';
            div.textContent = s.title || `Session ${s.id.substring(0,6)}`;
            div.onclick = () => switchSession(s.id);
            if (s.id === STATE.currentSessionId) {
                div.style.color = 'var(--accent-primary)';
                div.style.fontWeight = '700';
            }
            DOM.sessionList.appendChild(div);
        });

        if (!STATE.currentSessionId) {
            switchSession(sessions[0].id);
        }
    } catch {}
}

async function createNewSession() {
    try {
        const s = await apiCall('/sessions', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({title: 'New Workspace ' + new Date().toLocaleTimeString() })
        });
        showToast('New session created', 'success');
        STATE.currentSessionId = s.id;
        DOM.chatStream.innerHTML = ''; // clear chat
        DOM.chatStream.appendChild(DOM.emptyState);
        DOM.emptyState.style.display = 'flex';
        await loadSessions();
    } catch {}
}

async function switchSession(id) {
    STATE.currentSessionId = id;
    await loadSessions(); // re-render to higlight
    // Load messages
    try {
        const msgs = await apiCall(`/sessions/${id}/messages`);
        DOM.chatStream.innerHTML = '';
        if (msgs.length === 0) {
            DOM.chatStream.appendChild(DOM.emptyState);
            DOM.emptyState.style.display = 'flex';
        } else {
            DOM.emptyState.style.display = 'none';
            msgs.forEach(m => {
                appendChatBubble(m.role, m.content, m.sources || []);
            });
        }
        DOM.chatStream.scrollTop = DOM.chatStream.scrollHeight;
    } catch {}
}

DOM.newSessionBtn.addEventListener('click', createNewSession);

// -------------------------------------------------------------
// Chat Engine
// -------------------------------------------------------------
DOM.streamToggle.addEventListener('click', () => {
    STATE.isStreaming = !STATE.isStreaming;
    DOM.streamToggle.classList.toggle('active', STATE.isStreaming);
    DOM.streamToggle.querySelector('span').textContent = STATE.isStreaming ? 'ON' : 'OFF';
});

if (DOM.sourceFilterSelect) {
    DOM.sourceFilterSelect.addEventListener('change', (e) => {
        const value = e.target.value || null;
        STATE.activeFilter = value;
        showToast(value ? `Source filter: ${value}` : 'Source filter cleared', 'info');
    });
}

if (DOM.resetFilterBtn) {
    DOM.resetFilterBtn.addEventListener('click', () => {
        STATE.activeFilter = null;
        if (DOM.sourceFilterSelect) DOM.sourceFilterSelect.value = '';
        showToast('Source filter reset', 'success');
    });
}

if (DOM.exportChatBtn) {
    DOM.exportChatBtn.addEventListener('click', async () => {
        if (!STATE.currentSessionId) {
            showToast('No active session to export', 'error');
            return;
        }

        try {
            const msgs = await apiCall(`/sessions/${STATE.currentSessionId}/messages?limit=500`);
            if (!msgs.length) {
                showToast('No messages in this session', 'info');
                return;
            }

            const lines = ['# DocuAI Chat Export', `Session: ${STATE.currentSessionId}`, ''];
            msgs.forEach((m) => {
                lines.push(`## ${m.role.toUpperCase()}`);
                lines.push(m.content || '');
                lines.push('');
            });

            const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `docuai-session-${STATE.currentSessionId.slice(0, 8)}.md`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            showToast('Session exported', 'success');
        } catch (e) {
            showToast(`Export failed: ${e.message}`, 'error');
        }
    });
}

if (DOM.clearChatBtn) {
    DOM.clearChatBtn.addEventListener('click', async () => {
        await createNewSession();
    });
}

DOM.queryInput.addEventListener('input', () => {
    DOM.queryInput.style.height = 'auto';
    DOM.queryInput.style.height = `${Math.min(DOM.queryInput.scrollHeight, 150)}px`;
});

function formatTime() {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function appendChatBubble(role, content, sources = []) {
    DOM.emptyState.style.display = 'none';
    const isUser = role === 'user';
    const row = document.createElement('div');
    row.className = `msg-row ${isUser ? 'msg-user' : 'msg-ai'}`;
    
    let sourcesHtml = '';
    if (sources && sources.length > 0) {
        sourcesHtml = '<div class="sources-deck">';
        sources.forEach(s => {
            const safeObj = escapeHtml(JSON.stringify(s));
            sourcesHtml += `<div class="source-card" onclick='viewSourceCard(this)' data-source='${safeObj}'>📎 ${escapeHtml(s.source)} (p.${s.page || 1})</div>`;
        });
        sourcesHtml += '</div>';
    }

    // Basic markdown replacement for visual cleanlyness
    let formattedContent = escapeHtml(content);
    if (!isUser) {
        formattedContent = formattedContent
            .replace(/```(.*?)```/gs, '<pre><code>$1</code></pre>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/\n\n/g, '<br><br>');
    }

    row.innerHTML = `
        <div class="msg-avatar">${isUser ? '👤' : '🤖'}</div>
        <div class="msg-content-wrapper">
            <div class="msg-meta">
                <span>${isUser ? 'You' : 'DocuAI'}</span>
                <span>${formatTime()}</span>
            </div>
            <div class="msg-bubble">${formattedContent}</div>
            ${!isUser ? '<div class="msg-actions"><button class="msg-action-btn" type="button">Copy</button></div>' : ''}
            ${sourcesHtml}
        </div>
    `;

    if (!isUser) {
        const copyBtn = row.querySelector('.msg-action-btn');
        if (copyBtn) {
            copyBtn.addEventListener('click', async () => {
                try {
                    await navigator.clipboard.writeText(content || '');
                    showToast('Answer copied', 'success');
                } catch (e) {
                    showToast('Copy failed', 'error');
                }
            });
        }
    }
    
    DOM.chatStream.appendChild(row);
    DOM.chatStream.scrollTop = DOM.chatStream.scrollHeight;
    return row;
}

window.viewSourceCard = (el) => {
    try {
        const data = JSON.parse(el.dataset.source);
        getEl('sourceModalTitle').textContent = `Document: ${data.source} (Page ${data.page})`;
        getEl('sourceModalBody').textContent = data.excerpt || "No excerpt bound.";
        getEl('sourceModal').classList.add('active');
    } catch (e) { console.error(e); }
};

document.querySelectorAll('.close-modal-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
        e.target.closest('.modal-overlay').classList.remove('active');
    });
});

async function triggerQuery() {
    if (STATE.isQuerying) return;
    const q = DOM.queryInput.value.trim();
    if (!q) return;

    DOM.queryInput.value = '';
    STATE.isQuerying = true;
    DOM.sendBtn.style.opacity = '0.5';

    appendChatBubble('user', q);

    if (STATE.isStreaming) {
        await handleStreamQuery(q);
    } else {
        await handleSyncQuery(q);
    }

    STATE.isQuerying = false;
    DOM.sendBtn.style.opacity = '1';
    refreshStatus();
}

async function handleSyncQuery(q) {
    try {
        const res = await apiCall('/query', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: q,
                session_id: STATE.currentSessionId,
                source_filter: STATE.activeFilter
            })
        });
        appendChatBubble('assistant', res.answer || 'No answer generated.', res.sources || []);
    } catch (e) {
        appendChatBubble('assistant', `⚠️ Query Failed: ${e.message}`);
    }
}

async function handleStreamQuery(q) {
    // Scaffold UI for streaming
    DOM.emptyState.style.display = 'none';
    const row = document.createElement('div');
    row.className = `msg-row msg-ai`;
    row.innerHTML = `
        <div class="msg-avatar">🤖</div>
        <div class="msg-content-wrapper">
            <div class="msg-meta"><span>DocuAI Stream</span><span>${formatTime()}</span></div>
            <div class="msg-bubble"><div class="loading-dots"><span></span><span></span><span></span></div></div>
        </div>
    `;
    DOM.chatStream.appendChild(row);
    DOM.chatStream.scrollTop = DOM.chatStream.scrollHeight;
    
    const bubble = row.querySelector('.msg-bubble');
    const wrapper = row.querySelector('.msg-content-wrapper');
    let fullAnswer = "";
    let sources = [];

    try {
        const response = await fetch('/query-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question: q, session_id: STATE.currentSessionId, source_filter: STATE.activeFilter })
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = line.slice(6);
                    if (data === '[DONE]') continue;
                    try {
                        const payload = JSON.parse(data);
                        if (Array.isArray(payload.sources)) {
                            sources = payload.sources;
                        }
                        if (payload.delta) {
                            fullAnswer += payload.delta;
                            bubble.innerHTML = escapeHtml(fullAnswer).replace(/\n\n/g, '<br><br>');
                        }
                    } catch (e) {
                        fullAnswer += data;
                        bubble.innerHTML = escapeHtml(fullAnswer).replace(/\n\n/g, '<br><br>');
                    }
                    DOM.chatStream.scrollTop = DOM.chatStream.scrollHeight;
                }
            }
        }

        if (sources.length > 0) {
            const deck = document.createElement('div');
            deck.className = 'sources-deck';
            deck.innerHTML = sources.map(s => {
                const safeObj = escapeHtml(JSON.stringify(s));
                return `<div class="source-card" onclick='viewSourceCard(this)' data-source='${safeObj}'>📎 ${escapeHtml(s.source)} (p.${s.page || 1})</div>`;
            }).join('');
            wrapper.appendChild(deck);
        }

    } catch (err) {
        bubble.textContent = `⚠️ Streaming Error: ${err.message}`;
    }
}

DOM.sendBtn.addEventListener('click', triggerQuery);
DOM.queryInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        triggerQuery();
    }
});

// Template prompts hook
document.querySelectorAll('.suggestion-btn').forEach(b => {
    b.addEventListener('click', (e) => {
        DOM.queryInput.value = e.target.textContent;
        triggerQuery();
    });
});

// -------------------------------------------------------------
// Documents & Upload
// -------------------------------------------------------------
async function loadDocuments() {
    try {
        const docs = await apiCall('/documents');
        STATE.documents = docs;
        renderDocumentRows();
        refreshSourceFilterOptions();
        
    } catch {}
}

function renderDocumentRows() {
    const q = (DOM.documentSearchInput?.value || '').trim().toLowerCase();
    DOM.docTableBody.innerHTML = '';

    const docs = STATE.documents.filter((doc) => {
        if (!q) return true;
        return doc.filename.toLowerCase().includes(q) || (doc.suffix || '').toLowerCase().includes(q);
    });

    if (docs.length === 0) {
        DOM.docTableBody.innerHTML = `<tr><td colspan="5" class="text-center text-muted">No matching documents found.</td></tr>`;
        return;
    }

    docs.forEach(doc => {
        const tr = document.createElement('tr');

        const nameTd = document.createElement('td');
        const nameLink = document.createElement('a');
        nameLink.href = '#';
        nameLink.style.color = 'var(--accent-primary)';
        nameLink.style.textDecoration = 'none';
        nameLink.style.fontWeight = '600';
        nameLink.textContent = doc.filename;
        nameLink.addEventListener('click', (e) => {
            e.preventDefault();
            openPreview(doc.filename);
        });
        nameTd.appendChild(nameLink);

        const typeTd = document.createElement('td');
        const typePill = document.createElement('span');
        typePill.className = 'pill-btn';
        typePill.textContent = (doc.suffix || '').toUpperCase().replace('.', '');
        typeTd.appendChild(typePill);

        const sizeTd = document.createElement('td');
        sizeTd.textContent = `${doc.size_mb} MB`;

        const dateTd = document.createElement('td');
        dateTd.textContent = new Date(doc.modified || Date.now()).toLocaleDateString();

        const actionTd = document.createElement('td');
        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'btn-danger-outline';
        deleteBtn.textContent = 'Delete';
        deleteBtn.addEventListener('click', () => {
            deleteDoc(doc.filename);
        });
        actionTd.appendChild(deleteBtn);

        tr.appendChild(nameTd);
        tr.appendChild(typeTd);
        tr.appendChild(sizeTd);
        tr.appendChild(dateTd);
        tr.appendChild(actionTd);
        DOM.docTableBody.appendChild(tr);
    });
}

function refreshSourceFilterOptions() {
    if (!DOM.sourceFilterSelect) return;
    const current = STATE.activeFilter || '';
    DOM.sourceFilterSelect.innerHTML = '';

    const allOption = document.createElement('option');
    allOption.value = '';
    allOption.textContent = 'All Documents';
    DOM.sourceFilterSelect.appendChild(allOption);

    STATE.documents.forEach((d) => {
        const option = document.createElement('option');
        option.value = d.filename;
        option.textContent = d.filename;
        DOM.sourceFilterSelect.appendChild(option);
    });

    const isValidCurrent = current && STATE.documents.some((d) => d.filename === current);
    DOM.sourceFilterSelect.value = isValidCurrent ? current : '';
    if (!isValidCurrent) {
        STATE.activeFilter = null;
    }
}

if (DOM.documentSearchInput) {
    DOM.documentSearchInput.addEventListener('input', renderDocumentRows);
}

window.deleteDoc = async (filename) => {
    if(!confirm(`Delete ${filename} permanently from vector index?`)) return;
    try {
        await apiCall(`/document/${encodeURIComponent(filename)}`, { method: 'DELETE' });
        showToast(`Source deleted: ${filename}`, 'success');
        loadDocuments();
        refreshStatus();
    } catch {}
};

DOM.clearIndexBtn.addEventListener('click', async () => {
    if(!confirm("DANGER: Wiping entire vector index. Continue?")) return;
    try {
        await apiCall('/clear', { method: 'POST' });
        showToast("Index totally cleared.", "success");
        loadDocuments();
        refreshStatus();
    } catch {}
});

// File Upload Handlers
DOM.triggerFileBtn.addEventListener('click', () => DOM.bulkInput.click());
getEl('quickUploadBtn').addEventListener('click', () => {
    document.querySelector('[data-target="view-documents"]').click();
});

DOM.bulkInput.addEventListener('change', async (e) => {
    if (e.target.files.length > 0) handleFiles(e.target.files);
    e.target.value = '';
});

DOM.dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    DOM.dropZone.classList.add('dragover');
});
DOM.dropZone.addEventListener('dragleave', () => DOM.dropZone.classList.remove('dragover'));
DOM.dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    DOM.dropZone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) handleFiles(e.dataTransfer.files);
});

async function handleFiles(files) {
    DOM.uploadProgressBox.style.display = 'block';
    const percentEl = getEl('uploadPercent');
    const barEl = getEl('uploadBar');
    const nameEl = getEl('uploadFilename');
    
    // Convert to array
    const fileArray = Array.from(files);
    let successCount = 0;

    for (let i = 0; i < fileArray.length; i++) {
        const file = fileArray[i];
        nameEl.textContent = `Processing: ${file.name}`;
        
        const fd = new FormData();
        fd.append('file', file);

        try {
            await apiCall('/ingest', { method: 'POST', body: fd });
            successCount++;
        } catch {}

        const p = Math.round(((i + 1) / fileArray.length) * 100);
        percentEl.textContent = `${p}%`;
        barEl.style.width = `${p}%`;
    }

    showToast(`Successfully indexed ${successCount}/${fileArray.length} items.`, 'success');
    setTimeout(() => { DOM.uploadProgressBox.style.display = 'none'; barEl.style.width = '0%'; }, 2000);
    loadDocuments();
    refreshStatus();
}

DOM.ingestUrlBtn.addEventListener('click', async () => {
    const url = DOM.urlIngestInput.value.trim();
    if(!url) return;
    try {
        const res = await apiCall('/ingest/url', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({url})
        });
        showToast(`Indexed URL (${res.chunks} chunks)`, 'success');
        DOM.urlIngestInput.value = '';
        loadDocuments();
        refreshStatus();
    } catch {}
});

// -------------------------------------------------------------
// Intelligence Views (Compare, Extract, Summarize)
// -------------------------------------------------------------
function renderCompareDropdowns() {
    const fill = (selectEl) => {
        if (!selectEl) return;
        selectEl.innerHTML = '';
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = 'Select Document...';
        selectEl.appendChild(placeholder);

        STATE.documents.forEach((d) => {
            const option = document.createElement('option');
            option.value = d.filename;
            option.textContent = d.filename;
            selectEl.appendChild(option);
        });
    };

    fill(DOM.compareSelectA);
    fill(DOM.compareSelectB);
}

DOM.runCompareBtn.addEventListener('click', async () => {
    const a = DOM.compareSelectA.value;
    const b = DOM.compareSelectB.value;
    const q = DOM.compareInput.value;
    if(!a || !b) { showToast("Select both documents", "error"); return; }

    DOM.compareResult.innerHTML = `<div class="loading-dots"><span></span><span></span><span></span></div> Working...`;
    try {
        const data = await apiCall('/compare', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({doc_a: a, doc_b: b, question: q})
        });
        DOM.compareResult.innerHTML = escapeHtml(data.comparison || data.analysis || JSON.stringify(data)).replace(/\n/g, '<br>');
    } catch (e) {
        DOM.compareResult.innerHTML = `<span class="text-danger">Failed to evaluate: ${e.message}</span>`;
    }
});

DOM.runExtractBtn.addEventListener('click', async () => {
    const fields = DOM.extractFields.value.split('\n').map(l=>l.trim()).filter(Boolean);
    if(fields.length === 0) { showToast("Specify extraction keys", "error"); return; }

    DOM.extractResult.innerHTML = `Evaluating schema...`;
    try {
        const data = await apiCall('/extract', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({fields, context_query: DOM.extractContext.value})
        });
        DOM.extractResult.innerHTML = escapeHtml(JSON.stringify(data.extracted_data || data.fields || data, null, 2));
    } catch(e) {
        DOM.extractResult.innerHTML = escapeHtml(e.message);
    }
});

DOM.runSummaryBtn.addEventListener('click', async () => {
    DOM.summaryResult.innerHTML = `<div class="loading-dots"><span></span><span></span><span></span></div>`;
    try {
        const data = await apiCall('/summarize', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({topic: DOM.summaryTopic.value.trim() || 'the entire embedding index'})
        });
        DOM.summaryResult.innerHTML = escapeHtml(data.summary).replace(/\n/g, '<br>');
    } catch(e) {
        DOM.summaryResult.innerHTML = escapeHtml(e.message);
    }
});

// -------------------------------------------------------------
// Analytics & RAGAS
// -------------------------------------------------------------
async function loadAnalytics() {
    try {
        const data = await apiCall('/analytics');
        DOM.analyticsDash.innerHTML = `
            <div class="stat-box">
                <span class="s-label">Total Vectors Indexed</span>
                <span class="s-value">${data.total_vectors || 0}</span>
            </div>
            <div class="stat-box">
                <span class="s-label">Index Storage Size</span>
                <span class="s-value">${(data.storage?.index_size_mb || 0).toFixed(2)} MB</span>
            </div>
            <div class="stat-box">
                <span class="s-label">LRU Cache Hits</span>
                <span class="s-value">${data.cache?.hits || 0}</span>
            </div>
             <div class="stat-box">
                <span class="s-label">Unique Sources</span>
                <span class="s-value">${(data.sources || []).length}</span>
            </div>
        `;
    } catch {}
}
getEl('refreshAnalyticsBtn').addEventListener('click', loadAnalytics);

async function loadRagas() {
    try {
        const data = await apiCall('/evaluate/dashboard');
        DOM.ragasDash.innerHTML = `
            <div class="stat-box">
                <span class="s-label">Total Evaluated Queries</span>
                <span class="s-value">${data.total_evaluations || 0}</span>
            </div>
            <div class="stat-box">
                <span class="s-label">Avg Quality Core</span>
                <span class="s-value">${((data.avg_overall || 0)*100).toFixed(1)}%</span>
            </div>
        `;

        const history = await apiCall('/evaluate/history?limit=20');
        DOM.ragasHistory.innerHTML = '';
        if(history.length === 0){
             DOM.ragasHistory.innerHTML = `<tr><td colspan="2" class="text-center text-muted">No evaluations run yet.</td></tr>`;
             return;
        }

        history.forEach(h => {
             const tr = document.createElement('tr');
             const score = ((h.overall_score||0)*100).toFixed(0);
             tr.innerHTML = `
                <td>${escapeHtml(h.question)}</td>
                <td><span class="pill-btn" style="color: ${score > 80 ? 'var(--success)' : 'var(--warning)'}">${score}%</span></td>
             `;
             DOM.ragasHistory.appendChild(tr);
        });
    } catch {}
}
getEl('refreshRagasBtn').addEventListener('click', loadRagas);

getEl('purgeRagasBtn').addEventListener('click', async () => {
    if(!confirm("Clear all RAGAS evaluation metrics?")) return;
    try {
        await apiCall('/evaluate/clear', { method: 'POST' });
        loadRagas();
        showToast("Evaluation logs purged.", "success");
    } catch {}
});

// Settings Modal
getEl('settingsBtn').addEventListener('click', () => {
    DOM.settingsModal.classList.add('active');
});
getEl('clearCacheBtn').addEventListener('click', async () => {
    try {
        const res = await apiCall('/cache/clear', { method: 'POST' });
        showToast(`Cache purged. Items removed: ${res.entries_removed}`, 'success');
        DOM.settingsModal.classList.remove('active');
    } catch {}
});

// Document Preview Modal
window.openPreview = (filename) => {
    getEl('previewModalTitle').textContent = filename;
    const ext = filename.split('.').pop().toLowerCase();
    const frame = getEl('previewFrame');
    const unsupported = getEl('previewUnsupported');
    const downloadBtn = getEl('previewDownloadBtn');
    
    // Construct local download URL
    const url = `/download/${encodeURIComponent(filename)}`;
    
    // File types most modern browsers can reliably iframe
    const previewable = ['pdf', 'txt', 'png', 'jpg', 'jpeg', 'md'];
    
    if (previewable.includes(ext)) {
        frame.style.display = 'block';
        unsupported.style.display = 'none';
        frame.src = url;
    } else {
        frame.style.display = 'none';
        unsupported.style.display = 'block';
        downloadBtn.href = url;
    }
    
    getEl('previewModal').classList.add('active');
};


// Initialization hooks
applyTheme(STATE.theme);
refreshStatus();
loadSessions();
loadDocuments();

setInterval(refreshStatus, 30000); // 30s poll
