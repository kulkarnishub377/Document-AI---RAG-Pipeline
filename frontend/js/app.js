// ═══════════════════════════════════════════════════════════════════════════
// Document AI + RAG Pipeline — Frontend Application v2.0
//
// Features:
//   • File upload via drag & drop or click (multi-file support)
//   • Real-time streaming chat with 4 modes (Q&A, Summary, Extract, Table)
//   • XSS-safe rendering with HTML entity escaping
//   • Confidence score display in source citations
//   • Citation click-through to view full chunk text
//   • Export conversation as Markdown
//   • Analytics dashboard modal
//   • Document preview on hover
//   • Local storage for query history
//   • Status polling & Ollama connectivity indicator
// ═══════════════════════════════════════════════════════════════════════════

const API_BASE = window.location.origin;

// ── State ─────────────────────────────────────────────────────────────────
const state = {
    mode: 'qa',                // 'qa' | 'summary' | 'extract' | 'table'
    isProcessing: false,
    history: JSON.parse(localStorage.getItem('docai_history') || '[]'),
    documents: JSON.parse(localStorage.getItem('docai_documents') || '[]'),
    conversation: [],          // for export
};

// ── DOM References ────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

const els = {
    uploadZone:     $('uploadZone'),
    fileInput:      $('fileInput'),
    progressContainer: $('progressContainer'),
    progressFill:   $('progressFill'),
    progressText:   $('progressText'),
    urlForm:        $('urlForm'),
    urlInput:       $('urlInput'),
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
    exportBtn:      $('exportBtn'),
    analyticsBtn:   $('analyticsBtn'),
    citationModal:  $('citationModal'),
    citationModalTitle: $('citationModalTitle'),
    citationModalBody:  $('citationModalBody'),
    citationModalClose: $('citationModalClose'),
    analyticsModal: $('analyticsModal'),
    analyticsModalBody: $('analyticsModalBody'),
    analyticsModalClose: $('analyticsModalClose'),
};

// ── XSS Protection ───────────────────────────────────────────────────────
function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

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
    initUrlIngest();
    initTabs();
    initInput();
    initClearBtn();
    initExportBtn();
    initAnalyticsBtn();
    initModals();
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
        if (e.target.files.length) {
            // Multi-file support
            for (const file of e.target.files) {
                uploadFile(file);
            }
        }
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
        for (const file of e.dataTransfer.files) {
            uploadFile(file);
        }
    });
}

async function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    // Show progress
    els.progressContainer.style.display = 'block';
    els.progressFill.style.width = '10%';
    els.progressText.textContent = `Uploading ${escapeHtml(file.name)}…`;

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
        els.progressText.textContent = `✓ ${escapeHtml(result.file)} — ${result.chunks} chunks indexed in ${result.time_seconds}s`;

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

function initUrlIngest() {
    if (!els.urlForm) return;
    
    els.urlForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const url = els.urlInput.value.trim();
        if (!url) return;
        
        // Show progress
        els.progressContainer.style.display = 'block';
        els.progressFill.style.width = '10%';
        els.progressText.textContent = `Fetching URL…`;
        
        try {
            els.urlForm.querySelector('button').disabled = true;
            
            // Simulate scrape progress
            let progress = 10;
            const progressInterval = setInterval(() => {
                progress = Math.min(progress + Math.random() * 20, 90);
                els.progressFill.style.width = `${progress}%`;
            }, 300);

            const resp = await fetch(`${API_BASE}/ingest/url`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url })
            });

            clearInterval(progressInterval);

            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || 'URL Ingestion failed');
            }

            const result = await resp.json();

            els.progressFill.style.width = '100%';
            els.progressText.textContent = `✓ ${escapeHtml(result.file)} — Indexed successfully`;

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

            setTimeout(() => {
                els.progressContainer.style.display = 'none';
                els.progressFill.style.width = '0%';
            }, 3000);

            checkStatus();
            els.urlInput.value = '';

        } catch (err) {
            els.progressFill.style.width = '100%';
            els.progressFill.style.background = 'var(--red)';
            els.progressText.textContent = `✗ Error: ${err.message}`;
            setTimeout(() => {
                els.progressContainer.style.display = 'none';
                els.progressFill.style.width = '0%';
                els.progressFill.style.background = '';
            }, 5000);
        } finally {
            els.urlForm.querySelector('button').disabled = false;
        }
    });
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
    state.conversation.push({ role: 'user', content: userLabel });

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
                let sourcesData = [];

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
                                    sourcesData = data.sources;
                                    msgEl = addAIMessage('', data.sources);
                                }
                                
                                if (data.delta && msgEl) {
                                    const bubble = msgEl.querySelector('.msg__bubble');
                                    rawMarkdown += data.delta;
                                    
                                    // Re-render markdown + re-append sources
                                    const sourcesHtml = buildSourcesHtml(sourcesData);
                                    bubble.innerHTML = formatText(rawMarkdown) + sourcesHtml;
                                    scrollToBottom();
                                }
                            } catch (e) {
                                console.warn("Failed to parse SSE JSON chunk", line);
                            }
                        }
                    }
                }
                state.conversation.push({ role: 'ai', content: rawMarkdown });
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
                state.conversation.push({ role: 'ai', content: result.summary });
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
                state.conversation.push({ role: 'ai', content: JSON.stringify(result.fields, null, 2) });
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
                state.conversation.push({ role: 'ai', content: result.answer });
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

// ── Source Citation Builder ───────────────────────────────────────────────
function getConfidenceClass(score) {
    if (score >= 0.7) return 'confidence--high';
    if (score >= 0.4) return 'confidence--medium';
    return 'confidence--low';
}

function getConfidenceLabel(score) {
    if (score >= 0.7) return 'High';
    if (score >= 0.4) return 'Medium';
    return 'Low';
}

function buildSourcesHtml(sources) {
    if (!sources || sources.length === 0) return '';
    
    return `<div class="msg__sources"><div class="msg__sources-title">Sources</div>` +
        sources.map((s, idx) => {
            const scoreNum = s.score || 0;
            const confClass = getConfidenceClass(scoreNum);
            const confLabel = getConfidenceLabel(scoreNum);
            const excerpt = escapeHtml(s.excerpt || '');
            return `<div class="msg__source" data-source-idx="${idx}" onclick="showCitationDetail(${JSON.stringify(escapeHtml(s.source)).replace(/"/g, '&quot;')}, ${s.page}, ${JSON.stringify(excerpt).replace(/"/g, '&quot;')}, ${scoreNum})">
                <div class="msg__source-header">
                    <strong>${escapeHtml(s.source)}</strong>
                    <span class="msg__source-page">page ${s.page}</span>
                    <span class="confidence-badge ${confClass}" title="Confidence: ${scoreNum.toFixed(3)}">${confLabel}</span>
                </div>
            </div>`;
        }).join('') + `</div>`;
}

// ── Citation Detail Modal ─────────────────────────────────────────────────
function showCitationDetail(source, page, excerpt, score) {
    els.citationModalTitle.textContent = `${source} — Page ${page}`;
    els.citationModalBody.innerHTML = `
        <div class="citation-detail">
            <div class="citation-detail__meta">
                <span class="confidence-badge ${getConfidenceClass(score)}">
                    Confidence: ${score.toFixed(3)} (${getConfidenceLabel(score)})
                </span>
            </div>
            <div class="citation-detail__text">${formatText(excerpt)}</div>
        </div>
    `;
    els.citationModal.style.display = 'flex';
}
window.showCitationDetail = showCitationDetail;

// ── Message Rendering ─────────────────────────────────────────────────────
function addMessage(type, text) {
    const div = document.createElement('div');
    div.className = `msg msg--${type}`;

    const avatar = document.createElement('div');
    avatar.className = 'msg__avatar';
    avatar.textContent = type === 'user' ? 'U' : 'AI';

    const bubble = document.createElement('div');
    bubble.className = 'msg__bubble';
    bubble.textContent = text; // textContent is XSS-safe

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

    // Format text (markdown)
    const formattedText = formatText(text);
    bubble.innerHTML = formattedText;

    // Add sources with confidence scores
    if (sources && sources.length > 0) {
        bubble.innerHTML += buildSourcesHtml(sources);
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
        bubble.innerHTML += buildSourcesHtml(sources);
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
    
    // Fallback naive rendering (XSS-safe)
    let html = escapeHtml(text);
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    html = html.replace(/^[•\-\*]\s+(.+)$/gm, '<li>$1</li>');
    html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>');
    html = html.replace(/\n/g, '<br>');

    return html;
}

function syntaxHighlightJSON(json) {
    json = escapeHtml(json);
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

    els.docList.innerHTML = state.documents.map(doc => {
        const safeName = escapeHtml(doc.name);
        return `
        <li class="doc-list__item" title="${safeName} — ${doc.pages} pages, ${doc.chunks} chunks">
            <svg class="doc-list__icon" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clip-rule="evenodd"/>
            </svg>
            <span class="doc-list__name">${safeName}</span>
            <span class="doc-list__meta">${doc.chunks}ch</span>
            <button class="doc-delete-btn" title="Delete from index" onclick="deleteDocument('${safeName.replace(/'/g, "\\'")}')">
                <svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd"/></svg>
            </button>
        </li>`;
    }).join('');
}

async function deleteDocument(filename) {
    if (!confirm(`Are you sure you want to delete "${filename}" from the AI's memory?`)) return;
    
    try {
        const resp = await fetch(`${API_BASE}/document/${encodeURIComponent(filename)}`, { method: 'DELETE' });
        if (!resp.ok) throw new Error('Deletion failed');
        
        state.documents = state.documents.filter(d => d.name !== filename);
        localStorage.setItem('docai_documents', JSON.stringify(state.documents));
        renderDocList();
        checkStatus();
        
    } catch (err) {
        alert('Failed to delete document: ' + err.message);
    }
}

// ── Query History ─────────────────────────────────────────────────────────
function saveHistory(query, mode) {
    const entry = {
        query: query.substring(0, 100),
        mode,
        timestamp: new Date().toISOString(),
    };
    state.history.unshift(entry);
    state.history = state.history.slice(0, 15);
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
        const safeQuery = escapeHtml(h.query);
        return `<li class="history-list__item" title="${safeQuery}" onclick="replayQuery('${safeQuery.replace(/'/g, "\\'")}', '${h.mode}')">${icon} ${safeQuery}</li>`;
    }).join('');
}

function replayQuery(query, mode) {
    const tab = document.querySelector(`[data-mode="${mode}"]`);
    if (tab) tab.click();
    els.queryInput.value = query;
    els.queryInput.dispatchEvent(new Event('input'));
    els.queryInput.focus();
}
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

            if (els.welcomeScreen) els.welcomeScreen.style.display = 'none';
            addAIMessage('🗑️ Index cleared. All documents have been permanently removed.', []);

        } catch (err) {
            alert('Failed to clear index: ' + err.message);
        }
    });
}

// ── Export Conversation ───────────────────────────────────────────────────
function initExportBtn() {
    if (!els.exportBtn) return;
    els.exportBtn.addEventListener('click', () => {
        if (state.conversation.length === 0) {
            alert('No conversation to export yet.');
            return;
        }
        
        let md = `# Document AI — Conversation Export\n`;
        md += `*Exported on ${new Date().toLocaleString()}*\n\n---\n\n`;
        
        for (const msg of state.conversation) {
            if (msg.role === 'user') {
                md += `## 🧑 User\n${msg.content}\n\n`;
            } else {
                md += `## 🤖 AI\n${msg.content}\n\n`;
            }
            md += `---\n\n`;
        }
        
        // Copy to clipboard
        navigator.clipboard.writeText(md).then(() => {
            const origText = els.exportBtn.innerHTML;
            els.exportBtn.innerHTML = `<svg viewBox="0 0 20 20" fill="currentColor" width="14" height="14"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/></svg> Copied!`;
            setTimeout(() => { els.exportBtn.innerHTML = origText; }, 2000);
        }).catch(() => {
            // Fallback: download as file
            const blob = new Blob([md], { type: 'text/markdown' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'conversation_export.md';
            a.click();
            URL.revokeObjectURL(url);
        });
    });
}

// ── Analytics Modal ──────────────────────────────────────────────────────
function initAnalyticsBtn() {
    if (!els.analyticsBtn) return;
    els.analyticsBtn.addEventListener('click', async () => {
        els.analyticsModal.style.display = 'flex';
        els.analyticsModalBody.innerHTML = '<p style="text-align:center;padding:2rem;">Loading analytics…</p>';
        
        try {
            const resp = await fetch(`${API_BASE}/analytics`);
            if (!resp.ok) throw new Error('Failed to fetch analytics');
            const data = await resp.json();
            
            const storage = data.storage || {};
            const breakdown = data.source_breakdown || [];
            
            let html = `
                <div class="analytics-grid">
                    <div class="analytics-card">
                        <div class="analytics-card__value">${data.total_vectors || 0}</div>
                        <div class="analytics-card__label">Total Vectors</div>
                    </div>
                    <div class="analytics-card">
                        <div class="analytics-card__value">${data.unique_sources || 0}</div>
                        <div class="analytics-card__label">Documents</div>
                    </div>
                    <div class="analytics-card">
                        <div class="analytics-card__value">${data.dimension || 0}</div>
                        <div class="analytics-card__label">Dimensions</div>
                    </div>
                    <div class="analytics-card">
                        <div class="analytics-card__value">${storage.total_size_mb || 0} MB</div>
                        <div class="analytics-card__label">Total Storage</div>
                    </div>
                </div>
                
                <h4 style="margin:1.5rem 0 0.75rem;color:var(--text-primary);">Storage Breakdown</h4>
                <div class="analytics-storage">
                    <div class="analytics-storage__item">
                        <span>FAISS Index</span>
                        <span>${storage.index_size_mb || 0} MB</span>
                    </div>
                    <div class="analytics-storage__item">
                        <span>Metadata</span>
                        <span>${storage.metadata_size_mb || 0} MB</span>
                    </div>
                    <div class="analytics-storage__item">
                        <span>Uploaded Files</span>
                        <span>${storage.uploads_size_mb || 0} MB</span>
                    </div>
                </div>
                
                <h4 style="margin:1.5rem 0 0.75rem;color:var(--text-primary);">Ollama Status</h4>
                <div class="analytics-status">
                    <span class="status-dot ${data.ollama === 'connected' ? 'online' : 'offline'}"></span>
                    ${data.ollama === 'connected' ? 'Connected' : 'Not Reachable — run: ollama serve'}
                </div>`;
            
            if (breakdown.length > 0) {
                html += `
                <h4 style="margin:1.5rem 0 0.75rem;color:var(--text-primary);">Document Breakdown</h4>
                <div class="analytics-table">
                    <div class="analytics-table__header">
                        <span>Source</span>
                        <span>Chunks</span>
                    </div>
                    ${breakdown.map(b => `
                    <div class="analytics-table__row">
                        <span>${escapeHtml(b.source)}</span>
                        <span class="analytics-table__count">${b.chunks}</span>
                    </div>`).join('')}
                </div>`;
            }
            
            els.analyticsModalBody.innerHTML = html;
            
        } catch (err) {
            els.analyticsModalBody.innerHTML = `<p style="color:var(--red);padding:2rem;">Error: ${escapeHtml(err.message)}</p>`;
        }
    });
}

// ── Modals ────────────────────────────────────────────────────────────────
function initModals() {
    // Citation modal
    if (els.citationModalClose) {
        els.citationModalClose.addEventListener('click', () => {
            els.citationModal.style.display = 'none';
        });
    }
    if (els.citationModal) {
        els.citationModal.addEventListener('click', (e) => {
            if (e.target === els.citationModal) els.citationModal.style.display = 'none';
        });
    }
    
    // Analytics modal
    if (els.analyticsModalClose) {
        els.analyticsModalClose.addEventListener('click', () => {
            els.analyticsModal.style.display = 'none';
        });
    }
    if (els.analyticsModal) {
        els.analyticsModal.addEventListener('click', (e) => {
            if (e.target === els.analyticsModal) els.analyticsModal.style.display = 'none';
        });
    }
    
    // Close modals with Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            if (els.citationModal) els.citationModal.style.display = 'none';
            if (els.analyticsModal) els.analyticsModal.style.display = 'none';
        }
    });
}
