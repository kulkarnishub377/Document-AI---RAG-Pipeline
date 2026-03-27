// ═════════════════════════════════════════════════════════════════════════════
// Document AI + RAG Pipeline v3.0 — Frontend Application
// Clean, Modular, Professional JavaScript Architecture
// ═════════════════════════════════════════════════════════════════════════════

'use strict';

// ─────────────────────────────────────────────────────────────────────────────
// 1. Utilities & Helpers
// ─────────────────────────────────────────────────────────────────────────────

class HTMLUtils {
  static escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  static formatTime() {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  static getFileIcon(ext) {
    const map = {
      '.pdf': ['📕', 'pdf'], '.docx': ['📘', 'doc'], '.doc': ['📘', 'doc'],
      '.xlsx': ['📗', 'xls'], '.xls': ['📗', 'xls'], '.csv': ['📊', 'csv'],
      '.pptx': ['📙', 'ppt'], '.png': ['🖼️', 'img'], '.jpg': ['🖼️', 'img'],
      '.jpeg': ['🖼️', 'img'], '.tiff': ['🖼️', 'img'],
      '.txt': ['📄', 'txt'], '.md': ['📄', 'txt'],
    };
    return map[ext] || ['📄', 'txt'];
  }

  static getConfidenceClass(score) {
    if (score >= 0.75) return 'high';
    if (score >= 0.5) return 'mid';
    return 'low';
  }

  static getConfidenceLabel(score) {
    if (score >= 0.75) return 'High';
    if (score >= 0.5) return 'Medium';
    return 'Low';
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 2. Toast Notifications
// ─────────────────────────────────────────────────────────────────────────────

class ToastManager {
  constructor() {
    this.container = document.getElementById('toastContainer');
  }

  show(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `app-toast app-toast--${type}`;
    toast.textContent = message;
    this.container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 3. API Client
// ─────────────────────────────────────────────────────────────────────────────

class ApiClient {
  constructor(toastManager) {
    this.toastManager = toastManager;
  }

  async request(path, options = {}) {
    try {
      const res = await fetch(path, options);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || err.message || `HTTP ${res.status}`);
      }
      return await res.json();
    } catch (err) {
      this.toastManager.show(err.message, 'error');
      throw err;
    }
  }

  async get(path) {
    return this.request(path);
  }

  async post(path, data) {
    return this.request(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  }

  async postForm(path, formData) {
    return this.request(path, {
      method: 'POST',
      body: formData,
    });
  }

  async delete(path) {
    return this.request(path, { method: 'DELETE' });
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 4. Modal Manager
// ─────────────────────────────────────────────────────────────────────────────

class ModalManager {
  open(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.classList.add('active');
  }

  close(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.classList.remove('active');
  }

  closeAllOn(overlayId) {
    const overlay = document.getElementById(overlayId);
    if (overlay) {
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) overlay.classList.remove('active');
      });
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 5. Theme Manager
// ─────────────────────────────────────────────────────────────────────────────

class ThemeManager {
  constructor() {
    this.select = document.getElementById('themeSelect');
    this.init();
  }

  init() {
    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    this.select.value = savedTheme;
    this.select.addEventListener('change', (e) => this.setTheme(e.target.value));
  }

  setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 6. Panel Manager
// ─────────────────────────────────────────────────────────────────────────────

class PanelManager {
  constructor(callbacks = {}) {
    this.callbacks = callbacks;
    this.currentPanel = 'chat';
    this.init();
  }

  init() {
    document.querySelectorAll('.app-nav-item').forEach(item => {
      item.addEventListener('click', () => this.switchPanel(item.dataset.panel));
    });

    // Quick actions
    document.querySelectorAll('.app-quick-action').forEach(action => {
      action.addEventListener('click', () => {
        const actionType = action.dataset.action;
        if (actionType === 'overview') this.quickAsk('What is this document about?');
        else if (actionType === 'summarize') this.quickAsk('Summarize the key points');
        else if (actionType === 'upload') this.switchPanel('upload');
      });
    });
  }

  switchPanel(panelName) {
    // Hide all panels
    document.querySelectorAll('.app-panel').forEach(p => p.classList.remove('app-panel--active'));
    document.querySelectorAll('.app-nav-item').forEach(n => n.classList.remove('app-nav-item--active'));

    // Show selected panel
    const panel = document.getElementById(`panel-${panelName}`);
    if (panel) panel.classList.add('app-panel--active');

    const navItem = document.querySelector(`.app-nav-item[data-panel="${panelName}"]`);
    if (navItem) navItem.classList.add('app-nav-item--active');

    this.currentPanel = panelName;

    // Trigger panel callbacks
    if (this.callbacks[panelName]) {
      this.callbacks[panelName]();
    }
  }

  quickAsk(question) {
    document.getElementById('chatInput').value = question;
    this.switchPanel('chat');
    if (this.callbacks.sendQuery) this.callbacks.sendQuery();
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 7. Status Handler
// ─────────────────────────────────────────────────────────────────────────────

class StatusHandler {
  constructor(apiClient) {
    this.apiClient = apiClient;
  }

  async check() {
    try {
      const data = await this.apiClient.get('/status');
      const dot = document.getElementById('statusDot');
      const text = document.getElementById('statusText');
      const isOnline = data.ollama === 'connected';

      dot.className = `app-status-dot ${isOnline ? 'app-status-dot--online' : 'app-status-dot--offline'}`;
      text.textContent = isOnline
        ? `${data.total_vectors || 0} vectors indexed`
        : 'Ollama offline';
    } catch {
      document.getElementById('statusDot').className = 'app-status-dot app-status-dot--offline';
      document.getElementById('statusText').textContent = 'Server offline';
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 8. Document Management
// ─────────────────────────────────────────────────────────────────────────────

class DocumentManager {
  constructor(apiClient, toastManager) {
    this.apiClient = apiClient;
    this.toastManager = toastManager;
    this.documents = [];
  }

  async load() {
    try {
      this.documents = await this.apiClient.get('/documents');
      this.render();
    } catch {
      // Error handled by API client
    }
  }

  render() {
    const list = document.getElementById('fileList');
    const count = document.getElementById('fileCount');
    count.textContent = this.documents.length;

    if (!this.documents.length) {
      list.innerHTML = '<p style="font-size:12px;color:var(--app-text-muted);text-align:center;padding:20px;">No documents uploaded yet</p>';
      return;
    }

    list.innerHTML = this.documents.map(doc => this.createFileItem(doc)).join('');
  }

  createFileItem(doc) {
    const [icon, cls] = HTMLUtils.getFileIcon(doc.suffix);
    return `
      <div class="app-file-item">
        <div class="app-file-icon app-file-icon--${cls}">${icon}</div>
        <div class="app-file-info">
          <div class="app-file-name">${HTMLUtils.escapeHtml(doc.filename)}</div>
          <div class="app-file-meta">${doc.size_mb} MB</div>
        </div>
        <button class="app-file-delete" data-filename="${HTMLUtils.escapeHtml(doc.filename)}">🗑️</button>
      </div>`;
  }

  async delete(filename) {
    if (!confirm(`Delete "${filename}" from index?`)) return;
    try {
      await this.apiClient.delete(`/document/${encodeURIComponent(filename)}`);
      this.toastManager.show(`Deleted ${filename}`, 'success');
      this.load();
    } catch {
      // Error handled by API client
    }
  }

  attachDeleteHandlers() {
    document.querySelectorAll('.app-file-delete').forEach(btn => {
      btn.addEventListener('click', () => this.delete(btn.dataset.filename));
    });
  }

  getNames() {
    return this.documents.map(d => d.filename);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 9. Upload Handler
// ─────────────────────────────────────────────────────────────────────────────

class UploadHandler {
  constructor(apiClient, toastManager, documentManager) {
    this.apiClient = apiClient;
    this.toastManager = toastManager;
    this.documentManager = documentManager;
    this.init();
  }

  init() {
    const zone = document.getElementById('uploadZone');
    const fileInput = document.getElementById('fileInput');
    const urlInput = document.getElementById('urlInput');
    const ingestBtn = document.getElementById('ingestBtn');

    zone.addEventListener('click', () => fileInput.click());
    zone.addEventListener('dragover', (e) => {
      e.preventDefault();
      zone.classList.add('drag-over');
    });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', (e) => this.handleDrop(e));

    fileInput.addEventListener('change', (e) => this.handleFileSelect(e));
    ingestBtn.addEventListener('click', () => this.ingestUrl());
  }

  handleDrop(e) {
    e.preventDefault();
    document.getElementById('uploadZone').classList.remove('drag-over');
    if (e.dataTransfer.files.length) this.uploadFiles(e.dataTransfer.files);
  }

  handleFileSelect(e) {
    this.uploadFiles(e.target.files);
    e.target.value = '';
  }

  async uploadFiles(files) {
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
        const result = await this.apiClient.postForm('/ingest', formData);
        this.toastManager.show(`✓ ${result.file}: ${result.chunks} chunks indexed`, 'success');
      } catch {
        // Error handled by API client
      }

      fill.style.width = `${((i + 1) / files.length) * 100}%`;
    }

    text.textContent = 'Done!';
    setTimeout(() => {
      progress.style.display = 'none';
      fill.style.width = '0%';
    }, 2000);

    this.documentManager.load();
  }

  async ingestUrl() {
    const input = document.getElementById('urlInput');
    const url = input.value.trim();
    if (!url) return;

    try {
      const result = await this.apiClient.post('/ingest/url', { url });
      this.toastManager.show(`✓ ${result.file}: ${result.chunks} chunks indexed`, 'success');
      input.value = '';
      this.documentManager.load();
    } catch {
      // Error handled by API client
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 10. Chat Manager
// ─────────────────────────────────────────────────────────────────────────────

class ChatManager {
  constructor(apiClient, toastManager) {
    this.apiClient = apiClient;
    this.toastManager = toastManager;
    this.history = [];
    this.isQuerying = false;
    this.streaming = true;
    this.init();
  }

  init() {
    const input = document.getElementById('chatInput');
    const sendBtn = document.getElementById('sendBtn');

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.sendQuery();
      }
    });
    input.addEventListener('input', () => this.autoResizeInput());
    sendBtn.addEventListener('click', () => this.sendQuery());
  }

  autoResizeInput() {
    const input = document.getElementById('chatInput');
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
  }

  async sendQuery() {
    const input = document.getElementById('chatInput');
    const question = input.value.trim();
    if (!question || this.isQuerying) return;

    input.value = '';
    this.autoResizeInput();
    this.addMessage('user', question);
    this.isQuerying = true;
    document.getElementById('sendBtn').disabled = true;

    try {
      if (this.streaming) {
        await this.streamQuery(question);
      } else {
        await this.syncQuery(question);
      }
    } finally {
      this.isQuerying = false;
      document.getElementById('sendBtn').disabled = false;
    }
  }

  async syncQuery(question) {
    try {
      const result = await this.apiClient.post('/query', {
        question,
        history: this.history.slice(-10),
      });
      const msgEl = this.addMessage('ai', HTMLUtils.escapeHtml(result.answer), result.sources || []);
      this.addSuggestedQuestions(msgEl);
    } catch {
      this.addMessage('ai', '❌ Failed to get answer. Check if Ollama is running.');
    }
  }

  async streamQuery(question) {
    const welcome = document.getElementById('chatWelcome');
    if (welcome) welcome.style.display = 'none';

    const container = document.getElementById('chatMessages');
    const msg = document.createElement('div');
    msg.className = 'app-message app-message--ai';
    msg.innerHTML = `
      <div class="app-message-avatar app-message-avatar--ai">🧠</div>
      <div class="app-message-body">
        <div class="app-message-header">
          <span class="app-message-sender">Document AI</span>
          <span class="app-message-time">${HTMLUtils.formatTime()}</span>
        </div>
        <div class="app-message-content"><div class="app-loading-dots"><span></span><span></span><span></span></div></div>
      </div>`;
    container.appendChild(msg);
    container.scrollTop = container.scrollHeight;

    const contentEl = msg.querySelector('.app-message-content');
    let fullText = '';

    try {
      const res = await fetch('/query-stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question,
          history: this.history.slice(-10),
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
      this.history.push({ role: 'assistant', content: fullText });
      this.addSuggestedQuestions(msg);
    } catch {
      contentEl.textContent = '❌ Stream failed. Check if Ollama is running.';
    }
  }

  addMessage(role, content, sources = []) {
    const welcome = document.getElementById('chatWelcome');
    if (welcome) welcome.style.display = 'none';

    const container = document.getElementById('chatMessages');
    const msg = document.createElement('div');
    msg.className = `app-message app-message--${role}`;

    const avatar = role === 'user' ? '👤' : '🧠';
    const sender = role === 'user' ? 'You' : 'Document AI';

    let sourcesHtml = '';
    if (sources.length) {
      const sourcesChips = sources.map(s => {
        const cls = HTMLUtils.getConfidenceClass(s.score || 0);
        return `<span class="app-source-chip" data-source='${HTMLUtils.escapeHtml(JSON.stringify(s))}'>
          📄 ${HTMLUtils.escapeHtml(s.source)} p.${s.page}
          <span class="app-source-score app-score--${cls}">${((s.score || 0) * 100).toFixed(0)}%</span>
          <span class="app-confidence-badge app-confidence-badge--${cls}">${HTMLUtils.getConfidenceLabel(s.score || 0)}</span>
        </span>`;
      }).join('');

      sourcesHtml = `<div class="app-sources">
        <div class="app-sources-title">📎 Sources (${sources.length})</div>
        ${sourcesChips}
      </div>`;
    }

    msg.innerHTML = `
      <div class="app-message-avatar app-message-avatar--${role}">${avatar}</div>
      <div class="app-message-body">
        <div class="app-message-header">
          <span class="app-message-sender">${sender}</span>
          <span class="app-message-time">${HTMLUtils.formatTime()}</span>
        </div>
        <div class="app-message-content">${role === 'user' ? HTMLUtils.escapeHtml(content) : content}</div>
        ${sourcesHtml}
      </div>`;

    container.appendChild(msg);
    container.scrollTop = container.scrollHeight;

    this.history.push({ role, content: typeof content === 'string' ? content : '' });
    if (this.history.length > 20) this.history = this.history.slice(-20);

    return msg;
  }

  addSuggestedQuestions(msgEl) {
    const suggestions = [
      "What are the key takeaways?",
      "Can you provide more detail on this?",
      "Where exactly is this mentioned in the source?",
      "Summarize the main points briefly."
    ];

    const shuffled = suggestions.sort(() => 0.5 - Math.random()).slice(0, 3);
    const container = document.createElement('div');
    container.className = 'app-suggested-questions';

    shuffled.forEach(q => {
      const pill = document.createElement('span');
      pill.className = 'app-suggested-pill';
      pill.textContent = q;
      pill.addEventListener('click', () => {
        document.getElementById('chatInput').value = q;
        this.sendQuery();
      });
      container.appendChild(pill);
    });

    const body = msgEl.querySelector('.app-message-body');
    if (body) body.appendChild(container);

    const messages = document.getElementById('chatMessages');
    messages.scrollTop = messages.scrollHeight;
  }

  setStreaming(on) {
    this.streaming = on;
    document.getElementById('streamOn').className = on ? 'app-btn app-btn--primary' : 'app-btn app-btn--secondary';
    document.getElementById('streamOff').className = on ? 'app-btn app-btn--secondary' : 'app-btn app-btn--primary';
    this.toastManager.show(`Streaming ${on ? 'enabled' : 'disabled'}`, 'info');
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 11. Analytics Manager
// ─────────────────────────────────────────────────────────────────────────────

class AnalyticsManager {
  constructor(apiClient) {
    this.apiClient = apiClient;
  }

  async load() {
    try {
      const data = await this.apiClient.get('/analytics');
      this.renderStats(data);
      this.renderBreakdown(data.source_breakdown || []);
    } catch {
      // Error handled by API client
    }
  }

  renderStats(data) {
    const grid = document.getElementById('analyticsStats');
    grid.innerHTML = `
      <div class="app-stat-card">
        <div class="app-stat-label">Total Vectors</div>
        <div class="app-stat-value">${(data.total_vectors || 0).toLocaleString()}</div>
      </div>
      <div class="app-stat-card">
        <div class="app-stat-label">Documents</div>
        <div class="app-stat-value">${(data.sources || []).length}</div>
      </div>
      <div class="app-stat-card">
        <div class="app-stat-label">Index Size</div>
        <div class="app-stat-value">${data.storage?.index_size_mb || 0} MB</div>
      </div>
      <div class="app-stat-card">
        <div class="app-stat-label">Total Storage</div>
        <div class="app-stat-value">${data.storage?.total_size_mb || 0} MB</div>
      </div>
      <div class="app-stat-card">
        <div class="app-stat-label">Cache Hits</div>
        <div class="app-stat-value app-stat-value--success">${data.cache?.hits || 0}</div>
        <div class="app-stat-sub">Hit rate: ${data.cache?.hit_rate || '0%'}</div>
      </div>
      <div class="app-stat-card">
        <div class="app-stat-label">Ollama</div>
        <div class="app-stat-value ${data.ollama === 'connected' ? 'app-stat-value--success' : 'app-stat-value--warning'}">${data.ollama === 'connected' ? 'Online' : 'Offline'}</div>
      </div>`;
  }

  renderBreakdown(sources) {
    const breakdown = document.getElementById('sourceBreakdown');
    if (sources.length) {
      breakdown.innerHTML = sources.map(s => `
        <div class="app-breakdown-item">
          <span>${HTMLUtils.escapeHtml(s.source)}</span>
          <span>${s.chunks} chunks</span>
        </div>`).join('');
    } else {
      breakdown.innerHTML = '<p style="font-size:13px;color:var(--app-text-muted);text-align:center;padding:16px;">No documents indexed</p>';
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 12. Compare Manager
// ─────────────────────────────────────────────────────────────────────────────

class CompareManager {
  constructor(apiClient, documentManager) {
    this.apiClient = apiClient;
    this.documentManager = documentManager;
    this.init();
  }

  init() {
    document.getElementById('compareBtn').addEventListener('click', () => this.compare());
  }

  populateSelectors() {
    const docs = this.documentManager.getNames();
    ['compareDocA', 'compareDocB'].forEach(id => {
      const sel = document.getElementById(id);
      const current = sel.value;
      sel.innerHTML = '<option value="">Select document...</option>' +
        docs.map(d => `<option value="${HTMLUtils.escapeHtml(d)}">${HTMLUtils.escapeHtml(d)}</option>`).join('');
      if (current) sel.value = current;
    });
  }

  async compare() {
    const docA = document.getElementById('compareDocA').value;
    const docB = document.getElementById('compareDocB').value;
    const question = document.getElementById('compareQuestion').value;

    if (!docA || !docB) {
      alert('Select both documents to compare');
      return;
    }

    const result = document.getElementById('compareResult');
    result.classList.add('active');
    result.innerHTML = '<div class="app-loading-dots"><span></span><span></span><span></span></div>';

    try {
      const data = await this.apiClient.post('/compare', { doc_a: docA, doc_b: docB, question });
      result.innerHTML = HTMLUtils.escapeHtml(data.comparison || data.error || JSON.stringify(data, null, 2));
    } catch {
      result.innerHTML = 'Comparison failed.';
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 13. Extract Manager
// ─────────────────────────────────────────────────────────────────────────────

class ExtractManager {
  constructor(apiClient, toastManager) {
    this.apiClient = apiClient;
    this.toastManager = toastManager;
    this.init();
  }

  init() {
    document.getElementById('extractBtn').addEventListener('click', () => this.extract());
  }

  async extract() {
    const fieldsText = document.getElementById('extractFields').value.trim();
    if (!fieldsText) {
      this.toastManager.show('Enter at least one field name', 'error');
      return;
    }

    const fields = fieldsText.split('\n').map(f => f.trim()).filter(Boolean);
    const result = document.getElementById('extractResult');
    result.innerHTML = '<div class="app-loading-dots"><span></span><span></span><span></span></div>';

    try {
      const data = await this.apiClient.post('/extract', { fields });
      result.innerHTML = `<pre>${HTMLUtils.escapeHtml(JSON.stringify(data, null, 2))}</pre>`;
    } catch {
      result.innerHTML = 'Extraction failed.';
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 14. Summarize Manager
// ─────────────────────────────────────────────────────────────────────────────

class SummarizeManager {
  constructor(apiClient) {
    this.apiClient = apiClient;
    this.init();
  }

  init() {
    document.getElementById('summarizeBtn').addEventListener('click', () => this.summarize());
  }

  async summarize() {
    const topic = document.getElementById('summaryTopic').value.trim() || 'the document';
    const result = document.getElementById('summaryResult');
    result.classList.add('active');
    result.innerHTML = '<div class="app-loading-dots"><span></span><span></span><span></span></div>';

    try {
      const data = await this.apiClient.post('/summarize', { topic });
      result.textContent = data.summary || 'No summary generated.';
    } catch {
      result.textContent = 'Summary failed.';
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 15. RAGAS Manager
// ─────────────────────────────────────────────────────────────────────────────

class RAGASManager {
  constructor(apiClient, toastManager) {
    this.apiClient = apiClient;
    this.toastManager = toastManager;
    this.init();
  }

  init() {
    document.getElementById('refreshRagasBtn').addEventListener('click', () => this.load());
    document.getElementById('clearRagasBtn').addEventListener('click', () => this.clearHistory());
  }

  createScoreRing(elementId, score, color) {
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
      <div class="app-ragas-score-value" style="color:${color}">${(score * 100).toFixed(0)}%</div>`;
  }

  async load() {
    try {
      const data = await this.apiClient.get('/evaluate/dashboard');

      this.createScoreRing('ringFaith', data.avg_faithfulness || 0, '#00cec9');
      this.createScoreRing('ringRelevancy', data.avg_answer_relevancy || 0, '#6c5ce7');
      this.createScoreRing('ringPrecision', data.avg_context_precision || 0, '#fdcb6e');
      this.createScoreRing('ringRecall', data.avg_context_recall || 0, '#fd79a8');

      this.renderStats(data);
      this.renderHistory(data);
    } catch {
      // Error handled by API client
    }
  }

  renderStats(data) {
    const stats = document.getElementById('ragasStats');
    stats.innerHTML = `
      <div class="app-stat-card">
        <div class="app-stat-label">Total Evaluations</div>
        <div class="app-stat-value">${data.total_evaluations || 0}</div>
      </div>
      <div class="app-stat-card">
        <div class="app-stat-label">Overall Average</div>
        <div class="app-stat-value app-stat-value--success">${((data.avg_overall || 0) * 100).toFixed(1)}%</div>
      </div>
      <div class="app-stat-card">
        <div class="app-stat-label">Best Score</div>
        <div class="app-stat-value app-stat-value--success">${((data.best_score || 0) * 100).toFixed(1)}%</div>
      </div>
      <div class="app-stat-card">
        <div class="app-stat-label">Worst Score</div>
        <div class="app-stat-value" style="color:var(--app-danger)">${((data.worst_score || 0) * 100).toFixed(1)}%</div>
      </div>`;
  }

  async renderHistory(data) {
    try {
      const history = await this.apiClient.get('/evaluate/history?limit=10');
      const historyEl = document.getElementById('ragasHistory');

      if (history.length) {
        historyEl.innerHTML = history.map(h => `
          <div class="app-ragas-history-item">
            <div class="app-ragas-history-question">
              <span>${HTMLUtils.escapeHtml(h.question)}</span>
              <span class="app-confidence-badge app-confidence-badge--${HTMLUtils.getConfidenceClass(h.overall_score || 0)}">${((h.overall_score || 0) * 100).toFixed(0)}%</span>
            </div>
            <div class="app-ragas-history-scores">
              <span>Faith: ${((h.faithfulness || 0) * 100).toFixed(0)}%</span>
              <span>Rel: ${((h.answer_relevancy || 0) * 100).toFixed(0)}%</span>
              <span>Prec: ${((h.context_precision || 0) * 100).toFixed(0)}%</span>
              <span>Rec: ${((h.context_recall || 0) * 100).toFixed(0)}%</span>
            </div>
          </div>`).join('');
      } else {
        historyEl.innerHTML = '<p style="text-align:center;color:var(--app-text-muted);font-size:13px;padding:16px;">No evaluations yet</p>';
      }
    } catch {
      // Error handled
    }
  }

  async clearHistory() {
    if (!confirm('Clear all evaluation history?')) return;
    try {
      await this.apiClient.post('/evaluate/clear', {});
      this.toastManager.show('Evaluation history cleared', 'success');
      this.load();
    } catch {
      // Error handled
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 16. Settings Manager
// ─────────────────────────────────────────────────────────────────────────────

class SettingsManager {
  constructor(apiClient, toastManager, chatManager) {
    this.apiClient = apiClient;
    this.toastManager = toastManager;
    this.chatManager = chatManager;
    this.init();
  }

  init() {
    document.getElementById('streamOn').addEventListener('click', () => this.chatManager.setStreaming(true));
    document.getElementById('streamOff').addEventListener('click', () => this.chatManager.setStreaming(false));
    document.getElementById('cacheBtn').addEventListener('click', () => this.clearCache());
    document.getElementById('clearIndexBtn').addEventListener('click', () => this.clearIndex());
  }

  async clearCache() {
    try {
      await this.apiClient.post('/cache/clear', {});
      this.toastManager.show('Query cache cleared', 'success');
    } catch {
      // Error handled
    }
  }

  async clearIndex() {
    if (!confirm('This will delete ALL indexed documents. Are you sure?')) return;
    try {
      await this.apiClient.post('/clear', {});
      this.toastManager.show('Index cleared', 'success');
      location.reload();
    } catch {
      // Error handled
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 17. Application Bootstrap
// ─────────────────────────────────────────────────────────────────────────────

class Application {
  constructor() {
    this.toastManager = new ToastManager();
    this.apiClient = new ApiClient(this.toastManager);
    this.modalManager = new ModalManager();
    this.themeManager = new ThemeManager();
    this.statusHandler = new StatusHandler(this.apiClient);
    this.documentManager = new DocumentManager(this.apiClient, this.toastManager);
    this.chatManager = new ChatManager(this.apiClient, this.toastManager);
    this.uploadHandler = new UploadHandler(this.apiClient, this.toastManager, this.documentManager);
    this.analyticsManager = new AnalyticsManager(this.apiClient);
    this.compareManager = new CompareManager(this.apiClient, this.documentManager);
    this.extractManager = new ExtractManager(this.apiClient, this.toastManager);
    this.summarizeManager = new SummarizeManager(this.apiClient);
    this.ragasManager = new RAGASManager(this.apiClient, this.toastManager);
    this.settingsManager = new SettingsManager(this.apiClient, this.toastManager, this.chatManager);

    this.panelManager = new PanelManager({
      analytics: () => this.analyticsManager.load(),
      ragas: () => this.ragasManager.load(),
      compare: () => this.compareManager.populateSelectors(),
      sendQuery: () => this.chatManager.sendQuery(),
    });
  }

  async init() {
    this.statusHandler.check();
    this.documentManager.load();

    // Modal setup
    document.getElementById('settingsBtn').addEventListener('click', () => this.modalManager.open('settingsModal'));
    document.querySelectorAll('.app-icon-btn--close').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const modal = e.target.closest('.app-modal');
        if (modal) modal.parentElement.classList.remove('active');
      });
    });

    this.modalManager.closeAllOn('settingsModal');
    this.modalManager.closeAllOn('sourceModal');

    // Document delete handlers
    this.documentManager.attachDeleteHandlers();

    // Source modal setup
    document.addEventListener('click', (e) => {
      if (e.target.classList.contains('app-source-chip')) {
        const source = JSON.parse(e.target.dataset.source);
        document.getElementById('sourceModalTitle').textContent = `${source.source} — Page ${source.page}`;
        document.getElementById('sourceModalBody').textContent = source.excerpt || 'No excerpt available';
        this.modalManager.open('sourceModal');
      }
    });

    // Auto refresh
    setInterval(() => this.statusHandler.check(), 30000);
    setInterval(() => this.documentManager.load(), 60000);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 18. Initialization
// ─────────────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  const app = new Application();
  app.init();
});
