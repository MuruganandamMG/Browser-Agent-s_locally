class AgentMonitor {
  constructor({api, render = () => {}, element, schedule = globalThis.setTimeout.bind(globalThis), unschedule = globalThis.clearTimeout.bind(globalThis)}) {
    this.api = api;
    this.schedule = schedule;
    this.unschedule = unschedule;
    this.sessionId = null;
    this.task = null;
    this.error = '';
    this.connection = null;
    this.loading = this.pending = false;
    this.generation = 0;
    this.render = element ? createAgentMonitorView(element, this, render) : render;
  }
  get active() { return !!this.task && !['completed', 'failed', 'cancelled', 'blocked', 'paused'].includes(this.task.state); }
  get uncertain() { return (this.task?.steps || []).some(step => step.state === 'uncertain' || step.result?.status === 'uncertain'); }
  get unavailable() { return this.loading || this.pending || this.active || this.task?.state === 'paused' || !!this.error; }
  emit() { this.render({task: this.task, error: this.error, connection: this.connection, desktopConnection: this.desktopConnection, loading: this.loading, pending: this.pending}); }
  clearTimer() { this.unschedule(this.timer); this.timer = null; }
  queuePoll() {
    this.clearTimer();
    if (this.sessionId && (this.active || this.error)) this.timer = this.schedule(() => this.poll(), 1000);
  }
  async openSession(sessionId) {
    const generation = ++this.generation;
    this.clearTimer();
    this.sessionId = sessionId;
    this.task = null;
    this.error = '';
    this.connection = null;
    this.desktopConnection = null;
    this.loading = true;
    this.pending = false;
    this.emit();
    const results = await Promise.allSettled([
      this.api(`/api/agent/tasks?session_id=${encodeURIComponent(sessionId)}`), this.api('/api/agent/neo/status'), this.api('/api/agent/desktop/status'),
    ]);
    if (generation !== this.generation) return;
    const [tasks, connection, desktop] = results;
    if (tasks.status === 'fulfilled') {
      const ordered = [...tasks.value.tasks].sort((a, b) => String(b.created || b.updated || '').localeCompare(String(a.created || a.updated || '')));
      this.task = ordered.find(task => !['completed', 'failed', 'cancelled', 'blocked', 'paused'].includes(task.state)) || ordered[0] || null;
    } else this.error = tasks.reason.message;
    if (connection.status === 'fulfilled') this.connection = connection.value;
    else this.connection = {available: false, error: connection.reason.message};
    this.desktopConnection = desktop.status === 'fulfilled' ? desktop.value : {connected: false, error: desktop.reason.message};
    this.loading = false;
    this.emit();
    this.queuePoll();
  }
  async start(request, mode = 'browser') {
    if (!this.sessionId || this.unavailable || !request.trim()) return null;
    const generation = ++this.generation;
    this.pending = true;
    this.error = '';
    this.emit();
    try {
      const task = await this.api('/api/agent/tasks', {session_id: this.sessionId, request, ...(mode === 'computer' ? {mode} : {})});
      if (generation !== this.generation) return null;
      this.task = task;
      return task;
    } catch (error) {
      if (generation === this.generation) {
        this.error = `${error.message} Reconnecting to check whether the task was saved.`;
        this.task = null;
      }
      return null;
    } finally {
      if (generation === this.generation) { this.pending = false; this.emit(); this.queuePoll(); }
    }
  }
  async poll() {
    this.clearTimer();
    if (this.polling === this.generation || this.pending) { this.queuePoll(); return; }
    if (!this.task) { await this.openSession(this.sessionId); return; }
    const generation = this.generation;
    this.polling = generation;
    try {
      const task = await this.api(`/api/agent/tasks/${encodeURIComponent(this.task.id)}`);
      if (generation !== this.generation) return;
      this.task = task;
      this.error = '';
    } catch (error) { if (generation === this.generation) this.error = error.message; }
    finally {
      if (this.polling === generation) this.polling = null;
      if (generation === this.generation) { this.emit(); this.queuePoll(); }
    }
  }
  async control(operation, data = {}) {
    if (!this.task || this.pending) return null;
    if (operation === 'approve' && data.fingerprint !== this.task.approval?.fingerprint) return null;
    const generation = ++this.generation;
    this.pending = true;
    this.error = '';
    this.clearTimer();
    this.emit();
    try {
      const task = await this.api(`/api/agent/tasks/${encodeURIComponent(this.task.id)}/${operation}`, data);
      if (generation !== this.generation) return null;
      this.task = task;
      return task;
    } catch (error) { if (generation === this.generation) this.error = error.message; return null; }
    finally { if (generation === this.generation) { this.pending = false; this.emit(); this.queuePoll(); } }
  }
  stopWatching() { ++this.generation; this.clearTimer(); }
}

function createAgentMonitorView(root, monitor, onChange) {
  root.innerHTML = `<div class="agent-heading"><h2>Browser agent</h2><span class="agent-state" role="status"></span></div>
    <p class="agent-connection"></p><p class="agent-request"></p><p class="agent-current"></p>
    <p class="agent-error" role="status" hidden></p><button class="agent-reconnect" type="button" hidden>Reconnect</button>
    <details class="agent-history" hidden><summary>Step history</summary><ol></ol></details>
    <section class="agent-approval" aria-label="Pending operation" hidden><h3>Review operation</h3>
      <p class="agent-approval-reason"></p><pre class="agent-approval-detail"></pre>
      <p class="agent-expiry" role="status"></p><div class="agent-buttons">
      <button class="agent-approve" type="button">Approve once</button><button class="agent-reject" type="button">Reject</button></div></section>
    <div class="agent-controls"><button class="agent-stop" type="button" hidden>Stop task</button>
      <button class="agent-resume" type="button" hidden>Resume task</button><small class="agent-stop-note" hidden>Stop takes effect after the current operation finishes.</small></div>
    <div class="agent-result message-content" hidden></div>`;
  const node = selector => root.querySelector(selector);
  let historyKey, resultKey, displayedApproval;
  node('.agent-stop').onclick = () => monitor.control('cancel');
  node('.agent-resume').onclick = () => monitor.control('resume');
  node('.agent-reconnect').onclick = () => monitor.openSession(monitor.sessionId);
  node('.agent-approve').onclick = () => {
    if (displayedApproval && displayedApproval.expires > Date.now() / 1000) monitor.control('approve', {fingerprint: displayedApproval.fingerprint});
  };
  node('.agent-reject').onclick = () => monitor.control('reject');
  return view => {
    const {task, error, connection, desktopConnection, pending, loading} = view;
    node('.agent-heading h2').textContent = task?.mode === 'computer' ? 'Computer agent' : 'Browser agent';
    const finished = ['completed', 'failed', 'blocked', 'cancelled'].includes(task?.state);
    root.hidden = (!task && !error && !loading) || (!!task?.autonomous && finished && !error);
    const state = loading ? 'Restoring tasks…' : pending ? 'Saving…' : (task?.state || 'Ready').replaceAll('_', ' ');
    if (node('.agent-state').textContent !== state) node('.agent-state').textContent = state;
    node('.agent-connection').textContent = connection ? ((connection.available ?? connection.connected) ? 'BrowserOS neo connected' : `BrowserOS neo unavailable${connection.error ? `: ${connection.error}` : '. Start neo, then reconnect.'}`) : '';
    if (task?.mode === 'computer') {
      node('.agent-connection').textContent += desktopConnection?.connected ? ' · Agent Desktop connected' : ` · Agent Desktop unavailable${desktopConnection?.error ? `: ${desktopConnection.error}` : ''}`;
      if (task.desktop?.session_id) node('.agent-connection').textContent += task.desktop.cursor ? ' · Agent cursor available' : ' · Agent cursor unavailable';
    }
    node('.agent-request').textContent = task?.request || '';
    node('.agent-request').hidden = !!task?.autonomous;
    const steps = task?.steps || [];
    const latest = steps.at(-1);
    const tabs = Object.values(task?.tabs || {});
    const site = latest?.result?.app || latest?.action?.app || latest?.result?.workspace || latest?.result?.url || latest?.action?.url || tabs.at(-1)?.url || '';
    const action = latest?.action?.type || latest?.action?.action || '';
    node('.agent-current').textContent = [site, action ? `Current action: ${action}` : ''].filter(Boolean).join(' · ');
    node('.agent-error').hidden = !error && !task?.error;
    const errorText = [error, task?.error].filter(Boolean).join(' ');
    if (node('.agent-error').textContent !== errorText) node('.agent-error').textContent = errorText;
    node('.agent-reconnect').hidden = !error && (!connection || !!(connection.available ?? connection.connected)) && (task?.mode !== 'computer' || !!desktopConnection?.connected);
    displayedApproval = task?.state === 'awaiting_approval' ? task.approval : null;
    node('.agent-approval').hidden = !displayedApproval;
    node('.agent-approval-reason').textContent = displayedApproval?.reason || '';
    node('.agent-approval-detail').textContent = displayedApproval ? JSON.stringify({action: displayedApproval.action, target: displayedApproval.target}, null, 2) : '';
    const expired = !!displayedApproval && displayedApproval.expires <= Date.now() / 1000;
    node('.agent-expiry').textContent = displayedApproval ? (expired ? 'Approval expired. Resume to inspect and propose a new operation.' : 'Approval applies once to this operation and expires after five minutes.') : '';
    node('.agent-approve').disabled = pending || !!error || expired;
    node('.agent-reject').disabled = pending;
    const history = JSON.stringify([steps, task?.events]);
    if (history !== historyKey) {
      historyKey = history;
      const list = node('.agent-history ol');
      list.replaceChildren();
      for (const [index, step] of steps.entries()) {
        const item = document.createElement('li');
        const heading = document.createElement('strong');
        heading.textContent = `${step.action?.type || step.action?.action || `Step ${index + 1}`} · ${step.state || step.result?.status || 'pending'}`;
        const detail = document.createElement('pre');
        detail.textContent = JSON.stringify({action: step.action, result: step.result}, null, 2);
        item.append(heading, detail); list.append(item);
      }
      for (const event of (task?.events || []).slice(-12)) {
        const item = document.createElement('li');
        item.textContent = event.message || event.type; list.append(item);
      }
      node('.agent-history').hidden = !list.children.length;
    }
    node('.agent-stop').hidden = !task || ['completed', 'failed', 'cancelled', 'blocked'].includes(task.state);
    node('.agent-stop').disabled = pending;
    node('.agent-stop-note').hidden = node('.agent-stop').hidden;
    node('.agent-resume').hidden = task?.state !== 'paused' && !(task?.state === 'awaiting_approval' && expired);
    node('.agent-resume').disabled = pending || !!error;
    node('.agent-result').hidden = !task?.result || !!task?.autonomous;
    if (task?.result !== resultKey) {
      resultKey = task?.result;
      const result = node('.agent-result');
      if (task?.result && !task.autonomous && typeof window !== 'undefined' && window.marked && window.DOMPurify) {
        result.innerHTML = window.DOMPurify.sanitize(window.marked.parse(task.result, {breaks: true}), {
          USE_PROFILES: {html: true}, FORBID_TAGS: ['form', 'input', 'button', 'textarea', 'select', 'style', 'iframe'],
        });
        result.querySelectorAll('a').forEach(link => { link.target = '_blank'; link.rel = 'noopener noreferrer'; });
      } else result.textContent = task?.result || '';
    }
    onChange(view);
  };
}

if (typeof window !== 'undefined') window.AgentMonitor = AgentMonitor;
if (typeof module !== 'undefined' && module.exports) module.exports = {AgentMonitor, createAgentMonitorView};
