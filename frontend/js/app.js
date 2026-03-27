'use strict';

// Theme
function initTheme() {
  const select = document.getElementById('themeSelect');
  const saved = localStorage.getItem('theme') || 'dark';
  document.documentElement.setAttribute('data-theme', saved);
  select.value = saved;
  select.addEventListener('change', (e) => {
    document.documentElement.setAttribute('data-theme', e.target.value);
    localStorage.setItem('theme', e.target.value);
  });
}

// Toast
function showToast(msg, type = 'info') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast toast--${type}`;
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// API
async function apiCall(path, options = {}) {
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

// Modal
function openModal(id) {
  document.getElementById(id)?.classList.add('active');
}

function closeModal(id) {
  document.getElementById(id)?.classList.remove('active');
}

// Modals close on overlay click
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.classList.remove('active');
  }
});

// Search
const escapeHtml = (text) => {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
};

const formatTime = () => {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
};

const getFileIcon = (ext) => {
  const icons = {
    '.pdf': '📕', '.docx': '📘', '.doc': '📘', '.xlsx': '📗', '.xls': '📗',
    '.csv': '📊', '.pptx': '📙', '.png': '🖼️', '.jpg': '🖼️',
    '.jpeg': '🖼️', '.tiff': '🖼️', '.txt': '📄', '.md': '📄',
  };
  return icons[ext] || '📄';
};

// Status
async function checkStatus() {
  try {
    const data = await apiCall('/status');
    const isOnline = data.ollama === 'connected';
    const dot = document.getElementById('statusDot');
    const text = document.getElementById('statusText');
    const vectors = document.getElementById('vectorCount');
    const docs = document.getElementById('docCount');

    dot.classList.toggle('online', isOnline);
    text.textContent = isOnline ? 'Online' : 'Offline';
    vectors.textContent = (data.total_vectors || 0).toLocaleString();
    docs.textContent = (data.sources || []).length;
  } catch {}
}

// Documents
let allDocuments = [];

async function loadDocuments() {
  try {
    allDocuments = await apiCall('/documents');
    renderDocuments();
  } catch {}
}

function renderDocuments() {
  const list = document.getElementById('fileList');
  const count = document.getElementById('fileCount');
  count.textContent = allDocuments.length;

  if (!allDocuments.length) {
    list.innerHTML = '';
    return;
  }

  list.innerHTML = allDocuments.slice(0, 10).map(doc => `
    <div class="doc-item">
      <div class="doc-icon">${getFileIcon(doc.suffix)}</div>
      <div class="doc-info">
        <div class="doc-name">${escapeHtml(doc.filename)}</div>
        <div class="doc-size">${doc.size_mb} MB</div>
      </div>
      <button class="doc-delete" data-file="${escapeHtml(doc.filename)}">×</button>
    </div>`).join('');

  document.querySelectorAll('.doc-delete').forEach(btn => {
    btn.addEventListener('click', () => deleteDocument(btn.dataset.file));
  });
}

async function deleteDocument(filename) {
  if (!confirm(`Delete "${filename}"?`)) return;
  try {
    await apiCall(`/document/${encodeURIComponent(filename)}`, { method: 'DELETE' });
    showToast('Deleted', 'success');
    loadDocuments();
    checkStatus();
  } catch {}
}

// Upload
async function uploadFiles(files) {
  const progress = document.getElementById('uploadProgress');
  const fill = document.getElementById('progressFill');
  const text = document.getElementById('progressText');
  progress.style.display = 'block';

  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    text.textContent = `${file.name} (${i + 1}/${files.length})`;
    fill.style.width = `${(i / files.length) * 100}%`;

    const fd = new FormData();
    fd.append('file', file);

    try {
      const res = await apiCall('/ingest', { method: 'POST', body: fd });
      showToast(`✓ ${res.chunks} chunks indexed`, 'success');
    } catch {}

    fill.style.width = `${((i + 1) / files.length) * 100}%`;
  }

  text.textContent = 'Done!';
  setTimeout(() => {
    progress.style.display = 'none';
    fill.style.width = '0%';
  }, 2000);

  loadDocuments();
  checkStatus();
}

async function ingestUrl() {
  const input = document.getElementById('urlInput');
  const url = input.value.trim();
  if (!url) return;

  try {
    const res = await apiCall('/ingest/url', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    showToast(`✓ ${res.chunks} chunks indexed`, 'success');
    input.value = '';
    loadDocuments();
    checkStatus();
  } catch {}
}

// Chat
let chatHistory = [];
let isQuerying = false;
let streaming = true;

async function sendQuery() {
  const input = document.getElementById('chatInput');
  const q = input.value.trim();
  if (!q || isQuerying) return;

  input.value = '';
  input.style.height = 'auto';
  addMessage('user', q);
  isQuerying = true;
  document.getElementById('sendBtn').disabled = true;

  try {
    if (streaming) await streamQuery(q);
    else await syncQuery(q);
  } finally {
    isQuerying = false;
    document.getElementById('sendBtn').disabled = false;
  }
}

async function syncQuery(q) {
  try {
    const res = await apiCall('/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q, history: chatHistory.slice(-10) }),
    });
    addMessage('ai', escapeHtml(res.answer || ''), res.sources || []);
  } catch {
    addMessage('ai', '❌ Failed to get answer');
  }
}

async function streamQuery(q) {
  const container = document.getElementById('chatMessages');
  const msg = document.createElement('div');
  msg.className = 'message';
  msg.innerHTML = `<div class="message-avatar">🧠</div><div class="message-body"><div class="message-header"><span class="message-sender">Document AI</span><span class="message-time">${formatTime()}</span></div><div class="message-content"><div class="loading-dots"><span></span><span></span><span></span></div></div></div>`;
  container.appendChild(msg);
  container.scrollTop = container.scrollHeight;

  const content = msg.querySelector('.message-content');
  let fullText = '';

  try {
    const res = await fetch('/query-stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q, history: chatHistory.slice(-10) }),
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
          content.textContent = fullText;
          container.scrollTop = container.scrollHeight;
        }
      }
    }

    if (!fullText) content.textContent = 'No response';
    chatHistory.push({ role: 'assistant', content: fullText });
  } catch {
    content.textContent = '❌ Stream failed';
  }
}

function addMessage(role, content, sources = []) {
  const welcome = document.getElementById('chatWelcome');
  if (welcome) welcome.style.display = 'none';

  const container = document.getElementById('chatMessages');
  const msg = document.createElement('div');
  msg.className = 'message';

  const avatar = role === 'user' ? '👤' : '🧠';
  const name = role === 'user' ? 'You' : 'Document AI';

  let sourcesHtml = '';
  if (sources.length) {
    const chips = sources.map(s => {
      return `<span class="source-chip" data-source='${escapeHtml(JSON.stringify(s))}'>${escapeHtml(s.source)} p.${s.page}</span>`;
    }).join('');
    sourcesHtml = `<div style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border);"><div style="font-size:11px;font-weight:700;color:var(--text-3);margin-bottom:4px;">📎 ${sources.length} Source(s)</div>${chips}</div>`;
  }

  msg.innerHTML = `<div class="message-avatar${role === 'user' ? ' message-avatar--user' : ''}">${avatar}</div><div class="message-body"><div class="message-header"><span class="message-sender">${name}</span><span class="message-time">${formatTime()}</span></div><div class="message-content">${role === 'user' ? escapeHtml(content) : content}</div>${sourcesHtml}</div>`;
  container.appendChild(msg);
  container.scrollTop = container.scrollHeight;

  chatHistory.push({ role, content });
  if (chatHistory.length > 20) chatHistory = chatHistory.slice(-20);

  return msg;
}

// Quick actions
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('welcome-card')) {
    const action = e.target.dataset.action;
    if (action === 'overview') {
      document.getElementById('chatInput').value = 'What is this document about?';
      sendQuery();
    } else if (action === 'summarize') {
      document.getElementById('chatInput').value = 'Summarize the key points';
      sendQuery();
    } else if (action === 'upload') {
      switchPanel('upload');
    } else if (action === 'compare') {
      switchPanel('compare');
    }
  }

  if (e.target.classList.contains('source-chip')) {
    const source = JSON.parse(e.target.dataset.source);
    document.getElementById('sourceModalTitle').textContent = `${source.source} — Page ${source.page}`;
    document.getElementById('sourceModalBody').textContent = source.excerpt || 'No excerpt';
    openModal('sourceModal');
  }

  if (e.target.classList.contains('modal-close')) {
    closeModal(e.target.dataset.modal);
  }
});

// Compare
function populateCompare() {
  ['compareDocA', 'compareDocB'].forEach(id => {
    const sel = document.getElementById(id);
    const current = sel.value;
    sel.innerHTML = '<option value="">Select...</option>' + allDocuments.map(d => `<option value="${escapeHtml(d.filename)}">${escapeHtml(d.filename)}</option>`).join('');
    sel.value = current;
  });
}

async function compareDocuments() {
  const a = document.getElementById('compareDocA').value;
  const b = document.getElementById('compareDocB').value;
  if (!a || !b) {
    showToast('Select both documents', 'error');
    return;
  }

  const result = document.getElementById('compareResult');
  result.classList.add('active');
  result.innerHTML = '<div class="loading-dots"><span></span><span></span><span></span></div>';

  try {
    const data = await apiCall('/compare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ doc_a: a, doc_b: b, question: document.getElementById('compareQuestion').value }),
    });
    result.innerHTML = escapeHtml(data.comparison || JSON.stringify(data, null, 2));
  } catch {
    result.innerHTML = 'Failed';
  }
}

// Extract
async function extractFields() {
  const fields = document.getElementById('extractFields').value.trim();
  if (!fields) {
    showToast('Enter field names', 'error');
    return;
  }

  const result = document.getElementById('extractResult');
  result.classList.add('active');
  result.innerHTML = '<div class="loading-dots"><span></span><span></span><span></span></div>';

  try {
    const data = await apiCall('/extract', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fields: fields.split('\n').map(f => f.trim()).filter(Boolean) }),
    });
    result.innerHTML = `<pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre>`;
  } catch {}
}

// Summarize
async function getSummary() {
  const topic = document.getElementById('summaryTopic').value.trim() || 'document';
  const result = document.getElementById('summaryResult');
  result.classList.add('active');
  result.innerHTML = '<div class="loading-dots"><span></span><span></span><span></span></div>';

  try {
    const data = await apiCall('/summarize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topic }),
    });
    result.textContent = data.summary || 'No summary';
  } catch {}
}

// Analytics
async function loadAnalytics() {
  try {
    const data = await apiCall('/analytics');
    const stats = document.getElementById('analyticsStats');
    stats.innerHTML = `
      <div class="stat-card">
        <div class="stat-card-label">Total Vectors</div>
        <div class="stat-card-value">${(data.total_vectors || 0).toLocaleString()}</div>
      </div>
      <div class="stat-card">
        <div class="stat-card-label">Documents</div>
        <div class="stat-card-value">${(data.sources || []).length}</div>
      </div>
      <div class="stat-card">
        <div class="stat-card-label">Index Size</div>
        <div class="stat-card-value">${data.storage?.index_size_mb || 0} MB</div>
      </div>
      <div class="stat-card">
        <div class="stat-card-label">Cache Hits</div>
        <div class="stat-card-value">${data.cache?.hits || 0}</div>
      </div>`;

    const breakdown = document.getElementById('sourceBreakdown');
    const sources = data.source_breakdown || [];
    if (sources.length) {
      breakdown.innerHTML = sources.map(s => `<div class="breakdown-item"><span>${escapeHtml(s.source)}</span><span>${s.chunks} chunks</span></div>`).join('');
    } else {
      breakdown.innerHTML = '<div style="text-align:center;color:var(--text-3);">No sources</div>';
    }
  } catch {}
}

// RAGAS
async function loadRAGAS() {
  try {
    const data = await apiCall('/evaluate/dashboard');
    const stats = document.getElementById('ragasStats');
    stats.innerHTML = `
      <div class="stat-card">
        <div class="stat-card-label">Total</div>
        <div class="stat-card-value">${data.total_evaluations || 0}</div>
      </div>
      <div class="stat-card">
        <div class="stat-card-label">Average</div>
        <div class="stat-card-value">${((data.avg_overall || 0) * 100).toFixed(1)}%</div>
      </div>`;

    const history = await apiCall('/evaluate/history?limit=10');
    const historyEl = document.getElementById('ragasHistory');
    if (history.length) {
      historyEl.innerHTML = history.map(h => `<div class="history-item"><span>${escapeHtml(h.question)}</span><span>${((h.overall_score || 0) * 100).toFixed(0)}%</span></div>`).join('');
    } else {
      historyEl.innerHTML = '<div style="text-align:center;color:var(--text-3);padding:16px;">No evaluations</div>';
    }
  } catch {}
}

// Panel navigation
function switchPanel(name) {
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('panel--active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('nav-item--active'));

  const panel = document.getElementById(`panel-${name}`);
  if (panel) panel.classList.add('panel--active');

  const nav = document.querySelector(`.nav-item[data-panel="${name}"]`);
  if (nav) nav.classList.add('nav-item--active');

  if (name === 'compare') populateCompare();
  else if (name === 'analytics') loadAnalytics();
  else if (name === 'ragas') loadRAGAS();
}

// Settings
async function clearCache() {
  try {
    await apiCall('/cache/clear', { method: 'POST' });
    showToast('Cache cleared', 'success');
  } catch {}
}

async function clearIndex() {
  if (!confirm('Delete ALL documents?')) return;
  try {
    await apiCall('/clear', { method: 'POST' });
    showToast('Index cleared', 'success');
    location.reload();
  } catch {}
}

// Init
document.addEventListener('DOMContentLoaded', () => {
  initTheme();

  // Navigation
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => switchPanel(item.dataset.panel));
  });

  document.getElementById('newChatBtn')?.addEventListener('click', () => switchPanel('chat'));
  document.getElementById('uploadBtn')?.addEventListener('click', () => switchPanel('upload'));

  // Chat
  const chatInput = document.getElementById('chatInput');
  chatInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendQuery();
    }
  });
  chatInput?.addEventListener('input', () => {
    chatInput.style.height = 'auto';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
  });

  document.getElementById('sendBtn')?.addEventListener('click', sendQuery);

  // Upload
  const zone = document.getElementById('uploadZone');
  const fileInput = document.getElementById('fileInput');

  zone?.addEventListener('click', () => fileInput.click());
  zone?.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone?.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone?.addEventListener('drop', (e) => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    uploadFiles(e.dataTransfer.files);
  });

  fileInput?.addEventListener('change', (e) => {
    uploadFiles(e.target.files);
    e.target.value = '';
  });

  document.getElementById('ingestBtn')?.addEventListener('click', ingestUrl);

  // Compare
  document.getElementById('compareBtn')?.addEventListener('click', compareDocuments);

  // Extract
  document.getElementById('extractBtn')?.addEventListener('click', extractFields);

  // Summarize
  document.getElementById('summarizeBtn')?.addEventListener('click', getSummary);

  // RAGAS
  document.getElementById('refreshRagasBtn')?.addEventListener('click', loadRAGAS);
  document.getElementById('clearRagasBtn')?.addEventListener('click', async () => {
    if (!confirm('Clear all?')) return;
    try {
      await apiCall('/evaluate/clear', { method: 'POST' });
      showToast('Cleared', 'success');
      loadRAGAS();
    } catch {}
  });

  // Settings
  document.getElementById('settingsBtn')?.addEventListener('click', () => openModal('settingsModal'));
  document.getElementById('streamOn')?.addEventListener('click', () => {
    streaming = true;
    document.getElementById('streamOn').classList.add('toggle--active');
    document.getElementById('streamOff').classList.remove('toggle--active');
    showToast('Streaming enabled', 'info');
  });
  document.getElementById('streamOff')?.addEventListener('click', () => {
    streaming = false;
    document.getElementById('streamOff').classList.add('toggle--active');
    document.getElementById('streamOn').classList.remove('toggle--active');
    showToast('Streaming disabled', 'info');
  });
  document.getElementById('cacheBtn')?.addEventListener('click', clearCache);
  document.getElementById('clearIndexBtn')?.addEventListener('click', clearIndex);

  // Initial load
  checkStatus();
  loadDocuments();

  // Auto refresh
  setInterval(checkStatus, 30000);
  setInterval(loadDocuments, 60000);
});
