// ═════════════════════════════════════════════════════════════════════════════
// Document AI Pro - Advanced Frontend Application
// Production-Ready with Full Feature Set
// ═════════════════════════════════════════════════════════════════════════════

'use strict';

// Core Utilities
const Utils = {
  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  },

  getFileIcon(ext) {
    const map = {
      '.pdf': '📕', '.docx': '📘', '.doc': '📘', '.xlsx': '📗', '.xls': '📗',
      '.csv': '📊', '.pptx': '📙', '.png': '🖼️', '.jpg': '🖼️',
      '.jpeg': '🖼️', '.tiff': '🖼️', '.txt': '📄', '.md': '📄',
    };
    return map[ext] || '📄';
  },

  formatTime() {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  },
};

// Toast System
const Toast = {
  show(msg, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `ui-toast ui-toast--${type}`;
    toast.textContent = msg;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  },
};

// API Client
const API = {
  async request(path, options = {}) {
    try {
      const res = await fetch(path, options);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || err.message || `HTTP ${res.status}`);
      }
      return await res.json();
    } catch (err) {
      Toast.show(err.message, 'error');
      throw err;
    }
  },

  get(path) { return this.request(path); },
  post(path, data) {
    return this.request(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  },
  postForm(path, fd) { return this.request(path, { method: 'POST', body: fd }); },
  delete(path) { return this.request(path, { method: 'DELETE' }); },
};

// Modal System
const Modal = {
  open(id) {
    const el = document.getElementById(id);
    if (el) el.classList.add('active');
  },

  close(id) {
    const el = document.getElementById(id);
    if (el) el.classList.remove('active');
  },

  init(id) {
    const overlay = document.getElementById(id);
    if (!overlay) return;
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) overlay.classList.remove('active');
    });
  },
};

// Theme System
const Theme = {
  init() {
    const sel = document.getElementById('themeSelect');
    const saved = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', saved);
    sel.value = saved;
    sel.addEventListener('change', (e) => this.set(e.target.value));
  },

  set(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  },
};

// Panel Navigation
const Panels = {
  init(callbacks) {
    document.querySelectorAll('.ui-nav-item').forEach(item => {
      item.addEventListener('click', () => this.open(item.dataset.panel, callbacks));
    });

    document.getElementById('newChatBtn')?.addEventListener('click', () => this.open('chat', callbacks));
    document.getElementById('uploadBtn')?.addEventListener('click', () => this.open('upload', callbacks));

    // Welcome tabs
    document.querySelectorAll('.ui-welcome-tab').forEach(tab => {
      tab.addEventListener('click', () => this.switchTab(tab.dataset.tab));
    });

    // Welcome cards
    document.querySelectorAll('.ui-welcome-card').forEach(card => {
      card.addEventListener('click', () => {
        const action = card.dataset.action;
        if (action === 'overview') Chat.quickAsk('What is this document about?');
        else if (action === 'summarize') Chat.quickAsk('Summarize the key points');
        else if (action === 'upload') this.open('upload', callbacks);
        else if (action === 'compare') this.open('compare', callbacks);
      });
    });

    // Prompt suggestions
    document.querySelectorAll('.ui-prompt-btn').forEach(btn => {
      btn.addEventListener('click', () => Chat.quickAsk(btn.textContent));
    });
  },

  open(panel, callbacks) {
    document.querySelectorAll('.ui-panel').forEach(p => p.classList.remove('ui-panel--active'));
    document.querySelectorAll('.ui-nav-item').forEach(n => n.classList.remove('ui-nav-item--active'));

    const el = document.getElementById(`panel-${panel}`);
    if (el) el.classList.add('ui-panel--active');

    const nav = document.querySelector(`.ui-nav-item[data-panel="${panel}"]`);
    if (nav) nav.classList.add('ui-nav-item--active');

    if (callbacks[panel]) callbacks[panel]();
  },

  switchTab(tab) {
    document.querySelectorAll('.ui-welcome-tab').forEach(t => t.classList.remove('ui-welcome-tab--active'));
    document.querySelectorAll('.ui-welcome-content').forEach(c => c.classList.remove('ui-welcome-content--active'));

    document.querySelector(`.ui-welcome-tab[data-tab="${tab}"]`)?.classList.add('ui-welcome-tab--active');
    document.querySelector(`.ui-welcome-content[data-content="${tab}"]`)?.classList.add('ui-welcome-content--active');

    if (tab === 'docs') Docs.populateGallery();
  },
};

// Status & Statistics
const Status = {
  async check() {
    try {
      const data = await API.get('/status');
      const isOnline = data.ollama === 'connected';

      document.getElementById('statusDot').classList.toggle('online', isOnline);
      document.getElementById('statusText').textContent = isOnline ? 'Connected' : 'Offline';
      document.getElementById('statsVectors').textContent = (data.total_vectors || 0).toLocaleString();
      document.getElementById('statsDocs').textContent = (data.sources || []).length;
    } catch {
      document.getElementById('statusDot').classList.remove('online');
      document.getElementById('statusText').textContent = 'Offline';
    }
  },
};

// Document Management
const Docs = {
  data: [],

  async load() {
    try {
      this.data = await API.get('/documents');
      this.render();
    } catch {}
  },

  render() {
    const list = document.getElementById('fileList');
    const count = document.getElementById('fileCount');
    const empty = document.getElementById('emptyDocs');

    count.textContent = this.data.length;

    if (!this.data.length) {
      list.style.display = 'none';
      empty.style.display = 'flex';
      return;
    }

    list.style.display = 'flex';
    empty.style.display = 'none';
    list.innerHTML = this.data.slice(0, 10).map(doc => `
      <div class="ui-doc-item">
        <div class="ui-doc-item__icon">${Utils.getFileIcon(doc.suffix)}</div>
        <div class="ui-doc-item__info">
          <div class="ui-doc-item__name">${Utils.escapeHtml(doc.filename)}</div>
          <div class="ui-doc-item__size">${doc.size_mb} MB</div>
        </div>
        <button class="ui-doc-item__delete" data-file="${Utils.escapeHtml(doc.filename)}">×</button>
      </div>`).join('');

    document.querySelectorAll('.ui-doc-item__delete').forEach(btn => {
      btn.addEventListener('click', () => this.delete(btn.dataset.file));
    });
  },

  async delete(filename) {
    if (!confirm(`Delete "${filename}"?`)) return;
    try {
      await API.delete(`/document/${encodeURIComponent(filename)}`);
      Toast.show(`Deleted ${filename}`, 'success');
      this.load();
      Status.check();
    } catch {}
  },

  async populateGallery() {
    const gallery = document.getElementById('docsGallery');
    gallery.innerHTML = this.data.map(doc => `
      <div class="ui-doc-card">
        <div class="ui-doc-card-icon">${Utils.getFileIcon(doc.suffix)}</div>
        <div class="ui-doc-card-name">${Utils.escapeHtml(doc.filename)}</div>
      </div>`).join('');
  },

  getNames() {
    return this.data.map(d => d.filename);
  },
};

// Upload System
const Upload = {
  init() {
    const zone = document.getElementById('uploadZone');
    const input = document.getElementById('fileInput');
    const urlBtn = document.getElementById('ingestBtn');

    zone.addEventListener('click', () => input.click());
    zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', (e) => {
      e.preventDefault();
      zone.classList.remove('drag-over');
      this.uploadFiles(e.dataTransfer.files);
    });

    input.addEventListener('change', (e) => {
      this.uploadFiles(e.target.files);
      e.target.value = '';
    });

    urlBtn.addEventListener('click', () => this.ingestUrl());
  },

  async uploadFiles(files) {
    const progress = document.getElementById('uploadProgress');
    const fill = document.getElementById('progressFill');
    const text = document.getElementById('progressText');
    progress.style.display = 'block';

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      text.textContent = `Uploading ${file.name} (${i + 1}/${files.length})`;
      fill.style.width = `${(i / files.length) * 100}%`;

      const fd = new FormData();
      fd.append('file', file);

      try {
        const res = await API.postForm('/ingest', fd);
        Toast.show(`✓ ${res.file}: ${res.chunks} chunks`, 'success');
      } catch {}

      fill.style.width = `${((i + 1) / files.length) * 100}%`;
    }

    text.textContent = 'Done!';
    setTimeout(() => {
      progress.style.display = 'none';
      fill.style.width = '0%';
    }, 2000);

    Docs.load();
    Status.check();
  },

  async ingestUrl() {
    const input = document.getElementById('urlInput');
    const url = input.value.trim();
    if (!url) return;

    try {
      const res = await API.post('/ingest/url', { url });
      Toast.show(`✓ ${res.file}: ${res.chunks} chunks`, 'success');
      input.value = '';
      Docs.load();
      Status.check();
    } catch {}
  },
};

// Chat System
const Chat = {
  history: [],
  isQuerying: false,
  streaming: true,

  init() {
    const input = document.getElementById('chatInput');
    const btn = document.getElementById('sendBtn');

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.send();
      }
    });

    input.addEventListener('input', () => this.autoResize());
    btn.addEventListener('click', () => this.send());
  },

  autoResize() {
    const input = document.getElementById('chatInput');
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
  },

  quickAsk(q) {
    document.getElementById('chatInput').value = q;
    document.getElementById('chatWelcome').style.display = 'none';
    this.send();
  },

  async send() {
    const input = document.getElementById('chatInput');
    const q = input.value.trim();
    if (!q || this.isQuerying) return;

    input.value = '';
    this.autoResize();
    this.addMessage('user', q);
    this.isQuerying = true;
    document.getElementById('sendBtn').disabled = true;

    try {
      if (this.streaming) await this.stream(q);
      else await this.sync(q);
    } finally {
      this.isQuerying = false;
      document.getElementById('sendBtn').disabled = false;
    }
  },

  async sync(q) {
    try {
      const res = await API.post('/query', { question: q, history: this.history.slice(-10) });
      const el = this.addMessage('ai', Utils.escapeHtml(res.answer || ''), res.sources || []);
      this.addSuggestions(el);
    } catch {
      this.addMessage('ai', '❌ Failed to get answer. Check if Ollama is running.');
    }
  },

  async stream(q) {
    const container = document.getElementById('chatMessages');
    const msg = document.createElement('div');
    msg.className = 'ui-message';
    msg.innerHTML = `<div class="ui-message-avatar">🧠</div><div class="ui-message-body"><div class="ui-message-header"><span class="ui-message-sender">Document AI</span><span class="ui-message-time">${Utils.formatTime()}</span></div><div class="ui-message-content"><div class="ui-loading-dots"><span></span><span></span><span></span></div></div></div>`;
    container.appendChild(msg);
    container.scrollTop = container.scrollHeight;

    const content = msg.querySelector('.ui-message-content');
    let text = '';

    try {
      const res = await fetch('/query-stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, history: this.history.slice(-10) }),
      });

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data === '[DONE]') continue;
            text += data;
            content.textContent = text;
            container.scrollTop = container.scrollHeight;
          }
        }
      }

      if (!text) content.textContent = 'No response';
      this.history.push({ role: 'assistant', content: text });
      this.addSuggestions(msg);
    } catch {
      content.textContent = '❌ Stream failed';
    }
  },

  addMessage(role, content, sources = []) {
    const welcome = document.getElementById('chatWelcome');
    if (welcome) welcome.style.display = 'none';

    const container = document.getElementById('chatMessages');
    const msg = document.createElement('div');
    msg.className = 'ui-message';

    const avatar = role === 'user' ? '👤' : '🧠';
    const name = role === 'user' ? 'You' : 'Document AI';

    let sourcesHtml = '';
    if (sources.length) {
      const chips = sources.map(s => {
        return `<span class="ui-source-chip" data-source='${Utils.escapeHtml(JSON.stringify(s))}'>${Utils.escapeHtml(s.source)} p.${s.page} <strong>${((s.score || 0) * 100).toFixed(0)}%</strong></span>`;
      }).join('');
      sourcesHtml = `<div class="ui-sources"><div class="ui-sources-title">📎 ${sources.length} Source${sources.length !== 1 ? 's' : ''}</div>${chips}</div>`;
    }

    msg.innerHTML = `<div class="ui-message-avatar">${avatar}</div><div class="ui-message-body"><div class="ui-message-header"><span class="ui-message-sender">${name}</span><span class="ui-message-time">${Utils.formatTime()}</span></div><div class="ui-message-content">${role === 'user' ? Utils.escapeHtml(content) : content}</div>${sourcesHtml}</div>`;
    container.appendChild(msg);
    container.scrollTop = container.scrollHeight;

    this.history.push({ role, content: typeof content === 'string' ? content : '' });
    if (this.history.length > 20) this.history = this.history.slice(-20);

    return msg;
  },

  addSuggestions(el) {
    const suggestions = [
      'What are the key takeaways?',
      'Can you provide more details?',
      'Where is this mentioned in the source?',
      'Summarize the main points briefly.',
    ];

    const qs = suggestions.sort(() => Math.random() - 0.5).slice(0, 3);
    const container = document.createElement('div');
    container.className = 'ui-suggested-questions';

    qs.forEach(q => {
      const pill = document.createElement('span');
      pill.className = 'ui-suggested-pill';
      pill.textContent = q;
      pill.addEventListener('click', () => this.quickAsk(q));
      container.appendChild(pill);
    });

    el.querySelector('.ui-message-body')?.appendChild(container);
    document.getElementById('chatMessages').scrollTop = document.getElementById('chatMessages').scrollHeight;
  },

  setStreaming(on) {
    this.streaming = on;
    document.getElementById('streamOn').classList.toggle('ui-toggle--active', on);
    document.getElementById('streamOff').classList.toggle('ui-toggle--active', !on);
    Toast.show(`Streaming ${on ? 'enabled' : 'disabled'}`, 'info');
  },
};

// Other Modules (abbreviated for space)
const Compare = {
  init() {
    document.getElementById('compareBtn')?.addEventListener('click', () => this.compare());
  },

  populate() {
    const names = Docs.getNames();
    ['compareDocA', 'compareDocB'].forEach(id => {
      const sel = document.getElementById(id);
      const current = sel.value;
      sel.innerHTML = '<option value="">Select...</option>' + names.map(n => `<option value="${Utils.escapeHtml(n)}">${Utils.escapeHtml(n)}</option>`).join('');
      sel.value = current;
    });
  },

  async compare() {
    const a = document.getElementById('compareDocA').value;
    const b = document.getElementById('compareDocB').value;
    if (!a || !b) {
      Toast.show('Select both documents', 'error');
      return;
    }

    const result = document.getElementById('compareResult');
    result.classList.add('active');
    result.innerHTML = '<div class="ui-loading-dots"><span></span><span></span><span></span></div>';

    try {
      const data = await API.post('/compare', { doc_a: a, doc_b: b, question: document.getElementById('compareQuestion').value });
      result.innerHTML = Utils.escapeHtml(data.comparison || JSON.stringify(data, null, 2));
    } catch {
      result.innerHTML = 'Failed';
    }
  },
};

const Extract = {
  init() {
    document.getElementById('extractBtn')?.addEventListener('click', () => this.extract());
  },

  async extract() {
    const fields = document.getElementById('extractFields').value.trim();
    if (!fields) {
      Toast.show('Enter field names', 'error');
      return;
    }

    const result = document.getElementById('extractResult');
    result.innerHTML = '<div class="ui-loading-dots"><span></span><span></span><span></span></div>';

    try {
      const data = await API.post('/extract', { fields: fields.split('\n').map(f => f.trim()).filter(Boolean) });
      result.innerHTML = `<pre>${Utils.escapeHtml(JSON.stringify(data, null, 2))}</pre>`;
    } catch {}
  },
};

const Summarize = {
  init() {
    document.getElementById('summarizeBtn')?.addEventListener('click', () => this.summarize());
  },

  async summarize() {
    const topic = document.getElementById('summaryTopic').value.trim() || 'the document';
    const result = document.getElementById('summaryResult');
    result.classList.add('active');
    result.innerHTML = '<div class="ui-loading-dots"><span></span><span></span><span></span></div>';

    try {
      const data = await API.post('/summarize', { topic });
      result.textContent = data.summary || 'No summary';
    } catch {
      result.textContent = 'Failed';
    }
  },
};

const Analytics = {
  async load() {
    try {
      const data = await API.get('/analytics');
      this.renderStats(data);
      this.renderBreakdown(data.source_breakdown || []);
    } catch {}
  },

  renderStats(data) {
    const grid = document.getElementById('analyticsStats');
    grid.innerHTML = `
      <div class="ui-stat-card">
        <div class="ui-stat-card-label">Total Vectors</div>
        <div class="ui-stat-card-value">${(data.total_vectors || 0).toLocaleString()}</div>
      </div>
      <div class="ui-stat-card">
        <div class="ui-stat-card-label">Documents</div>
        <div class="ui-stat-card-value">${(data.sources || []).length}</div>
      </div>
      <div class="ui-stat-card">
        <div class="ui-stat-card-label">Index Size</div>
        <div class="ui-stat-card-value">${data.storage?.index_size_mb || 0} MB</div>
      </div>
      <div class="ui-stat-card">
        <div class="ui-stat-card-label">Cache Hits</div>
        <div class="ui-stat-card-value">${data.cache?.hits || 0}</div>
      </div>`;
  },

  renderBreakdown(sources) {
    const breakdown = document.getElementById('sourceBreakdown');
    if (!sources.length) {
      breakdown.innerHTML = '<p style="text-align:center;color:var(--text-muted);">No sources</p>';
      return;
    }
    breakdown.innerHTML = sources.map(s => `<div class="ui-breakdown-item"><span>${Utils.escapeHtml(s.source)}</span><span>${s.chunks} chunks</span></div>`).join('');
  },
};

const RAGAS = {
  init() {
    document.getElementById('refreshRagasBtn')?.addEventListener('click', () => this.load());
    document.getElementById('clearRagasBtn')?.addEventListener('click', () => this.clear());
  },

  async load() {
    try {
      const data = await API.get('/evaluate/dashboard');
      this.renderStats(data);
      this.renderHistory(data);
    } catch {}
  },

  renderStats(data) {
    const stats = document.getElementById('ragasStats');
    stats.innerHTML = `
      <div class="ui-stat-card">
        <div class="ui-stat-card-label">Total</div>
        <div class="ui-stat-card-value">${data.total_evaluations || 0}</div>
      </div>
      <div class="ui-stat-card">
        <div class="ui-stat-card-label">Average</div>
        <div class="ui-stat-card-value">${((data.avg_overall || 0) * 100).toFixed(1)}%</div>
      </div>
      <div class="ui-stat-card">
        <div class="ui-stat-card-label">Best</div>
        <div class="ui-stat-card-value">${((data.best_score || 0) * 100).toFixed(1)}%</div>
      </div>
      <div class="ui-stat-card">
        <div class="ui-stat-card-label">Worst</div>
        <div class="ui-stat-card-value">${((data.worst_score || 0) * 100).toFixed(1)}%</div>
      </div>`;
  },

  async renderHistory(data) {
    try {
      const history = await API.get('/evaluate/history?limit=10');
      const el = document.getElementById('ragasHistory');
      if (!history.length) {
        el.innerHTML = '<p style="text-align:center;color:var(--text-muted);padding:16px;">No evaluations</p>';
        return;
      }
      el.innerHTML = history.map(h => `<div class="ui-history-item"><span>${Utils.escapeHtml(h.question)}</span><span>${((h.overall_score || 0) * 100).toFixed(0)}%</span></div>`).join('');
    } catch {}
  },

  async clear() {
    if (!confirm('Clear all?')) return;
    try {
      await API.post('/evaluate/clear', {});
      Toast.show('Cleared', 'success');
      this.load();
    } catch {}
  },
};

const Settings = {
  init() {
    document.getElementById('streamOn')?.addEventListener('click', () => Chat.setStreaming(true));
    document.getElementById('streamOff')?.addEventListener('click', () => Chat.setStreaming(false));
    document.getElementById('cacheBtn')?.addEventListener('click', () => this.clearCache());
    document.getElementById('clearIndexBtn')?.addEventListener('click', () => this.clearIndex());
  },

  async clearCache() {
    try {
      await API.post('/cache/clear', {});
      Toast.show('Cache cleared', 'success');
    } catch {}
  },

  async clearIndex() {
    if (!confirm('Delete ALL documents?')) return;
    try {
      await API.post('/clear', {});
      Toast.show('Index cleared', 'success');
      location.reload();
    } catch {}
  },
};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  Theme.init();
  Chat.init();
  Upload.init();
  Compare.init();
  Extract.init();
  Summarize.init();
  Analytics.init();
  RAGAS.init();
  Settings.init();

  const callbacks = {
    chat: () => {},
    upload: () => {},
    explorer: () => Docs.populateGallery?.(),
    analytics: () => Analytics.load(),
    ragas: () => RAGAS.load(),
    compare: () => Compare.populate(),
    extract: () => {},
    summarize: () => {},
  };

  Panels.init(callbacks);

  // Settings button
  document.getElementById('settingsBtn')?.addEventListener('click', () => Modal.open('settingsModal'));

  // Modal close buttons
  document.querySelectorAll('.ui-modal-close').forEach(btn => {
    btn.addEventListener('click', () => {
      const modal = btn.closest('.ui-modal');
      if (modal) modal.parentElement.classList.remove('active');
    });
  });

  Modal.init('settingsModal');
  Modal.init('sourceModal');

  // Source modal
  document.addEventListener('click', (e) => {
    if (e.target.classList.contains('ui-source-chip')) {
      const source = JSON.parse(e.target.dataset.source);
      document.getElementById('sourceModalTitle').textContent = `${source.source} — Page ${source.page}`;
      document.getElementById('sourceModalBody').textContent = source.excerpt || 'No excerpt';
      Modal.open('sourceModal');
    }
  });

  // Initial load
  Status.check();
  Docs.load();

  // Auto refresh
  setInterval(() => Status.check(), 30000);
  setInterval(() => Docs.load(), 60000);
});
