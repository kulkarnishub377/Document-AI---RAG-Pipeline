/* app.js — DocuAI Studio v3.1 Client */
/* ─────────────────────────────────────────────────────────────────────────── */

const API = window.location.origin;
const getEl = (id) => document.getElementById(id);

// ── DOM Cache ────────────────────────────────────────────────────────────────
const DOM = {
    chatStream: getEl('chatStream'),
    chatEmptyState: getEl('chatEmptyState'),
    queryInput: getEl('queryInput'),
    sendQueryBtn: getEl('sendQueryBtn'),
    streamToggle: getEl('streamToggle'),
    sourceFilter: getEl('sourceFilterSelect'),
    currentViewTitle: getEl('currentViewTitle'),
    globalVectorCount: getEl('globalVectorCount'),
    systemPulse: getEl('systemPulse'),
    systemStatusText: getEl('systemStatusText'),
    sessionList: getEl('sessionList'),
    documentTableBody: getEl('documentTableBody'),
    documentSearchInput: getEl('documentSearchInput'),
    compareSelectA: getEl('compareSelectA'),
    compareSelectB: getEl('compareSelectB'),
    compareResult: getEl('compareResultContent'),
    extractFields: getEl('extractFieldsInput'),
    extractContext: getEl('extractContextInput'),
    extractResult: getEl('extractResultContent'),
    summaryTopic: getEl('summaryTopicInput'),
    summaryResult: getEl('summaryResultContent'),
    analyticsDash: getEl('analyticsDashboard'),
    queryAnalyticsDash: getEl('queryAnalyticsDash'),
    ragasDash: getEl('ragasDashboard'),
    ragasHistory: getEl('ragasHistoryLog'),
    settingsModal: getEl('settingsModal'),
    sourceModal: getEl('sourceModal'),
    shortcutsModal: getEl('shortcutsModal'),
    sidebarPanel: getEl('sidebarPanel'),
    sidebarToggle: getEl('sidebarToggleBtn'),
    searchInput: getEl('semanticSearchInput'),
    searchResults: getEl('searchResultsContainer'),
    searchSourceFilter: getEl('searchSourceFilter'),
    batchInput: getEl('batchQuestionsInput'),
    batchResultBody: getEl('batchResultBody'),
    batchResultPanel: getEl('batchResultPanel'),
    kgCanvas: getEl('kgCanvas'),
    kgStatsRow: getEl('kgStatsRow'),
    kgEntityList: getEl('kgEntityList'),
};

// ── State ────────────────────────────────────────────────────────────────────
const STATE = {
    isStreaming: JSON.parse(localStorage.getItem('streaming') ?? 'true'),
    isQuerying: false,
    currentSession: null,
    theme: localStorage.getItem('theme') || 'dark',
    allDocuments: [],
    batchResults: [],
};

// ── Utility Functions ────────────────────────────────────────────────────────
function escapeHtml(str) {
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}

function renderMarkdown(text) {
    if (typeof marked !== 'undefined') {
        marked.setOptions({
            breaks: true,
            gfm: true,
            sanitize: false,
            headerIds: false,
            mangle: false,
        });
        return marked.parse(text);
    }
    // Fallback if marked.js not loaded
    return text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/`(.*?)`/g, '<code>$1</code>')
        .replace(/\n/g, '<br>');
}

function showToast(msg, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = msg;
    getEl('toastContainer').appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('show'));
    setTimeout(() => { toast.classList.remove('show'); setTimeout(() => toast.remove(), 400); }, 3500);
}

async function apiCall(endpoint, opts = {}) {
    const res = await fetch(`${API}${endpoint}`, opts);
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || err.errors || `HTTP ${res.status}`);
    }
    return res.json();
}

function applyTheme(theme) {
    STATE.theme = theme;
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
}

// ── Navigation ───────────────────────────────────────────────────────────────
document.querySelectorAll('.nav-btn[data-target]').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const target = btn.dataset.target;
        document.querySelectorAll('.view-panel').forEach(v => v.classList.remove('active'));
        getEl(target)?.classList.add('active');
        DOM.currentViewTitle.textContent = btn.textContent.trim();

        // Load data for specific views
        if (target === 'view-analytics') { loadAnalytics(); loadQueryAnalytics(); }
        if (target === 'view-ragas') loadRagas();
        if (target === 'view-documents') loadDocuments();
        if (target === 'view-kg') loadKnowledgeGraph();

        // Close sidebar on mobile
        DOM.sidebarPanel.classList.remove('open');
        document.querySelector('.sidebar-overlay')?.classList.remove('active');
    });
});

// ── Mobile Sidebar Toggle (v3.1 — F18) ──────────────────────────────────────
DOM.sidebarToggle.addEventListener('click', () => {
    const isOpen = DOM.sidebarPanel.classList.toggle('open');
    let overlay = document.querySelector('.sidebar-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.className = 'sidebar-overlay';
        document.body.appendChild(overlay);
        overlay.addEventListener('click', () => {
            DOM.sidebarPanel.classList.remove('open');
            overlay.classList.remove('active');
        });
    }
    overlay.classList.toggle('active', isOpen);
});

// ── Theme Toggle ─────────────────────────────────────────────────────────────
getEl('themeToggleBtn').addEventListener('click', () => {
    applyTheme(STATE.theme === 'dark' ? 'light' : 'dark');
});

// ── Status Polling ───────────────────────────────────────────────────────────
async function refreshStatus() {
    try {
        const data = await apiCall('/status');
        DOM.globalVectorCount.textContent = (data.total_vectors || 0).toLocaleString();
        const connected = data.ollama === 'connected';
        DOM.systemPulse.style.background = connected ? 'var(--success)' : 'var(--warning)';
        DOM.systemPulse.style.boxShadow = `0 0 10px ${connected ? 'var(--success)' : 'var(--warning)'}`;
        DOM.systemStatusText.textContent = connected ? 'System Online' : 'Local Engine Online';
        updateSourceFilters(data.sources || []);
    } catch {}
}

function updateSourceFilters(sources) {
    const current = DOM.sourceFilter.value;
    DOM.sourceFilter.innerHTML = '<option value="">All Documents</option>';
    DOM.searchSourceFilter.innerHTML = '<option value="">All Sources</option>';
    sources.forEach(s => {
        DOM.sourceFilter.innerHTML += `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`;
        DOM.searchSourceFilter.innerHTML += `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`;
    });
    DOM.sourceFilter.value = current;
}

// ── Sessions ─────────────────────────────────────────────────────────────────
async function loadSessions() {
    try {
        const sessions = await apiCall('/sessions');
        DOM.sessionList.innerHTML = '';
        if (!sessions.length) {
            DOM.sessionList.innerHTML = '<div class="session-item" style="opacity:0.5">No sessions yet</div>';
            return;
        }
        sessions.forEach(s => {
            const item = document.createElement('div');
            item.className = 'session-item' + (s.id === STATE.currentSession ? ' active' : '');
            item.textContent = s.title || 'Untitled';
            item.addEventListener('click', () => switchSession(s.id));
            DOM.sessionList.appendChild(item);
        });
    } catch {}
}

async function switchSession(sessionId) {
    STATE.currentSession = sessionId;
    try {
        const messages = await apiCall(`/sessions/${sessionId}/messages`);
        DOM.chatStream.innerHTML = '';
        if (!messages.length) {
            DOM.chatStream.innerHTML = getEl('view-chat').querySelector('.chat-empty-state')?.outerHTML || '';
        }
        messages.forEach(m => appendMessage(m.role, m.content, m.sources));
        loadSessions();
    } catch {}
}

getEl('newSessionBtn').addEventListener('click', async () => {
    try {
        const s = await apiCall('/sessions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: `Session ${new Date().toLocaleDateString()}` }),
        });
        STATE.currentSession = s.id;
        loadSessions();
        DOM.chatStream.innerHTML = '';
        showToast('New session created', 'success');
    } catch {}
});

// ── Chat ─────────────────────────────────────────────────────────────────────
function appendMessage(role, content, sources = []) {
    if (DOM.chatEmptyState) DOM.chatEmptyState.style.display = 'none';
    const emptyState = DOM.chatStream.querySelector('.chat-empty-state');
    if (emptyState) emptyState.style.display = 'none';

    const row = document.createElement('div');
    row.className = `msg-row msg-${role === 'user' ? 'user' : 'ai'}`;

    const avatar = role === 'user' ? '👤' : '🤖';
    const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const renderedContent = role === 'assistant' ? renderMarkdown(content) : escapeHtml(content);

    let sourceCards = '';
    if (sources && sources.length) {
        sourceCards = '<div class="sources-deck">' + sources.map((s, i) =>
            `<div class="source-card" data-idx="${i}" data-source='${escapeHtml(JSON.stringify(s))}'>`
            + `📄 ${escapeHtml(s.source || 'unknown')} (p.${s.page || '?'})`
            + `</div>`
        ).join('') + '</div>';
    }

    row.innerHTML = `
        <div class="msg-avatar">${avatar}</div>
        <div class="msg-content-wrapper">
            <div class="msg-meta"><span>${role === 'user' ? 'You' : 'DocuAI'}</span><span>${timeStr}</span></div>
            <div class="msg-bubble">${renderedContent}</div>
            ${sourceCards}
            ${role === 'assistant' ? '<div class="msg-actions"><button class="msg-action-btn copy-btn">Copy</button></div>' : ''}
        </div>
    `;

    DOM.chatStream.appendChild(row);
    DOM.chatStream.scrollTop = DOM.chatStream.scrollHeight;

    // Event listeners for source cards
    row.querySelectorAll('.source-card').forEach(card => {
        card.addEventListener('click', () => {
            try {
                const sData = JSON.parse(card.dataset.source);
                getEl('sourceModalTitle').textContent = `${sData.source} — Page ${sData.page || '?'}`;
                getEl('sourceModalBody').textContent = sData.excerpt || sData.text || 'No excerpt available';
                DOM.sourceModal.classList.add('active');
            } catch {}
        });
    });

    // Copy button
    row.querySelectorAll('.copy-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            try {
                const text = btn.closest('.msg-content-wrapper').querySelector('.msg-bubble').textContent;
                await navigator.clipboard.writeText(text);
                showToast('Copied to clipboard', 'success');
            } catch { showToast('Copy failed', 'error'); }
        });
    });
}

function appendStreamingMessage() {
    if (DOM.chatEmptyState) DOM.chatEmptyState.style.display = 'none';
    const emptyState = DOM.chatStream.querySelector('.chat-empty-state');
    if (emptyState) emptyState.style.display = 'none';

    const row = document.createElement('div');
    row.className = 'msg-row msg-ai';
    row.id = 'streamingMsg';
    const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    row.innerHTML = `
        <div class="msg-avatar">🤖</div>
        <div class="msg-content-wrapper">
            <div class="msg-meta"><span>DocuAI</span><span>${timeStr}</span></div>
            <div class="msg-bubble"><span class="loading-dots"><span></span><span></span><span></span></span></div>
            <div class="sources-deck" id="streamingSources"></div>
        </div>
    `;
    DOM.chatStream.appendChild(row);
    DOM.chatStream.scrollTop = DOM.chatStream.scrollHeight;
    return row;
}

async function triggerQuery() {
    const question = DOM.queryInput.value.trim();
    if (!question || STATE.isQuerying) return;

    STATE.isQuerying = true;
    DOM.sendQueryBtn.disabled = true;
    DOM.queryInput.value = '';

    appendMessage('user', question);

    if (STATE.isStreaming) {
        await streamQuery(question);
    } else {
        await syncQuery(question);
    }

    STATE.isQuerying = false;
    DOM.sendQueryBtn.disabled = false;
    refreshStatus();
}

async function syncQuery(question) {
    const loadingRow = appendStreamingMessage();
    try {
        const data = await apiCall('/query', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question,
                session_id: STATE.currentSession,
                source_filter: DOM.sourceFilter.value || null,
            }),
        });
        loadingRow.remove();
        appendMessage('assistant', data.answer, data.sources);
    } catch (e) {
        loadingRow.remove();
        appendMessage('assistant', `⚠️ Error: ${e.message}`);
        showToast(e.message, 'error');
    }
}

async function streamQuery(question) {
    const streamRow = appendStreamingMessage();
    const bubble = streamRow.querySelector('.msg-bubble');
    const sourcesDeck = streamRow.querySelector('#streamingSources');

    try {
        const resp = await fetch(`${API}/query-stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question,
                session_id: STATE.currentSession,
                source_filter: DOM.sourceFilter.value || null,
            }),
        });

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let rawAnswer = '';
        let sources = [];

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const text = decoder.decode(value, { stream: true });
            const lines = text.split('\n');

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const payload = line.slice(6).trim();
                if (payload === '[DONE]') continue;

                try {
                    const json = JSON.parse(payload);
                    if (json.sources) {
                        sources = json.sources;
                        if (sourcesDeck) {
                            sourcesDeck.innerHTML = sources.map((s, i) =>
                                `<div class="source-card" data-idx="${i}" data-source='${escapeHtml(JSON.stringify(s))}'>`
                                + `📄 ${escapeHtml(s.source || 'unknown')} (p.${s.page || '?'})`
                                + `</div>`
                            ).join('');
                        }
                    }
                    if (json.delta) {
                        rawAnswer += json.delta;
                        bubble.innerHTML = renderMarkdown(rawAnswer);
                    }
                } catch {}
            }
        }

        // Add copy button and source event listeners
        const actionsDiv = document.createElement('div');
        actionsDiv.className = 'msg-actions';
        actionsDiv.innerHTML = '<button class="msg-action-btn copy-btn">Copy</button>';
        streamRow.querySelector('.msg-content-wrapper').appendChild(actionsDiv);

        streamRow.querySelectorAll('.source-card').forEach(card => {
            card.addEventListener('click', () => {
                try {
                    const sData = JSON.parse(card.dataset.source);
                    getEl('sourceModalTitle').textContent = `${sData.source} — Page ${sData.page || '?'}`;
                    getEl('sourceModalBody').textContent = sData.excerpt || 'No excerpt';
                    DOM.sourceModal.classList.add('active');
                } catch {}
            });
        });

        actionsDiv.querySelector('.copy-btn').addEventListener('click', async () => {
            try {
                await navigator.clipboard.writeText(rawAnswer);
                showToast('Copied to clipboard', 'success');
            } catch { showToast('Copy failed', 'error'); }
        });

        streamRow.removeAttribute('id');

    } catch (e) {
        bubble.innerHTML = renderMarkdown(`⚠️ Streaming failed: ${e.message}`);
        showToast(e.message, 'error');
    }
    DOM.chatStream.scrollTop = DOM.chatStream.scrollHeight;
}

// ── Input Event Handlers ─────────────────────────────────────────────────────
DOM.sendQueryBtn.addEventListener('click', triggerQuery);
DOM.queryInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); triggerQuery(); }
});
DOM.queryInput.addEventListener('input', () => {
    DOM.queryInput.style.height = 'auto';
    DOM.queryInput.style.height = Math.min(DOM.queryInput.scrollHeight, 150) + 'px';
});
DOM.streamToggle.addEventListener('click', () => {
    STATE.isStreaming = !STATE.isStreaming;
    DOM.streamToggle.classList.toggle('active', STATE.isStreaming);
    DOM.streamToggle.querySelector('span').textContent = STATE.isStreaming ? 'ON' : 'OFF';
    localStorage.setItem('streaming', JSON.stringify(STATE.isStreaming));
});
getEl('resetFilterBtn').addEventListener('click', () => { DOM.sourceFilter.value = ''; });
getEl('clearChatBtn').addEventListener('click', () => {
    DOM.chatStream.innerHTML = '';
    const emptyState = getEl('view-chat').querySelector('.chat-empty-state');
    if (emptyState) emptyState.style.display = '';
});
getEl('exportChatBtn').addEventListener('click', () => {
    const msgs = DOM.chatStream.querySelectorAll('.msg-row');
    let text = '';
    msgs.forEach(m => {
        const role = m.classList.contains('msg-user') ? 'User' : 'DocuAI';
        const content = m.querySelector('.msg-bubble')?.textContent || '';
        text += `${role}: ${content}\n\n`;
    });
    const blob = new Blob([text], { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `chat_export_${new Date().toISOString().slice(0, 10)}.txt`;
    a.click();
});

// Quick prompts
document.querySelectorAll('.suggestion-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        DOM.queryInput.value = btn.textContent.trim();
        triggerQuery();
    });
});

// Quick upload
getEl('quickUploadBtn').addEventListener('click', () => {
    document.querySelector('.nav-btn[data-target="view-documents"]')?.click();
});

// ── Documents ────────────────────────────────────────────────────────────────
async function loadDocuments() {
    try {
        const docs = await apiCall('/documents');
        STATE.allDocuments = docs;
        renderDocumentsTable(docs);
        updateCompareSelects(docs);
    } catch { DOM.documentTableBody.innerHTML = '<tr><td colspan="5" class="text-muted">Unable to load documents</td></tr>'; }
}

function renderDocumentsTable(docs) {
    if (!docs.length) {
        DOM.documentTableBody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:32px;">No documents indexed. Upload files above to get started.</td></tr>';
        return;
    }
    DOM.documentTableBody.innerHTML = docs.map(d => `
        <tr>
            <td><span style="cursor:pointer;color:var(--accent-primary)" onclick="openPreview('${escapeHtml(d.filename)}')">${escapeHtml(d.filename)}</span></td>
            <td>${escapeHtml(d.suffix || '-')}</td>
            <td>${d.size_mb ? d.size_mb.toFixed(2) + ' MB' : '-'}</td>
            <td>${d.chunks || 0} chunks</td>
            <td><button class="btn-danger-outline" style="padding:6px 12px;font-size:12px" onclick="deleteDoc('${escapeHtml(d.filename)}')">Delete</button></td>
        </tr>
    `).join('');
}

DOM.documentSearchInput.addEventListener('input', (e) => {
    const q = e.target.value.toLowerCase();
    const filtered = STATE.allDocuments.filter(d => d.filename.toLowerCase().includes(q));
    renderDocumentsTable(filtered);
});

function updateCompareSelects(docs) {
    const options = '<option value="">Select Document</option>' + docs.map(d => `<option value="${escapeHtml(d.filename)}">${escapeHtml(d.filename)}</option>`).join('');
    DOM.compareSelectA.innerHTML = options;
    DOM.compareSelectB.innerHTML = options;
}

window.deleteDoc = async (filename) => {
    if (!confirm(`Delete "${filename}" from the index?`)) return;
    try {
        await apiCall(`/document/${encodeURIComponent(filename)}`, { method: 'DELETE' });
        showToast(`Deleted: ${filename}`, 'success');
        loadDocuments();
        refreshStatus();
    } catch (e) { showToast(e.message, 'error'); }
};

window.openPreview = (filename) => {
    getEl('previewModalTitle').textContent = filename;
    const ext = filename.split('.').pop().toLowerCase();
    const frame = getEl('previewFrame');
    const unsupported = getEl('previewUnsupported');
    const url = `/download/${encodeURIComponent(filename)}`;
    const previewable = ['pdf', 'txt', 'png', 'jpg', 'jpeg', 'md'];
    if (previewable.includes(ext)) {
        frame.style.display = 'block'; unsupported.style.display = 'none'; frame.src = url;
    } else {
        frame.style.display = 'none'; unsupported.style.display = 'block';
        getEl('previewDownloadBtn').href = url;
    }
    getEl('previewModal').classList.add('active');
};

// ── File Upload ──────────────────────────────────────────────────────────────
const dropZone = getEl('dropZone');
const fileInput = getEl('bulkFileInput');

getEl('triggerFileBtn').addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', (e) => { e.preventDefault(); dropZone.classList.remove('dragover'); handleFiles(e.dataTransfer.files); });
fileInput.addEventListener('change', () => { handleFiles(fileInput.files); fileInput.value = ''; });

async function handleFiles(files) {
    for (const file of files) {
        const progressBox = getEl('uploadProgressBox');
        const bar = getEl('uploadBar');
        const fname = getEl('uploadFilename');
        const pct = getEl('uploadPercent');

        progressBox.style.display = 'block';
        fname.textContent = file.name;
        bar.style.width = '0%';
        pct.textContent = '0%';

        const formData = new FormData();
        formData.append('file', file);

        try {
            // Use XHR for progress tracking
            await new Promise((resolve, reject) => {
                const xhr = new XMLHttpRequest();
                xhr.open('POST', `${API}/ingest`);
                xhr.upload.onprogress = (e) => {
                    if (e.lengthComputable) {
                        const p = Math.round((e.loaded / e.total) * 100);
                        bar.style.width = p + '%';
                        pct.textContent = p + '%';
                    }
                };
                xhr.onload = () => {
                    bar.style.width = '100%';
                    pct.textContent = '100%';
                    if (xhr.status === 200) {
                        const data = JSON.parse(xhr.responseText);
                        showToast(`Indexed "${data.file}" — ${data.chunks} chunks in ${data.time_seconds}s`, 'success');
                        resolve();
                    } else {
                        const err = JSON.parse(xhr.responseText);
                        reject(new Error(err.detail || 'Upload failed'));
                    }
                };
                xhr.onerror = () => reject(new Error('Network error'));
                xhr.send(formData);
            });
        } catch (e) {
            showToast(`Failed: ${e.message}`, 'error');
        }
    }
    setTimeout(() => { getEl('uploadProgressBox').style.display = 'none'; }, 1500);
    loadDocuments();
    refreshStatus();
}

// ── URL Ingestion ────────────────────────────────────────────────────────────
getEl('ingestUrlBtn').addEventListener('click', async () => {
    const url = getEl('urlIngestInput').value.trim();
    if (!url) { showToast('Enter a URL', 'error'); return; }
    showToast('Ingesting URL...', 'info');
    try {
        const data = await apiCall('/ingest/url', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url }),
        });
        showToast(`Indexed: ${data.file} — ${data.chunks} chunks`, 'success');
        getEl('urlIngestInput').value = '';
        loadDocuments();
        refreshStatus();
    } catch (e) { showToast(e.message, 'error'); }
});

// ── Export / Import (v3.1 — F5) ──────────────────────────────────────────────
getEl('exportIndexBtn').addEventListener('click', async () => {
    try {
        showToast('Exporting index...', 'info');
        const resp = await fetch(`${API}/export`);
        if (!resp.ok) throw new Error('Export failed');
        const blob = await resp.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `docuai_index_${new Date().toISOString().slice(0, 10)}.zip`;
        a.click();
        showToast('Index exported!', 'success');
    } catch (e) { showToast(e.message, 'error'); }
});

getEl('importIndexInput').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    try {
        showToast('Importing index...', 'info');
        const data = await apiCall('/import', { method: 'POST', body: formData });
        showToast(`Imported ${data.imported_vectors || 0} vectors!`, 'success');
        loadDocuments();
        refreshStatus();
    } catch (err) { showToast(err.message, 'error'); }
    e.target.value = '';
});

// ── Clear Index ──────────────────────────────────────────────────────────────
getEl('clearIndexBtn').addEventListener('click', async () => {
    if (!confirm('Clear the ENTIRE vector index? This cannot be undone.')) return;
    try {
        await apiCall('/clear', { method: 'POST' });
        showToast('Index cleared', 'success');
        loadDocuments();
        refreshStatus();
    } catch (e) { showToast(e.message, 'error'); }
});

// ── Compare ──────────────────────────────────────────────────────────────────
getEl('runCompareBtn').addEventListener('click', async () => {
    const a = DOM.compareSelectA.value, b = DOM.compareSelectB.value;
    if (!a || !b) { showToast('Select both documents', 'error'); return; }
    DOM.compareResult.innerHTML = '<div class="loading-dots"><span></span><span></span><span></span></div>';
    try {
        const data = await apiCall('/compare', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ doc_a: a, doc_b: b, question: getEl('compareQuestionInput').value }),
        });
        DOM.compareResult.innerHTML = renderMarkdown(data.comparison || data.analysis || JSON.stringify(data));
    } catch (e) { DOM.compareResult.innerHTML = `<span style="color:var(--danger)">Error: ${escapeHtml(e.message)}</span>`; }
});

getEl('swapCompareBtn')?.addEventListener('click', () => {
    const a = DOM.compareSelectA.value, b = DOM.compareSelectB.value;
    DOM.compareSelectA.value = b; DOM.compareSelectB.value = a;
});

// ── Extract ──────────────────────────────────────────────────────────────────
getEl('runExtractBtn').addEventListener('click', async () => {
    const fields = DOM.extractFields.value.split('\n').map(l => l.trim()).filter(Boolean);
    if (!fields.length) { showToast('Specify extraction keys', 'error'); return; }
    DOM.extractResult.textContent = 'Extracting...';
    try {
        const data = await apiCall('/extract', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ fields, context_query: DOM.extractContext.value }),
        });
        DOM.extractResult.textContent = JSON.stringify(data.extracted_data || data.fields || data, null, 2);
    } catch (e) { DOM.extractResult.textContent = e.message; }
});

getEl('copyExtractBtn')?.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(DOM.extractResult.textContent); showToast('Copied', 'success'); } catch { showToast('Copy failed', 'error'); }
});

// ── Summarize ────────────────────────────────────────────────────────────────
getEl('runSummaryBtn').addEventListener('click', async () => {
    DOM.summaryResult.innerHTML = '<div class="loading-dots"><span></span><span></span><span></span></div>';
    try {
        const data = await apiCall('/summarize', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ topic: DOM.summaryTopic.value.trim() || 'the entire embedding index' }),
        });
        DOM.summaryResult.innerHTML = renderMarkdown(data.summary);
    } catch (e) { DOM.summaryResult.innerHTML = escapeHtml(e.message); }
});
getEl('copySummaryBtn')?.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(DOM.summaryResult.textContent); showToast('Copied', 'success'); } catch { showToast('Copy failed', 'error'); }
});

// ── Semantic Search (v3.1 — F7) ──────────────────────────────────────────────
getEl('runSearchBtn').addEventListener('click', runSemanticSearch);
DOM.searchInput?.addEventListener('keydown', (e) => { if (e.key === 'Enter') runSemanticSearch(); });

async function runSemanticSearch() {
    const q = DOM.searchInput.value.trim();
    if (!q) { showToast('Enter a search query', 'error'); return; }
    DOM.searchResults.innerHTML = '<div class="loading-dots" style="padding:40px;text-align:center"><span></span><span></span><span></span></div>';
    try {
        const data = await apiCall('/search', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: q, top_k: 20, source_filter: DOM.searchSourceFilter.value || null }),
        });
        const results = data.results || [];
        if (!results.length) {
            DOM.searchResults.innerHTML = '<div class="glass-panel pd-6 text-center text-muted">No results found</div>';
            return;
        }
        DOM.searchResults.innerHTML = results.map((r, i) => `
            <div class="search-result-card">
                <div class="search-result-header">
                    <span class="search-result-source">📄 ${escapeHtml(r.source)} — Page ${r.page || '?'}</span>
                    <span class="search-result-score">Score: ${r.score.toFixed(6)}</span>
                </div>
                <div class="search-result-text">${escapeHtml(r.text?.substring(0, 400) || '')}${r.text?.length > 400 ? '...' : ''}</div>
                <div class="search-result-meta">
                    <span>Type: ${r.chunk_type || 'text'}</span>
                    <span>Rank: #${i + 1}</span>
                </div>
            </div>
        `).join('');
    } catch (e) { DOM.searchResults.innerHTML = `<div class="glass-panel pd-6 text-center" style="color:var(--danger)">Error: ${escapeHtml(e.message)}</div>`; }
}

// ── Batch Q&A (v3.1 — F14) ──────────────────────────────────────────────────
getEl('runBatchBtn').addEventListener('click', async () => {
    const questions = DOM.batchInput.value.split('\n').map(l => l.trim()).filter(Boolean);
    if (!questions.length) { showToast('Enter at least one question', 'error'); return; }
    DOM.batchResultPanel.style.display = 'block';
    DOM.batchResultBody.innerHTML = '<tr><td colspan="4" class="text-center"><div class="loading-dots"><span></span><span></span><span></span></div> Processing...</td></tr>';
    try {
        const data = await apiCall('/query/batch', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ questions }),
        });
        STATE.batchResults = data.results || [];
        DOM.batchResultBody.innerHTML = STATE.batchResults.map((r, i) => `
            <tr>
                <td>${i + 1}</td>
                <td>${escapeHtml(r.question)}</td>
                <td class="markdown-body">${renderMarkdown(r.answer || '-')}</td>
                <td>${r.response_time_ms || 0}ms</td>
            </tr>
        `).join('');
        getEl('exportBatchBtn').style.display = 'inline-block';
        showToast(`Batch complete: ${STATE.batchResults.length} answers`, 'success');
    } catch (e) {
        DOM.batchResultBody.innerHTML = `<tr><td colspan="4" style="color:var(--danger)">${escapeHtml(e.message)}</td></tr>`;
    }
});

getEl('exportBatchBtn').addEventListener('click', () => {
    if (!STATE.batchResults.length) return;
    let csv = 'Question,Answer,ResponseTime_ms\n';
    STATE.batchResults.forEach(r => {
        csv += `"${r.question.replace(/"/g, '""')}","${(r.answer || '').replace(/"/g, '""')}",${r.response_time_ms || 0}\n`;
    });
    const blob = new Blob([csv], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `batch_qa_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    showToast('CSV exported', 'success');
});

// ── Knowledge Graph (v3.1 — F13) ────────────────────────────────────────────
let kgData = null;

async function loadKnowledgeGraph() {
    try {
        kgData = await apiCall('/knowledge-graph');
        renderKgStats(kgData);
        renderKgCanvas(kgData);
        renderKgEntityList(kgData);
    } catch (e) {
        DOM.kgStatsRow.innerHTML = `<div class="kg-stat" style="color:var(--danger)">Failed to load: ${escapeHtml(e.message)}</div>`;
    }
}

function renderKgStats(data) {
    DOM.kgStatsRow.innerHTML = `
        <div class="kg-stat">Entities: <strong>${data.total_entities || 0}</strong></div>
        <div class="kg-stat">Relationships: <strong>${data.total_relationships || 0}</strong></div>
        <div class="kg-stat">Node Types: <strong>${new Set((data.nodes || []).map(n => n.type)).size}</strong></div>
    `;
}

let kgAnimId = null;

function renderKgCanvas(data) {
    const canvas = DOM.kgCanvas;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.parentElement.getBoundingClientRect();
    const W = rect.width, H = rect.height || 600;

    canvas.width = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width = W + 'px';
    canvas.style.height = H + 'px';
    ctx.scale(dpr, dpr);

    if (kgAnimId) cancelAnimationFrame(kgAnimId);

    // Sort nodes by mentions so most important are first
    const allNodes = (data.nodes || []).sort((a, b) => (b.mentions || 0) - (a.mentions || 0));
    const nodes = allNodes.slice(0, 50);
    const nodeIds = new Set(nodes.map(n => n.id));
    // Only keep edges between visible nodes
    const edges = (data.edges || []).filter(e => nodeIds.has(e.source) && nodeIds.has(e.target));

    if (!nodes.length) {
        ctx.clearRect(0, 0, W, H);
        ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--text-muted');
        ctx.font = '16px Inter';
        ctx.textAlign = 'center';
        ctx.fillText('No knowledge graph data yet. Ingest documents to build the graph.', W / 2, H / 2);
        return;
    }

    // Initialize physics — spread nodes in a large circle initially
    const nodeMap = {};
    const maxMentions = Math.max(...nodes.map(n => n.mentions || 1));
    nodes.forEach((n, i) => {
        const angle = (2 * Math.PI * i) / nodes.length;
        const spread = Math.min(W, H) * 0.42;
        n.x = W / 2 + Math.cos(angle) * spread * (0.6 + Math.random() * 0.4);
        n.y = H / 2 + Math.sin(angle) * spread * (0.6 + Math.random() * 0.4);
        n.vx = 0; n.vy = 0;
        const norm = (n.mentions || 1) / maxMentions;
        n.r = 4 + norm * 14; // 4px to 18px — much smaller
        n.mass = 1 + norm * 3;
        nodeMap[n.id] = n;
    });

    const isDark = STATE.theme === 'dark';
    const colors = {
        MONEY: '#10b981', DATE: '#f59e0b', EMAIL: '#60a5fa',
        PHONE: '#a78bfa', PERCENTAGE: '#f87171', ENTITY: '#22d3ee',
    };

    // Determine which nodes get labels (top 25 by mentions)
    const labelSet = new Set(nodes.slice(0, 25).map(n => n.id));

    let alpha = 1.0;
    let frame = 0;

    function tick() {
        if (alpha < 0.003) {
            drawFrame(); // Final render
            return;
        }
        alpha *= 0.965;
        frame++;

        // ── Repulsion (Coulomb) ──
        for (let i = 0; i < nodes.length; i++) {
            for (let j = i + 1; j < nodes.length; j++) {
                let dx = nodes[i].x - nodes[j].x;
                let dy = nodes[i].y - nodes[j].y;
                let distSq = dx * dx + dy * dy;
                let dist = Math.sqrt(distSq) || 1;
                if (dist < 350) {
                    // Strong inverse-square repulsion
                    let force = 2000 / (distSq + 100) * alpha;
                    let fx = dx / dist * force;
                    let fy = dy / dist * force;
                    nodes[i].vx += fx; nodes[i].vy += fy;
                    nodes[j].vx -= fx; nodes[j].vy -= fy;
                }
            }
        }

        // ── Attraction (Springs on edges) ──
        edges.forEach(e => {
            const s = nodeMap[e.source], t = nodeMap[e.target];
            if (!s || !t) return;
            let dx = t.x - s.x;
            let dy = t.y - s.y;
            let dist = Math.sqrt(dx * dx + dy * dy) || 1;
            let idealLen = 120;
            let force = (dist - idealLen) * 0.004 * alpha;
            let fx = dx / dist * force;
            let fy = dy / dist * force;
            s.vx += fx; s.vy += fy;
            t.vx -= fx; t.vy -= fy;
        });

        // ── Gentle gravity toward center ──
        nodes.forEach(n => {
            n.vx += (W / 2 - n.x) * 0.001 * alpha;
            n.vy += (H / 2 - n.y) * 0.001 * alpha;
            // Velocity damping
            n.vx *= 0.75;
            n.vy *= 0.75;
            n.x += n.vx;
            n.y += n.vy;
            // Bounds with padding
            n.x = Math.max(40, Math.min(W - 40, n.x));
            n.y = Math.max(40, Math.min(H - 40, n.y));
        });

        // Draw every 2nd frame for performance
        if (frame % 2 === 0) drawFrame();

        kgAnimId = requestAnimationFrame(tick);
    }

    function drawFrame() {
        ctx.clearRect(0, 0, W, H);

        // ── Draw edges ──
        edges.forEach(e => {
            const s = nodeMap[e.source], t = nodeMap[e.target];
            if (!s || !t) return;
            const w = Math.min(e.weight || 1, 10);
            ctx.strokeStyle = isDark
                ? `rgba(255,255,255,${0.03 + w * 0.015})`
                : `rgba(0,0,0,${0.04 + w * 0.015})`;
            ctx.lineWidth = 0.5 + w * 0.12;
            ctx.beginPath();
            // Slight curve for visual appeal
            const mx = (s.x + t.x) / 2 + (s.y - t.y) * 0.08;
            const my = (s.y + t.y) / 2 + (t.x - s.x) * 0.08;
            ctx.moveTo(s.x, s.y);
            ctx.quadraticCurveTo(mx, my, t.x, t.y);
            ctx.stroke();
        });

        // ── Draw nodes ──
        nodes.forEach(n => {
            const color = colors[n.type] || '#22d3ee';

            // Soft glow
            ctx.beginPath();
            ctx.arc(n.x, n.y, n.r + 3, 0, Math.PI * 2);
            ctx.fillStyle = color + '18';
            ctx.fill();

            // Filled circle with border
            ctx.beginPath();
            ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
            ctx.fillStyle = color + '30';
            ctx.fill();
            ctx.strokeStyle = color;
            ctx.lineWidth = 1.8;
            ctx.stroke();
        });

        // ── Draw labels (only for important nodes, with collision avoidance) ──
        const placedLabels = []; // {x, y, w, h}
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';

        nodes.forEach(n => {
            if (!labelSet.has(n.id)) return;
            const label = n.id.length > 18 ? n.id.substring(0, 16) + '…' : n.id;
            const fontSize = Math.max(9, Math.min(12, 8 + n.r * 0.3));
            ctx.font = `500 ${fontSize}px Inter`;
            const tw = ctx.measureText(label).width;
            const lx = n.x;
            const ly = n.y + n.r + 4;
            const lw = tw + 6;
            const lh = fontSize + 4;

            // Check collision with already placed labels
            const collides = placedLabels.some(p =>
                Math.abs(lx - p.x) < (lw + p.w) / 2 && Math.abs(ly - p.y) < (lh + p.h) / 2
            );
            if (collides) return;
            placedLabels.push({ x: lx, y: ly, w: lw, h: lh });

            // Draw label background pill
            ctx.fillStyle = isDark ? 'rgba(15,23,42,0.85)' : 'rgba(255,255,255,0.9)';
            const rx = lx - tw / 2 - 3;
            const ry = ly - 1;
            ctx.beginPath();
            ctx.roundRect(rx, ry, lw, lh, 3);
            ctx.fill();

            // Draw label text
            ctx.fillStyle = isDark ? '#e2e8f0' : '#1e293b';
            ctx.fillText(label, lx, ly);
        });
    }

    tick();
}

function renderKgEntityList(data) {
    const nodes = (data.nodes || []).sort((a, b) => b.mentions - a.mentions).slice(0, 50);
    DOM.kgEntityList.innerHTML = nodes.map(n => `
        <div class="kg-entity-item">
            <span>${escapeHtml(n.id)} <span class="text-muted">(${n.mentions}×)</span></span>
            <span class="kg-entity-type">${n.type}</span>
        </div>
    `).join('') || '<div class="text-muted" style="padding:16px">No entities extracted yet</div>';
}

getEl('refreshKgBtn').addEventListener('click', loadKnowledgeGraph);
getEl('resetKgBtn').addEventListener('click', async () => {
    if (!confirm('Clear the entire knowledge graph?')) return;
    try {
        await apiCall('/knowledge-graph/reset', { method: 'POST' });
        showToast('Knowledge graph cleared', 'success');
        loadKnowledgeGraph();
    } catch {}
});

// ── Analytics ────────────────────────────────────────────────────────────────
async function loadAnalytics() {
    try {
        const data = await apiCall('/analytics');
        DOM.analyticsDash.innerHTML = `
            <div class="stat-box"><span class="s-label">Total Vectors</span><span class="s-value">${data.total_vectors || 0}</span></div>
            <div class="stat-box"><span class="s-label">Index Size</span><span class="s-value">${(data.storage?.index_size_mb || 0).toFixed(2)} MB</span></div>
            <div class="stat-box"><span class="s-label">Cache Hits</span><span class="s-value">${data.cache?.hits || 0}</span></div>
            <div class="stat-box"><span class="s-label">Unique Sources</span><span class="s-value">${(data.sources || []).length}</span></div>
            <div class="stat-box"><span class="s-label">Upload Storage</span><span class="s-value">${(data.storage?.uploads_size_mb || 0).toFixed(2)} MB</span></div>
            <div class="stat-box"><span class="s-label">LLM Status</span><span class="s-value" style="font-size:16px">${data.ollama === 'connected' ? '🟢 Online' : '🟡 Local'}</span></div>
        `;
    } catch {}
}

async function loadQueryAnalytics() {
    try {
        const data = await apiCall('/query-analytics');
        DOM.queryAnalyticsDash.innerHTML = `
            <div class="stat-box"><span class="s-label">Total Queries</span><span class="s-value">${data.total_queries || 0}</span></div>
            <div class="stat-box"><span class="s-label">Today</span><span class="s-value">${data.queries_today || 0}</span></div>
            <div class="stat-box"><span class="s-label">Avg Response</span><span class="s-value">${data.avg_response_time_ms || 0}ms</span></div>
            <div class="stat-box"><span class="s-label">Cached</span><span class="s-value">${data.cached_queries || 0}</span></div>
            <div class="stat-box"><span class="s-label">Success Rate</span><span class="s-value">${data.total_queries ? Math.round((data.successful_queries / data.total_queries) * 100) : 100}%</span></div>
            <div class="stat-box"><span class="s-label">Failed</span><span class="s-value">${data.failed_queries || 0}</span></div>
        `;
    } catch {}
}

getEl('refreshAnalyticsBtn').addEventListener('click', () => { loadAnalytics(); loadQueryAnalytics(); });

// ── RAGAS Metrics ────────────────────────────────────────────────────────────
async function loadRagas() {
    try {
        const data = await apiCall('/evaluate/dashboard');
        DOM.ragasDash.innerHTML = `
            <div class="stat-box"><span class="s-label">Evaluations</span><span class="s-value">${data.total_evaluations || 0}</span></div>
            <div class="stat-box"><span class="s-label">Avg Quality</span><span class="s-value">${((data.avg_overall || 0) * 100).toFixed(1)}%</span></div>
            <div class="stat-box"><span class="s-label">Faithfulness</span><span class="s-value">${((data.avg_faithfulness || 0) * 100).toFixed(1)}%</span></div>
            <div class="stat-box"><span class="s-label">Relevancy</span><span class="s-value">${((data.avg_answer_relevancy || 0) * 100).toFixed(1)}%</span></div>
        `;

        const history = await apiCall('/evaluate/history?limit=20');
        DOM.ragasHistory.innerHTML = '';
        if (!history.length) {
            DOM.ragasHistory.innerHTML = '<tr><td colspan="2" class="text-center text-muted">No evaluations run yet.</td></tr>';
            return;
        }
        history.forEach(h => {
            const tr = document.createElement('tr');
            const score = ((h.overall_score || 0) * 100).toFixed(0);
            tr.innerHTML = `<td>${escapeHtml(h.question)}</td><td><span class="pill-btn" style="color:${score > 80 ? 'var(--success)' : 'var(--warning)'}">${score}%</span></td>`;
            DOM.ragasHistory.appendChild(tr);
        });
    } catch {}
}
getEl('refreshRagasBtn').addEventListener('click', loadRagas);
getEl('purgeRagasBtn').addEventListener('click', async () => {
    if (!confirm('Clear all RAGAS evaluation metrics?')) return;
    try { await apiCall('/evaluate/clear', { method: 'POST' }); loadRagas(); showToast('Purged', 'success'); } catch {}
});

// ── Settings ─────────────────────────────────────────────────────────────────
getEl('settingsBtn').addEventListener('click', () => DOM.settingsModal.classList.add('active'));
getEl('shortcutsBtn')?.addEventListener('click', () => DOM.shortcutsModal.classList.add('active'));
getEl('clearCacheBtn').addEventListener('click', async () => {
    try { const r = await apiCall('/cache/clear', { method: 'POST' }); showToast(`Cache purged: ${r.entries_removed} entries`, 'success'); DOM.settingsModal.classList.remove('active'); } catch {}
});
getEl('clearAnalyticsCacheBtn')?.addEventListener('click', async () => {
    try { await apiCall('/query-analytics/clear', { method: 'POST' }); showToast('Analytics cleared', 'success'); DOM.settingsModal.classList.remove('active'); } catch {}
});

// ── Modals ────────────────────────────────────────────────────────────────────
document.querySelectorAll('.close-modal-btn').forEach(btn => {
    btn.addEventListener('click', () => btn.closest('.modal-overlay')?.classList.remove('active'));
});
document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.classList.remove('active'); });
});

// ── Keyboard Shortcuts ───────────────────────────────────────────────────────
document.addEventListener('keydown', (e) => {
    const isMac = navigator.platform.toUpperCase().includes('MAC');
    const cmdOrCtrl = isMac ? e.metaKey : e.ctrlKey;

    if (cmdOrCtrl && e.key.toLowerCase() === 'k') { e.preventDefault(); DOM.queryInput.focus(); return; }
    if (cmdOrCtrl && e.key === 'Enter') { if (!STATE.isQuerying) { e.preventDefault(); triggerQuery(); } return; }
    if (e.altKey && e.key.toLowerCase() === 's') { e.preventDefault(); DOM.streamToggle.click(); return; }
    if (e.altKey && e.key.toLowerCase() === 'b') { e.preventDefault(); DOM.sidebarToggle.click(); return; }
    if (e.key === 'Escape') { document.querySelectorAll('.modal-overlay.active').forEach(m => m.classList.remove('active')); }
});

// ── Initialization ───────────────────────────────────────────────────────────
applyTheme(STATE.theme);
DOM.streamToggle.classList.toggle('active', STATE.isStreaming);
DOM.streamToggle.querySelector('span').textContent = STATE.isStreaming ? 'ON' : 'OFF';
refreshStatus();
loadSessions();
loadDocuments();
setInterval(refreshStatus, 30000);
