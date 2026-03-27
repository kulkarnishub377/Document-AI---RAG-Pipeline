// ═══════════════════════════════════════════════════════════════════════════
// Document AI + RAG Pipeline v3.0 — Frontend Logic
// ═══════════════════════════════════════════════════════════════════════════

'use strict';

// ── State ────────────────────────────────────────────────────────────────
const state = {
  streaming: true,
  history: [],
  documents: [],
  isQuerying: false,
};

// ── Utilities ────────────────────────────────────────────────────────────
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function formatTime() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function getFileIcon(ext) {
  const map = {
    '.pdf': ['📕', 'pdf'], '.docx': ['📘', 'doc'], '.doc': ['📘', 'doc'],
    '.xlsx': ['📗', 'xls'], '.xls': ['📗', 'xls'], '.csv': ['📊', 'csv'],
    '.pptx': ['📙', 'ppt'], '.png': ['🖼️', 'img'], '.jpg': ['🖼️', 'img'],
    '.jpeg': ['🖼️', 'img'], '.tiff': ['🖼️', 'img'],
    '.txt': ['📄', 'txt'], '.md': ['📄', 'txt'],
  };
  return map[ext] || ['📄', 'txt'];
}

function confidenceClass(score) {
  if (score >= 0.75) return 'high';
  if (score >= 0.5) return 'mid';
  return 'low';
}

function confidenceLabel(score) {
  if (score >= 0.75) return 'High';
  if (score >= 0.5) return 'Medium';
  return 'Low';
}

// ── Toast Notifications ──────────────────────────────────────────────────
function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = escapeHtml(message);
  container.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 4000);
}

// ── Panel Switching ──────────────────────────────────────────────────────
function switchPanel(panelName) {
  document.querySelectorAll('.panel').forEach(p => p.style.display = 'none');
  document.querySelectorAll('.nav-item[data-panel]').forEach(n => n.classList.remove('active'));

  const panel = document.getElementById(`panel-${panelName}`);
  if (panel) {
    panel.style.display = panelName === 'chat' ? '' : (panel.classList.contains('chat-panel') ? '' : 'flex');
    if (panelName === 'chat') panel.style.display = '';
    else panel.style.display = 'flex';
    panel.style.flexDirection = 'column';
  }

  const navItem = document.querySelector(`.nav-item[data-panel="${panelName}"]`);
  if (navItem) navItem.classList.add('active');

  // Load data for specific panels
  if (panelName === 'analytics') loadAnalytics();
  if (panelName === 'ragas') loadRagasDashboard();
  if (panelName === 'compare') populateCompareSelectors();
}

// ── Modal ────────────────────────────────────────────────────────────────
function openModal(id) { document.getElementById(id).classList.add('active'); }
function closeModal(id) { document.getElementById(id).classList.remove('active'); }

// Close modals on overlay click
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.classList.remove('active');
  }
});

// ── Settings ─────────────────────────────────────────────────────────────
function setStreaming(on) {
  state.streaming = on;
  document.getElementById('streamOn').className = on ? 'btn btn-primary' : 'btn btn-secondary';
  document.getElementById('streamOff').className = on ? 'btn btn-secondary' : 'btn btn-primary';
  showToast(`Streaming ${on ? 'enabled' : 'disabled'}`, 'info');
}

// ── API Calls ────────────────────────────────────────────────────────────
async function api(path, options = {}) {
  try {
    const res = await fetch(path, options);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || err.message || `HTTP ${res.status}`);
    }
    return await res.json();
  } catch (err) {
    showToast(err.message, 'error');
    throw err;
  }
}

// ── Status Check ─────────────────────────────────────────────────────────
async function checkStatus() {
  try {
    const data = await api('/status');
    const dot = document.getElementById('statusDot');
    const text = document.getElementById('statusText');
    const isOnline = data.ollama === 'connected';
    dot.className = `status-dot ${isOnline ? 'online' : 'offline'}`;
    text.textContent = isOnline
      ? `${data.total_vectors || 0} vectors indexed`
      : 'Ollama offline';
  } catch {
    document.getElementById('statusDot').className = 'status-dot offline';
    document.getElementById('statusText').textContent = 'Server offline';
  }
}

// ── Document List ────────────────────────────────────────────────────────
async function loadDocuments() {
  try {
    const docs = await api('/documents');
    state.documents = docs;
    renderDocumentList(docs);
  } catch { /* silent */ }
}

function renderDocumentList(docs) {
  const list = document.getElementById('fileList');
  const count = document.getElementById('fileCount');
  count.textContent = docs.length;

  if (!docs.length) {
    list.innerHTML = '<p style="font-size:12px;color:var(--text-muted);text-align:center;padding:20px;">No documents uploaded yet</p>';
    return;
  }

  list.innerHTML = docs.map(doc => {
    const [icon, cls] = getFileIcon(doc.suffix);
    return `
      <div class="file-item">
        <div class="file-icon ${cls}">${icon}</div>
        <div class="file-info">
          <div class="file-name">${escapeHtml(doc.filename)}</div>
          <div class="file-meta">${doc.size_mb} MB</div>
        </div>
        <button class="file-delete" onclick="deleteDocument('${escapeHtml(doc.filename)}')" data-tooltip="Delete">🗑️</button>
      </div>`;
  }).join('');
}

async function deleteDocument(filename) {
  if (!confirm(`Delete "${filename}" from index?`)) return;
  try {
    await api(`/document/${encodeURIComponent(filename)}`, { method: 'DELETE' });
    showToast(`Deleted ${filename}`, 'success');
    loadDocuments();
    checkStatus();
  } catch { /* toast shown by api() */ }
}

// ── File Upload ──────────────────────────────────────────────────────────
function handleDrop(e) {
  e.preventDefault();
  document.getElementById('uploadZone').classList.remove('drag-over');
  const files = e.dataTransfer.files;
  if (files.length) uploadFiles(files);
}

function handleFileSelect(e) {
  uploadFiles(e.target.files);
  e.target.value = '';
}

async function uploadFiles(files) {
  const progress = document.getElementById('uploadProgress');
  const fill = document.getElementById('progressFill');
  const text = document.getElementById('progressText');
  progress.style.display = 'block';

  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    text.textContent = `Uploading ${file.name} (${i + 1}/${files.length})...`;
    fill.style.width = `${((i) / files.length) * 100}%`;

    const formData = new FormData();
    formData.append('file', file);

    try {
      const result = await api('/ingest', { method: 'POST', body: formData });
      showToast(`✓ ${result.file}: ${result.chunks} chunks indexed`, 'success');
    } catch { /* toast shown by api() */ }

    fill.style.width = `${((i + 1) / files.length) * 100}%`;
  }

  text.textContent = 'Done!';
  setTimeout(() => { progress.style.display = 'none'; fill.style.width = '0%'; }, 2000);
  loadDocuments();
  checkStatus();
}

async function ingestUrl() {
  const input = document.getElementById('urlInput');
  const url = input.value.trim();
  if (!url) return;

  try {
    const result = await api('/ingest/url', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    showToast(`✓ ${result.file}: ${result.chunks} chunks indexed`, 'success');
    input.value = '';
    loadDocuments();
    checkStatus();
  } catch { /* toast shown by api() */ }
}

// ── Chat ─────────────────────────────────────────────────────────────────
function addMessage(role, content, sources = []) {
  const welcome = document.getElementById('chatWelcome');
  if (welcome) welcome.style.display = 'none';

  const container = document.getElementById('chatMessages');
  const msg = document.createElement('div');
  msg.className = `message ${role}`;

  const avatar = role === 'user' ? '👤' : '🧠';
  const sender = role === 'user' ? 'You' : 'Document AI';

  let sourcesHtml = '';
  if (sources.length) {
    sourcesHtml = `<div class="sources-container">
      <div class="sources-title">📎 Sources (${sources.length})</div>
      ${sources.map(s => {
        const cls = confidenceClass(s.score || 0);
        return `<span class="source-chip" onclick="showSource(${JSON.stringify(s).replace(/"/g, '&quot;')})">
          📄 ${escapeHtml(s.source)} p.${s.page}
          <span class="score ${cls}">${((s.score || 0) * 100).toFixed(0)}%</span>
          <span class="confidence-badge ${cls}">${confidenceLabel(s.score || 0)}</span>
        </span>`;
      }).join('')}
    </div>`;
  }

  msg.innerHTML = `
    <div class="message-avatar ${role}">${avatar}</div>
    <div class="message-body">
      <div class="message-header">
        <span class="message-sender">${sender}</span>
        <span class="message-time">${formatTime()}</span>
      </div>
      <div class="message-content">${role === 'user' ? escapeHtml(content) : content}</div>
      ${sourcesHtml}
    </div>`;

  container.appendChild(msg);
  container.scrollTop = container.scrollHeight;

  // Update history
  state.history.push({ role, content: typeof content === 'string' ? content : '' });
  if (state.history.length > 20) state.history = state.history.slice(-20);
}

function showSource(source) {
  document.getElementById('sourceModalTitle').textContent = `${source.source} — Page ${source.page}`;
  document.getElementById('sourceModalBody').textContent = source.excerpt || 'No excerpt available';
  openModal('sourceModal');
}

function quickAsk(question) {
  document.getElementById('chatInput').value = question;
  switchPanel('chat');
  sendQuery();
}

async function sendQuery() {
  const input = document.getElementById('chatInput');
  const question = input.value.trim();
  if (!question || state.isQuerying) return;

  input.value = '';
  autoResizeInput();
  addMessage('user', question);
  state.isQuerying = true;
  document.getElementById('sendBtn').disabled = true;

  if (state.streaming) {
    await streamQuery(question);
  } else {
    await syncQuery(question);
  }

  state.isQuerying = false;
  document.getElementById('sendBtn').disabled = false;
}

async function syncQuery(question) {
  try {
    const result = await api('/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question,
        history: state.history.slice(-10),
      }),
    });
    addMessage('ai', escapeHtml(result.answer), result.sources || []);
  } catch { addMessage('ai', '❌ Failed to get answer. Check if Ollama is running.'); }
}

async function streamQuery(question) {
  // Create placeholder message
  const welcome = document.getElementById('chatWelcome');
  if (welcome) welcome.style.display = 'none';

  const container = document.getElementById('chatMessages');
  const msg = document.createElement('div');
  msg.className = 'message ai';
  msg.innerHTML = `
    <div class="message-avatar ai">🧠</div>
    <div class="message-body">
      <div class="message-header">
        <span class="message-sender">Document AI</span>
        <span class="message-time">${formatTime()}</span>
      </div>
      <div class="message-content"><div class="loading-dots"><span></span><span></span><span></span></div></div>
    </div>`;
  container.appendChild(msg);
  container.scrollTop = container.scrollHeight;

  const contentEl = msg.querySelector('.message-content');
  let fullText = '';

  try {
    const res = await fetch('/query-stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question,
        history: state.history.slice(-10),
      }),
    });

    const reader = res.body.getReader();
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
          fullText += data;
          contentEl.textContent = fullText;
          container.scrollTop = container.scrollHeight;
        }
      }
    }

    if (!fullText) contentEl.textContent = 'No response received.';
    state.history.push({ role: 'assistant', content: fullText });

  } catch {
    contentEl.textContent = '❌ Stream failed. Check if Ollama is running.';
  }
}

// ── Auto-resize textarea ─────────────────────────────────────────────────
function autoResizeInput() {
  const input = document.getElementById('chatInput');
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 120) + 'px';
}
document.getElementById('chatInput')?.addEventListener('input', autoResizeInput);

// ── Analytics ────────────────────────────────────────────────────────────
async function loadAnalytics() {
  try {
    const data = await api('/analytics');
    const grid = document.getElementById('analyticsStats');
    grid.innerHTML = `
      <div class="stat-card">
        <div class="stat-label">Total Vectors</div>
        <div class="stat-value accent">${(data.total_vectors || 0).toLocaleString()}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Documents</div>
        <div class="stat-value accent">${(data.sources || []).length}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Index Size</div>
        <div class="stat-value">${data.storage?.index_size_mb || 0} MB</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Total Storage</div>
        <div class="stat-value">${data.storage?.total_size_mb || 0} MB</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Cache Hits</div>
        <div class="stat-value success">${data.cache?.hits || 0}</div>
        <div class="stat-sub">Hit rate: ${data.cache?.hit_rate || '0%'}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Ollama</div>
        <div class="stat-value ${data.ollama === 'connected' ? 'success' : 'warning'}">${data.ollama === 'connected' ? 'Online' : 'Offline'}</div>
      </div>`;

    // Source breakdown
    const breakdown = document.getElementById('sourceBreakdown');
    const sources = data.source_breakdown || [];
    if (sources.length) {
      breakdown.innerHTML = sources.map(s => `
        <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border);">
          <span style="font-size:13px;font-weight:500;">${escapeHtml(s.source)}</span>
          <span style="font-size:12px;color:var(--accent-light);font-weight:700;font-family:var(--font-mono);">${s.chunks} chunks</span>
        </div>`).join('');
    } else {
      breakdown.innerHTML = '<p style="font-size:13px;color:var(--text-muted);text-align:center;">No documents indexed</p>';
    }
  } catch { /* toast shown by api() */ }
}

// ── RAGAS Dashboard ──────────────────────────────────────────────────────
function createScoreRing(elementId, score, color) {
  const el = document.getElementById(elementId);
  if (!el) return;
  const radius = 32;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score * circumference);

  el.innerHTML = `
    <svg viewBox="0 0 80 80">
      <circle class="bg" cx="40" cy="40" r="${radius}" fill="none" stroke-width="6"/>
      <circle class="fill" cx="40" cy="40" r="${radius}" fill="none" stroke="${color}" stroke-width="6"
        stroke-dasharray="${circumference}" stroke-dashoffset="${offset}" stroke-linecap="round"/>
    </svg>
    <div class="ragas-score-value" style="color:${color}">${(score * 100).toFixed(0)}%</div>`;
}

async function loadRagasDashboard() {
  try {
    const data = await api('/evaluate/dashboard');

    // Score rings
    createScoreRing('ringFaith', data.avg_faithfulness || 0, '#00cec9');
    createScoreRing('ringRelevancy', data.avg_answer_relevancy || 0, '#6c5ce7');
    createScoreRing('ringPrecision', data.avg_context_precision || 0, '#fdcb6e');
    createScoreRing('ringRecall', data.avg_context_recall || 0, '#fd79a8');

    // Trend labels
    document.getElementById('trendFaith').textContent = `Avg: ${((data.avg_faithfulness || 0) * 100).toFixed(1)}%`;
    document.getElementById('trendRelevancy').textContent = `Avg: ${((data.avg_answer_relevancy || 0) * 100).toFixed(1)}%`;
    document.getElementById('trendPrecision').textContent = `Avg: ${((data.avg_context_precision || 0) * 100).toFixed(1)}%`;
    document.getElementById('trendRecall').textContent = `Avg: ${((data.avg_context_recall || 0) * 100).toFixed(1)}%`;

    // Stats
    const stats = document.getElementById('ragasStats');
    stats.innerHTML = `
      <div class="stat-card">
        <div class="stat-label">Total Evaluations</div>
        <div class="stat-value accent">${data.total_evaluations || 0}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Overall Average</div>
        <div class="stat-value success">${((data.avg_overall || 0) * 100).toFixed(1)}%</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Best Score</div>
        <div class="stat-value" style="color:var(--success)">${((data.best_score || 0) * 100).toFixed(1)}%</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Worst Score</div>
        <div class="stat-value" style="color:var(--danger)">${((data.worst_score || 0) * 100).toFixed(1)}%</div>
      </div>`;

    // History
    const history = await api('/evaluate/history?limit=10');
    const historyEl = document.getElementById('ragasHistory');
    if (history.length) {
      historyEl.innerHTML = history.map(h => `
        <div style="padding:10px 0;border-bottom:1px solid var(--border);">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <span style="font-size:12px;font-weight:600;color:var(--text-primary);max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(h.question)}</span>
            <span class="confidence-badge ${confidenceClass(h.overall_score || 0)}">${((h.overall_score || 0) * 100).toFixed(0)}%</span>
          </div>
          <div style="display:flex;gap:12px;margin-top:4px;font-size:11px;color:var(--text-muted);">
            <span>Faith: ${((h.faithfulness || 0) * 100).toFixed(0)}%</span>
            <span>Rel: ${((h.answer_relevancy || 0) * 100).toFixed(0)}%</span>
            <span>Prec: ${((h.context_precision || 0) * 100).toFixed(0)}%</span>
            <span>Rec: ${((h.context_recall || 0) * 100).toFixed(0)}%</span>
          </div>
        </div>`).join('');
    } else {
      historyEl.innerHTML = '<p style="text-align:center;color:var(--text-muted);font-size:13px;">No evaluations yet. Use the /evaluate/auto endpoint or query with auto-eval.</p>';
    }
  } catch { /* toast shown by api() */ }
}

async function clearRagasHistory() {
  if (!confirm('Clear all evaluation history?')) return;
  await api('/evaluate/clear', { method: 'POST' });
  showToast('Evaluation history cleared', 'success');
  loadRagasDashboard();
}

// ── Document Comparison ──────────────────────────────────────────────────
function populateCompareSelectors() {
  const docs = state.documents;
  ['compareDocA', 'compareDocB'].forEach(id => {
    const sel = document.getElementById(id);
    const current = sel.value;
    sel.innerHTML = '<option value="">Select document...</option>' +
      docs.map(d => `<option value="${escapeHtml(d.filename)}">${escapeHtml(d.filename)}</option>`).join('');
    if (current) sel.value = current;
  });
}

async function compareDocuments() {
  const docA = document.getElementById('compareDocA').value;
  const docB = document.getElementById('compareDocB').value;
  const question = document.getElementById('compareQuestion').value;
  if (!docA || !docB) { showToast('Select both documents to compare', 'error'); return; }

  const result = document.getElementById('compareResult');
  result.style.display = 'block';
  result.innerHTML = '<div class="loading-dots"><span></span><span></span><span></span></div>';

  try {
    const data = await api('/compare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ doc_a: docA, doc_b: docB, question }),
    });
    result.innerHTML = escapeHtml(data.comparison || data.error || JSON.stringify(data, null, 2));
  } catch { result.innerHTML = 'Comparison failed.'; }
}

// ── Field Extraction ─────────────────────────────────────────────────────
async function extractFields() {
  const fieldsText = document.getElementById('extractFields').value.trim();
  if (!fieldsText) { showToast('Enter at least one field name', 'error'); return; }
  const fields = fieldsText.split('\n').map(f => f.trim()).filter(Boolean);

  const result = document.getElementById('extractResult');
  result.innerHTML = '<div class="loading-dots"><span></span><span></span><span></span></div>';

  try {
    const data = await api('/extract', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fields }),
    });
    result.innerHTML = `<pre style="background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-md);padding:20px;font-family:var(--font-mono);font-size:13px;color:var(--text-primary);overflow-x:auto;">${escapeHtml(JSON.stringify(data, null, 2))}</pre>`;
  } catch { result.innerHTML = 'Extraction failed.'; }
}

// ── Summarize ────────────────────────────────────────────────────────────
async function getSummary() {
  const topic = document.getElementById('summaryTopic').value.trim() || 'the document';
  const result = document.getElementById('summaryResult');
  result.style.display = 'block';
  result.innerHTML = '<div class="loading-dots"><span></span><span></span><span></span></div>';

  try {
    const data = await api('/summarize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topic }),
    });
    result.textContent = data.summary || 'No summary generated.';
  } catch { result.textContent = 'Summary failed.'; }
}

// ── Management ───────────────────────────────────────────────────────────
async function clearCache() {
  await api('/cache/clear', { method: 'POST' });
  showToast('Query cache cleared', 'success');
}

async function clearIndex() {
  if (!confirm('This will delete ALL indexed documents. Are you sure?')) return;
  await api('/clear', { method: 'POST' });
  showToast('Index cleared', 'success');
  loadDocuments();
  checkStatus();
}

// ── Initialization ───────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  checkStatus();
  loadDocuments();
  setInterval(checkStatus, 30000);
  setInterval(loadDocuments, 60000);
});
