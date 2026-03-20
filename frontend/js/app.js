// ═══════════════════════════════════════════════════════════════════════════
// Document AI + RAG Pipeline — Frontend Application
//
// Features:
//   • File upload via drag & drop or click
//   • Real-time chat interface with 4 modes (Q&A, Summary, Extract, Table)
//   • Local storage for query history
//   • Status polling & Ollama connectivity indicator
//   • Source citations display
// ═══════════════════════════════════════════════════════════════════════════

const API_BASE = window.location.origin;

// ── State ─────────────────────────────────────────────────────────────────
const state = {
    mode: 'qa',                // 'qa' | 'summary' | 'extract' | 'table'
    isProcessing: false,
    history: JSON.parse(localStorage.getItem('docai_history') || '[]'),
    documents: JSON.parse(localStorage.getItem('docai_documents') || '[]'),
};

// ── DOM References ────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

const els = {
    uploadZone:     $('uploadZone'),
    fileInput:      $('fileInput'),
    progressContainer: $('progressContainer'),
    progressFill:   $('progressFill'),
    progressText:   $('progressText'),
    docList:        $('docList'),
    historyList:    $('historyList'),
    chatMessages:   $('chatMessages'),
    welcomeScreen:  $('welcomeScreen'),
    queryInput:     $('queryInput'),
    sendBtn:        $('sendBtn'),
    statusDot:      $('statusDot'),
    statusText:     $('statusText'),
    clearBtn:       $('clearBtn'),
    fieldsInput:    $('fieldsInput'),
    fieldsField:    $('fieldsField'),
    modeTabs:       $('modeTabs'),
};

// Configure marked.js with highlight.js integration
if (typeof marked !== 'undefined' && window.hljs) {
    marked.setOptions({
        highlight: function(code, lang) {
            const language = hljs.getLanguage(lang) ? lang : 'plaintext';
            return hljs.highlight(code, { language }).value;
        },
        breaks: true,
        gfm: true
    });
}

// ── Initialization ────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initUpload();
    initTabs();
    initInput();
    initClearBtn();
    renderDocList();
    renderHistoryList();
    checkStatus();
    setInterval(checkStatus, 30000); // poll every 30s
});

// ── Upload ────────────────────────────────────────────────────────────────
function initUpload() {
    const zone = els.uploadZone;
    const input = els.fileInput;

    zone.addEventListener('click', () => input.click());
    input.addEventListener('change', (e) => {
        if (e.target.files.length) uploadFile(e.target.files[0]);
    });

    // Drag & drop
    zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        zone.classList.add('dragover');
    });
    zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('dragover');
        if (e.dataTransfer.files.length) uploadFile(e.dataTransfer.files[0]);
    });
}

async function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    // Show progress
    els.progressContainer.style.display = 'block';
    els.progressFill.style.width = '10%';
    els.progressText.textContent = `Uploading ${file.name}…`;

    try {
        // Simulate progress during upload
        let progress = 10;
        const progressInterval = setInterval(() => {
            progress = Math.min(progress + Math.random() * 15, 85);
            els.progressFill.style.width = `${progress}%`;
        }, 500);

        els.progressText.textContent = 'Processing document (OCR + chunking + embedding)…';

        const resp = await fetch(`${API_BASE}/ingest`, {
            method: 'POST',
            body: formData,
        });

        clearInterval(progressInterval);

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || 'Upload failed');
        }

        const result = await resp.json();

        els.progressFill.style.width = '100%';
        els.progressText.textContent = `✓ ${result.file} — ${result.chunks} chunks indexed in ${result.time_seconds}s`;

        // Save to local storage
        const doc = {
            name: result.file,
            pages: result.pages,
            chunks: result.chunks,
            indexedAt: new Date().toISOString(),
        };
        state.documents = state.documents.filter(d => d.name !== doc.name);
        state.documents.unshift(doc);
        localStorage.setItem('docai_documents', JSON.stringify(state.documents));
        renderDocList();

        // Auto-hide progress after 3 seconds
        setTimeout(() => {
            els.progressContainer.style.display = 'none';
            els.progressFill.style.width = '0%';
        }, 3000);

        checkStatus();

    } catch (err) {
        els.progressFill.style.width = '100%';
        els.progressFill.style.background = 'var(--red)';
        els.progressText.textContent = `✗ Error: ${err.message}`;
        setTimeout(() => {
            els.progressContainer.style.display = 'none';
            els.progressFill.style.width = '0%';
            els.progressFill.style.background = '';
        }, 5000);
    }

    els.fileInput.value = '';
}

// ── Tabs ──────────────────────────────────────────────────────────────────
function initTabs() {
    els.modeTabs.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const mode = tab.dataset.mode;
            state.mode = mode;

            els.modeTabs.querySelectorAll('.tab').forEach(t => t.classList.remove('tab--active'));
            tab.classList.add('tab--active');

            // Show/hide fields input for extract mode
            els.fieldsInput.style.display = mode === 'extract' ? 'block' : 'none';

            // Update placeholder
            const placeholders = {
                qa:      'Ask a question about your documents…',
                summary: 'Enter a topic to summarize (e.g. "payment terms")…',
                extract: 'Optional: narrow down context (e.g. "invoice details")…',
                table:   'Ask a question about a table in your documents…',
            };
            els.queryInput.placeholder = placeholders[mode];
        });
    });
}

// ── Input ─────────────────────────────────────────────────────────────────
function initInput() {
    const input = els.queryInput;
    const btn   = els.sendBtn;

    // Auto-resize
    input.addEventListener('input', () => {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 160) + 'px';
        btn.disabled = !input.value.trim();
    });

    // Enter to send
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (!btn.disabled && !state.isProcessing) sendQuery();
        }
    });

    btn.addEventListener('click', () => {
        if (!state.isProcessing) sendQuery();
    });
}

// ── Send Query ────────────────────────────────────────────────────────────
async function sendQuery() {
    const queryText = els.queryInput.value.trim();
    if (!queryText && state.mode !== 'extract') return;

    state.isProcessing = true;
    els.sendBtn.disabled = true;

    // Hide welcome
    if (els.welcomeScreen) {
        els.welcomeScreen.style.display = 'none';
    }

    // Show user message
    const userLabel = state.mode === 'summary' ? `📋 Summarize: ${queryText}` :
                      state.mode === 'extract' ? `🔧 Extract fields` :
                      state.mode === 'table'   ? `📊 Table: ${queryText}` :
                      queryText;
    addMessage('user', userLabel);

    // Show loading
    const loadingEl = addLoading();

    // Clear input
    els.queryInput.value = '';
    els.queryInput.style.height = 'auto';

    try {
        let resp, result;

        switch (state.mode) {
            case 'qa':
                // Send history along with question
                const historyPayload = state.history.map(h => ({
                    role: h.mode === 'qa' ? "user" : "system",
                    content: h.query
                })).reverse(); // Oldest first

                resp = await fetch(`${API_BASE}/query-stream`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        question: queryText,
                        history: historyPayload
                    }),
                });

                if (!resp.ok) {
                    result = await resp.json();
                    throw new Error(result.detail || 'Query failed');
                }
                
                removeElement(loadingEl);
                
                const reader = resp.body.getReader();
                const decoder = new TextDecoder("utf-8");
                let msgEl = null;
                let rawMarkdown = "";
                let sourcesHtml = "";

                while (true) {
                    const { value, done } = await reader.read();
                    if (done) break;
                    
                    const chunkStr = decoder.decode(value, { stream: true });
                    const lines = chunkStr.split('\n');
                    
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const dataStr = line.slice(6);
                            if (dataStr === '[DONE]') continue;
                            
                            try {
                                const data = JSON.parse(dataStr);
                                
                                if (data.sources) {
                                    // Initial chunk contains formatting sources
                                    msgEl = addAIMessage('', data.sources);
                                    
                                    // Save the source HTML string because we'll overwrite innerHTML when parsing markdown
                                    if (data.sources.length > 0) {
                                        sourcesHtml = `<div class="msg__sources"><div class="msg__sources-title">Sources</div>` +
                                            data.sources.map(s => `<div class="msg__source"><strong>${s.source}</strong> page ${s.page}</div>`).join('') +
                                            `</div>`;
                                    }
                                }
                                
                                if (data.delta && msgEl) {
                                    const bubble = msgEl.querySelector('.msg__bubble');
                                    rawMarkdown += data.delta;
                                    
                                    // Live markdown render + append sources container at bottom
                                    bubble.innerHTML = formatText(rawMarkdown) + sourcesHtml;
                                    scrollToBottom();
                                }
                            } catch (e) {
                                console.warn("Failed to parse SSE JSON chunk", line);
                            }
                        }
                    }
                }
                break;

            case 'summary':
                resp = await fetch(`${API_BASE}/summarize`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ topic: queryText || 'the document' }),
                });
                result = await resp.json();
                if (!resp.ok) throw new Error(result.detail || 'Summarization failed');
                removeElement(loadingEl);
                addAIMessage(result.summary, result.sources);
                break;

            case 'extract':
                const fieldsStr = els.fieldsField.value.trim();
                if (!fieldsStr) {
                    removeElement(loadingEl);
                    addAIMessage('Please enter field names in the input above (comma-separated).', []);
                    break;
                }
                const fields = fieldsStr.split(',').map(f => f.trim()).filter(Boolean);
                resp = await fetch(`${API_BASE}/extract`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ fields, context_query: queryText }),
                });
                result = await resp.json();
                if (!resp.ok) throw new Error(result.detail || 'Extraction failed');
                removeElement(loadingEl);
                addJSONMessage(result.fields, result.sources);
                break;

            case 'table':
                resp = await fetch(`${API_BASE}/table-query`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ question: queryText }),
                });
                result = await resp.json();
                if (!resp.ok) throw new Error(result.detail || 'Table query failed');
                removeElement(loadingEl);
                addAIMessage(result.answer, result.sources);
                break;
        }

        // Save to history
        saveHistory(queryText || `Extract: ${els.fieldsField.value}`, state.mode);

    } catch (err) {
        removeElement(loadingEl);
        addAIMessage(`❌ Error: ${err.message}`, []);
    }

    state.isProcessing = false;
    els.sendBtn.disabled = false;
}

// ── Message Rendering ─────────────────────────────────────────────────────
function addMessage(type, text) {
    const div = document.createElement('div');
    div.className = `msg msg--${type}`;

    const avatar = document.createElement('div');
    avatar.className = 'msg__avatar';
    avatar.textContent = type === 'user' ? 'U' : 'AI';

    const bubble = document.createElement('div');
    bubble.className = 'msg__bubble';
    bubble.textContent = text;

    div.appendChild(avatar);
    div.appendChild(bubble);
    els.chatMessages.appendChild(div);
    scrollToBottom();

    return div;
}

function addAIMessage(text, sources) {
    const div = document.createElement('div');
    div.className = 'msg msg--ai';

    const avatar = document.createElement('div');
    avatar.className = 'msg__avatar';
    avatar.textContent = 'AI';

    const bubble = document.createElement('div');
    bubble.className = 'msg__bubble';

    // Format text (simple markdown-like)
    const formattedText = formatText(text);
    bubble.innerHTML = formattedText;

    // Add sources
    if (sources && sources.length > 0) {
        const sourcesDiv = document.createElement('div');
        sourcesDiv.className = 'msg__sources';
        sourcesDiv.innerHTML = `<div class="msg__sources-title">Sources</div>` +
            sources.map(s =>
                `<div class="msg__source"><strong>${s.source}</strong> page ${s.page}</div>`
            ).join('');
        bubble.appendChild(sourcesDiv);
    }

    div.appendChild(avatar);
    div.appendChild(bubble);
    els.chatMessages.appendChild(div);
    scrollToBottom();
    return div;
}

function addJSONMessage(data, sources) {
    const div = document.createElement('div');
    div.className = 'msg msg--ai';

    const avatar = document.createElement('div');
    avatar.className = 'msg__avatar';
    avatar.textContent = 'AI';

    const bubble = document.createElement('div');
    bubble.className = 'msg__bubble';

    const jsonDiv = document.createElement('div');
    jsonDiv.className = 'json-result';
    jsonDiv.innerHTML = syntaxHighlightJSON(JSON.stringify(data, null, 2));
    bubble.appendChild(jsonDiv);

    if (sources && sources.length > 0) {
        const sourcesDiv = document.createElement('div');
        sourcesDiv.className = 'msg__sources';
        sourcesDiv.innerHTML = `<div class="msg__sources-title">Sources</div>` +
            sources.map(s =>
                `<div class="msg__source"><strong>${s.source}</strong> page ${s.page}</div>`
            ).join('');
        bubble.appendChild(sourcesDiv);
    }

    div.appendChild(avatar);
    div.appendChild(bubble);
    els.chatMessages.appendChild(div);
    scrollToBottom();
}

function addLoading() {
    const div = document.createElement('div');
    div.className = 'msg msg--ai';
    div.innerHTML = `
        <div class="msg__avatar">AI</div>
        <div class="msg__bubble">
            <div class="loading-dots">
                <span></span><span></span><span></span>
            </div>
        </div>
    `;
    els.chatMessages.appendChild(div);
    scrollToBottom();
    return div;
}

function removeElement(el) {
    if (el && el.parentNode) el.parentNode.removeChild(el);
}

function scrollToBottom() {
    els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
}

// ── Text Formatting ───────────────────────────────────────────────────────
function formatText(text) {
    // Premium markdown parsing if available
    if (typeof marked !== 'undefined') {
        return marked.parse(text);
    }
    
    // Fallback naive rendering
    let html = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    html = html.replace(/^[•\-\*]\s+(.+)$/gm, '<li>$1</li>');
    html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>');
    html = html.replace(/\n/g, '<br>');

    return html;
}

function syntaxHighlightJSON(json) {
    json = json
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    return json.replace(
        /("(\\u[a-fA-F0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
        (match) => {
            let cls = 'json-number';
            if (/^"/.test(match)) {
                cls = /:$/.test(match) ? 'json-key' : 'json-string';
            } else if (/true|false/.test(match)) {
                cls = 'json-string';
            } else if (/null/.test(match)) {
                cls = 'json-null';
            }
            return `<span class="${cls}">${match}</span>`;
        }
    );
}

// ── Document List ─────────────────────────────────────────────────────────
function renderDocList() {
    if (state.documents.length === 0) {
        els.docList.innerHTML = '<li class="doc-list__empty">No documents yet</li>';
        return;
    }

    els.docList.innerHTML = state.documents.map(doc => `
        <li class="doc-list__item" title="${doc.name} — ${doc.pages} pages, ${doc.chunks} chunks">
            <svg class="doc-list__icon" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clip-rule="evenodd"/>
            </svg>
            <span class="doc-list__name">${doc.name}</span>
            <span class="doc-list__meta">${doc.chunks}ch</span>
        </li>
    `).join('');
}

// ── Query History ─────────────────────────────────────────────────────────
function saveHistory(query, mode) {
    const entry = {
        query: query.substring(0, 100),
        mode,
        timestamp: new Date().toISOString(),
    };
    state.history.unshift(entry);
    state.history = state.history.slice(0, 15); // keep last 15 for memory context limits
    localStorage.setItem('docai_history', JSON.stringify(state.history));
    renderHistoryList();
}

function renderHistoryList() {
    if (state.history.length === 0) {
        els.historyList.innerHTML = '<li class="history-list__empty">No queries yet</li>';
        return;
    }

    els.historyList.innerHTML = state.history.slice(0, 15).map(h => {
        const icon = h.mode === 'summary' ? '📋' : h.mode === 'extract' ? '🔧' : h.mode === 'table' ? '📊' : '❓';
        return `<li class="history-list__item" title="${h.query}" onclick="replayQuery('${escapeQuotes(h.query)}', '${h.mode}')">${icon} ${h.query}</li>`;
    }).join('');
}

function escapeQuotes(str) {
    return str.replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

function replayQuery(query, mode) {
    // Switch to the correct tab
    const tab = document.querySelector(`[data-mode="${mode}"]`);
    if (tab) tab.click();

    els.queryInput.value = query;
    els.queryInput.dispatchEvent(new Event('input'));
    els.queryInput.focus();
}

// Make replayQuery available globally
window.replayQuery = replayQuery;

// ── Status ────────────────────────────────────────────────────────────────
async function checkStatus() {
    try {
        const resp = await fetch(`${API_BASE}/status`);
        if (!resp.ok) throw new Error('API unreachable');
        const data = await resp.json();

        const vectors = data.total_vectors || 0;
        const ollamaOk = data.ollama === 'connected';

        if (ollamaOk && vectors > 0) {
            els.statusDot.className = 'status-dot online';
            els.statusText.textContent = `${vectors} vectors · Ollama OK`;
        } else if (ollamaOk) {
            els.statusDot.className = 'status-dot partial';
            els.statusText.textContent = `No docs · Ollama OK`;
        } else if (vectors > 0) {
            els.statusDot.className = 'status-dot partial';
            els.statusText.textContent = `${vectors} vectors · Ollama offline`;
        } else {
            els.statusDot.className = 'status-dot offline';
            els.statusText.textContent = `No docs · Ollama offline`;
        }

        // Sync document list from index
        if (data.sources && data.sources.length > 0) {
            const indexed = new Set(data.sources);
            // add any indexed docs not already in local state
            data.sources.forEach(name => {
                if (!state.documents.find(d => d.name === name)) {
                    state.documents.push({ name, pages: '?', chunks: '?', indexedAt: '' });
                }
            });
            localStorage.setItem('docai_documents', JSON.stringify(state.documents));
            renderDocList();
        }

    } catch {
        els.statusDot.className = 'status-dot offline';
        els.statusText.textContent = 'API unreachable';
    }
}

// ── Clear Index ───────────────────────────────────────────────────────────
function initClearBtn() {
    els.clearBtn.addEventListener('click', async () => {
        if (!confirm('Clear all indexed documents? This cannot be undone.')) return;

        try {
            const resp = await fetch(`${API_BASE}/clear`, { method: 'POST' });
            if (!resp.ok) throw new Error('Clear failed');

            state.documents = [];
            localStorage.setItem('docai_documents', JSON.stringify(state.documents));
            renderDocList();
            checkStatus();

            // Show confirmation in chat
            if (els.welcomeScreen) els.welcomeScreen.style.display = 'none';
            addAIMessage('🗑️ Index cleared. All documents have been removed. Upload new documents to start again.', []);

        } catch (err) {
            alert('Failed to clear index: ' + err.message);
        }
    });
}
