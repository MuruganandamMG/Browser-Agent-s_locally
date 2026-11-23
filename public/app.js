const form = document.querySelector('#composer');
const prompt = document.querySelector('#prompt');
const log = document.querySelector('#conversation');
const status = document.querySelector('#status');
const send = document.querySelector('#send');
const reset = document.querySelector('#reset');
const empty = document.querySelector('#empty');
const thinkingButton = document.querySelector('#thinking');
let thinking = false;
let messages = [];
let currentSession = null;
let draftTimer;
let pollTimer;
let ready = false;
let busy = false;
let loadingModel = false;
let sessionIndex = [];
let sessionGeneration = 0;
let browserMode = false;
let computerMode = false;
const modelSelect = document.querySelector('#model-select');
const loadModel = document.querySelector('#load-model');
const modelStatus = document.querySelector('#model-status');
const dictateButton = document.querySelector('#dictate');
const voiceButton = document.querySelector('#voice-chat');
const voiceLanguage = document.querySelector('#voice-language');
const voiceDialog = document.querySelector('#voice-dialog');
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
voiceLanguage.value = navigator.language || 'en-IN';
const voice = new VoiceChat({
  Recognition, speech: window.speechSynthesis, Utterance: window.SpeechSynthesisUtterance,
  lang: voiceLanguage.value,
  onState(message) {
    document.querySelector('#voice-status').textContent = message;
    dictateButton.setAttribute('aria-pressed', String(voice.active && !voice.conversation));
    voiceButton.setAttribute('aria-pressed', String(voice.active && voice.conversation));
    dictateButton.textContent = voice.active && !voice.conversation ? 'Stop dictation' : 'STT · Dictate';
    voiceButton.textContent = voice.active && voice.conversation ? 'End voice chat' : 'TTS + STT · Voice chat';
    voiceLanguage.disabled = voice.active;
    const inConversation = voice.active && voice.conversation;
    if (inConversation && !voiceDialog.open) voiceDialog.showModal();
    document.querySelector('#voice-phase').textContent = message.startsWith('Heard:') ? 'Listening…' : message;
    if (message.startsWith('Heard:')) document.querySelector('#voice-caption').textContent = message.slice(7);
    document.querySelector('#voice-orb').dataset.phase = message.startsWith('Speaking') ? 'speaking' : message.startsWith('Thinking') ? 'thinking' : voice.muted ? 'muted' : 'listening';
    document.querySelector('#voice-mute').setAttribute('aria-pressed', String(!!voice.muted));
    document.querySelector('#voice-mute').textContent = voice.muted ? 'Unmute microphone' : 'Mute microphone';
    document.querySelector('#voice-interrupt').hidden = !voice.utterance;
    if (!inConversation && voiceDialog.open) { voiceDialog.close(); voiceButton.focus(); }
  },
  onTranscript(text, conversation) {
    if (conversation) { sendMessage(text); return; }
    prompt.value = [prompt.value.trim(), text].filter(Boolean).join(' ');
    prompt.dispatchEvent(new Event('input'));
  },
});
function toggleVoice(conversation) {
  if (voice.active) { voice.stop(); return; }
  if (busy || !ready) return;
  const language = voiceLanguage.value.trim();
  try { Intl.getCanonicalLocales(language); if (!language) throw new Error(); }
  catch { document.querySelector('#voice-status').textContent = 'Enter a language tag such as en-IN, en-US or ta-IN.'; return; }
  voice.lang = language;
  if (conversation) {
    document.querySelector('#voice-caption').textContent = 'Go ahead, I’m listening.';
    document.querySelector('#voice-response').textContent = '';
  }
  voice.start(conversation);
}
dictateButton.addEventListener('click', () => toggleVoice(false));
voiceButton.addEventListener('click', () => toggleVoice(true));
document.querySelector('#voice-mute').addEventListener('click', () => voice.toggleMute());
document.querySelector('#voice-interrupt').addEventListener('click', () => voice.interrupt());
for (const id of ['voice-end', 'voice-close']) document.querySelector(`#${id}`).addEventListener('click', () => voice.stop());
voiceDialog.addEventListener('cancel', event => { event.preventDefault(); voice.stop(); });
if (!Recognition) {
  dictateButton.disabled = voiceButton.disabled = true;
  document.querySelector('#voice-status').textContent = 'Speech recognition unavailable. Use a browser with speech recognition support.';
} else if (!window.speechSynthesis || !window.SpeechSynthesisUtterance) {
  voiceButton.disabled = true;
  document.querySelector('#voice-status').textContent = 'TTS unavailable; dictation is available.';
}
window.addEventListener('pagehide', () => voice.stop());
document.addEventListener('visibilitychange', () => { if (document.hidden) voice.stop(); });

async function refreshModels() {
  const data = await api('/api/models');
  const selected = modelSelect.value;
  modelSelect.replaceChildren();
  for (const model of data.models) {
    const option = document.createElement('option');
    option.value = model.id;
    option.textContent = `${model.name} - ${model.context.toLocaleString()} token context` + (model.active ? ' (loaded)' : !model.installed ? ' (not downloaded)' : '');
    option.disabled = !model.installed;
    option.selected = model.active;
    modelSelect.append(option);
  }
  if (data.models.some(model => model.id === selected && model.installed)) modelSelect.value = selected;
  const active = data.models.find(model => model.active);
  document.querySelector('#model-context').textContent = active
    ? `Using ${active.name} | Context window: ${active.context.toLocaleString()} tokens`
    : 'No model loaded. Choose a model to start chatting.';
  loadModel.disabled = modelSelect.disabled = busy || loadingModel;
}

loadModel.addEventListener('click', async () => {
  if (busy || loadingModel) return;
  voice.stop();
  loadingModel = true;
  document.querySelector('#model-context').textContent = 'Loading selected model...';
  setBusy(true);
  modelStatus.textContent = 'Loading model… This may take a few minutes.';
  loadModel.textContent = 'Loading…';
  try {
    await api('/api/models/load', {model: modelSelect.value});
    modelStatus.textContent = 'Model loaded. Ready to chat.';
  } catch (error) {
    modelStatus.textContent = error.message;
  } finally {
    loadingModel = false;
    setBusy(false);
    loadModel.textContent = 'Load model';
    await checkConnection();
    await refreshModels().catch(showError);
  }
});

modelSelect.addEventListener('change', () => {
  modelStatus.textContent = modelSelect.value === 'qwen30b'
    ? '12.6 GB · Uses system RAM and GPU. Loading and replies may be slower.'
    : 'Select Load model to switch. Your conversations stay saved.';
});

async function checkConnection() {
  const indicator = document.querySelector('#connection');
  try {
    const response = await fetch('/api/status');
    const data = await response.json();
    indicator.textContent = response.ok && data.available ? '\u25cf Connected to local model' : '\u25cb Start the local model runtime';
    document.querySelector('#model-name').textContent = data.model || 'Local model';
    thinkingButton.hidden = data.tools === false;
  } catch { indicator.textContent = '○ Local server unavailable'; }
}

function addMessage(role, content, metrics, toolCalls = [], model = 'Assistant') {
  empty.hidden = true;
  const article = document.createElement('article');
  article.className = `message ${role}`;
  const label = document.createElement('strong');
  label.textContent = role === 'user' ? 'YOU' : model;
  const text = document.createElement('div');
  text.className = 'message-content';
  if (role === 'assistant' && window.marked && window.DOMPurify) {
    text.innerHTML = DOMPurify.sanitize(marked.parse(content, {breaks: true}), {
      USE_PROFILES: {html: true}, FORBID_TAGS: ['form', 'input', 'button', 'textarea', 'select', 'style', 'iframe'],
    });
    text.querySelectorAll('a').forEach(link => { link.target = '_blank'; link.rel = 'noopener noreferrer'; });
    text.querySelectorAll('pre').forEach(block => {
      const copy = document.createElement('button');
      copy.className = 'code-copy';
      copy.type = 'button';
      copy.textContent = 'Copy code';
      copy.addEventListener('click', () => copyText(block.textContent, copy, 'Copy code'));
      block.after(copy);
    });
  } else text.textContent = content;
  article.append(label, text);
  if (toolCalls.length) {
    const details = document.createElement('details');
    details.className = 'message-tools';
    const summary = document.createElement('summary');
    summary.textContent = `Tools used: ${toolCalls.map(call => call.name).join(', ')}`;
    details.append(summary);
    for (const call of toolCalls) {
      const record = document.createElement('pre');
      record.textContent = `${call.name}(${call.arguments})\n${JSON.stringify(call.output, null, 2)}`;
      details.append(record);
      const files = [...(call.output.downloads || [])];
      if (call.output.screenshot_url) files.push({ name: 'View screenshot', url: call.output.screenshot_url });
      for (const file of files) {
        if (typeof file.url !== 'string' || !/^\/browser-files\/[a-zA-Z0-9_.-]+$/.test(file.url)) continue;
        const link = document.createElement('a');
        link.href = file.url;
        link.textContent = file.name;
        link.target = '_blank';
        link.rel = 'noopener';
        details.append(link, document.createElement('br'));
      }
    }
    article.append(details);
  }
  if (metrics) {
    const stats = document.createElement('small');
    stats.className = 'metrics';
    stats.title = 'Average speed = output tokens / request time, including prompt processing and tools. Tokens are summed across model calls, including thinking. Metrics appear after the reply finishes.';
    const values = [
      ['average_tokens_per_second', 'avg tok/s'],
      ['response_seconds', 's elapsed'],
      ['input_tokens', 'input tokens'],
      ['output_tokens', 'output tokens'],
      ['reasoning_tokens', 'thinking tokens'],
      ['total_tokens', 'total tokens'],
    ];
    stats.textContent = values.filter(([key]) => Number.isFinite(metrics[key]))
      .map(([key, unit]) => `${metrics[key].toLocaleString(undefined, { maximumFractionDigits: 2 })} ${unit}`).join(' · ');
    article.append(stats);
  }
  if (role === 'assistant') {
    const copy = document.createElement('button');
    copy.className = 'copy-answer';
    copy.type = 'button';
    copy.textContent = 'Copy response';
    copy.addEventListener('click', () => copyText(content, copy, 'Copy response'));
    article.append(copy);
  }
  log.insertBefore(article, document.querySelector('#agent-monitor'));
  log.scrollTop = log.scrollHeight;
  return article;
}

async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Unable to save changes.');
  return result;
}

const browserModeButton = document.querySelector('#browser-mode');
const computerModeButton = document.querySelector('#computer-mode');
let taskChatKey = '';
const browserAgent = new AgentMonitor({api, element: document.querySelector('#agent-monitor'), render({task}) {
  if (task?.autonomous && task.session_id === currentSession) {
    const key = task.id + (['completed', 'failed', 'blocked', 'cancelled'].includes(task.state) ? ':final' : ':request');
    if (key !== taskChatKey) {
      taskChatKey = key;
      Promise.resolve().then(() => openSession(task.session_id, true)).catch(showError);
    }
  }
  empty.hidden = messages.length > 0 || !document.querySelector('#agent-monitor').hidden;
  updateAgentControls();
}});
function updateAgentControls() {
  browserModeButton.disabled = busy || !ready || browserAgent.pending;
  computerModeButton.disabled = browserModeButton.disabled;
  send.disabled = busy || !ready || ((browserMode || computerMode) && browserAgent.unavailable);
}
browserModeButton.addEventListener('click', () => {
  browserMode = !browserMode;
  computerMode = false;
  computerModeButton.setAttribute('aria-pressed', 'false');
  computerModeButton.textContent = 'Computer: Off';
  browserModeButton.setAttribute('aria-pressed', String(browserMode));
  browserModeButton.textContent = browserMode ? 'Browser: On' : 'Browser: Off';
  prompt.placeholder = browserMode ? 'Describe a browser task' : 'Ask anything';
  updateAgentControls();
  prompt.focus();
});
computerModeButton.addEventListener('click', () => {
  computerMode = !computerMode;
  browserMode = false;
  browserModeButton.setAttribute('aria-pressed', 'false');
  browserModeButton.textContent = 'Browser: Off';
  computerModeButton.setAttribute('aria-pressed', String(computerMode));
  computerModeButton.textContent = computerMode ? 'Computer: On' : 'Computer: Off';
  prompt.placeholder = computerMode ? 'Describe a desktop, browser or coding task' : 'Ask anything';
  updateAgentControls();
  prompt.focus();
});
window.addEventListener('pagehide', () => browserAgent.stopWatching());
window.addEventListener('pageshow', event => {
  if (event.persisted && currentSession) browserAgent.openSession(currentSession);
});

function setBusy(value) {
  busy = value || loadingModel;
  value = busy;
  loadModel.disabled = modelSelect.disabled = value;
  send.disabled = reset.disabled = prompt.disabled = thinkingButton.disabled = value || !ready;
  document.querySelector('#new-session').disabled = value || !ready;
  document.querySelector('#delete-session').disabled = value || !currentSession;
  document.querySelectorAll('#sessions button').forEach(button => button.disabled = value);
  dictateButton.disabled = !Recognition || (!voice.active && (value || !ready));
  voiceButton.disabled = !Recognition || !window.speechSynthesis || !window.SpeechSynthesisUtterance || (!voice.active && (value || !ready));
  updateAgentControls();
}

async function refreshSessions() {
  const data = await api('/api/sessions');
  sessionIndex = data.sessions;
  renderSessions();
}

function renderSessions() {
  const list = document.querySelector('#sessions');
  list.replaceChildren();
  const query = document.querySelector('#search-chats').value.trim().toLocaleLowerCase();
  const matching = sessionIndex.filter(session => session.title.toLocaleLowerCase().includes(query));
  document.querySelector('#no-results').hidden = matching.length > 0 || !query;
  for (const session of matching) {
    const button = document.createElement('button');
    button.className = 'session';
    button.setAttribute('aria-current', session.id === currentSession ? 'true' : 'false');
    const title = document.createElement('span');
    title.textContent = session.title;
    const date = document.createElement('small');
    date.textContent = new Date(session.updated).toLocaleDateString(undefined, {month: 'short', day: 'numeric'});
    button.append(title, date);
    button.disabled = busy;
    button.addEventListener('click', () => openSession(session.id).catch(showError));
    list.append(button);
  }
}

function showError(error) { status.textContent = error.message; }

async function saveDraft() {
  clearTimeout(draftTimer);
  if (!currentSession) return;
  localStorage.setItem(`draft:${currentSession}`, prompt.value);
  await api('/api/draft', {session_id: currentSession, draft: prompt.value});
}

async function openSession(id, polling = false) {
  if (polling && currentSession !== id) return;
  const generation = ++sessionGeneration;
  if (!polling) voice.stop();
  if (!polling) await saveDraft();
  if (generation !== sessionGeneration) return;
  clearTimeout(pollTimer);
  const session = await api(`/api/session?id=${encodeURIComponent(id)}`);
  if (generation !== sessionGeneration) return;
  currentSession = id;
  if (browserAgent.sessionId !== id) browserAgent.openSession(id);
  localStorage.setItem('last-session', id);
  document.querySelector('#chat-title').textContent = session.title;
  log.querySelectorAll('.message').forEach(message => message.remove());
  messages = session.messages;
  empty.hidden = messages.length > 0 || !!browserAgent.task;
  for (const message of messages) {
    const article = addMessage(message.role, message.content, message.result?.metrics, message.result?.tool_calls, message.result?.model);
    if (message.state === 'failed') {
      const note = document.createElement('small');
      note.className = 'failed';
      note.textContent = message.error;
      const retry = document.createElement('button');
      retry.textContent = 'Retry reply';
      retry.type = 'button';
      retry.addEventListener('click', () => sendMessage(message.content, message.request_id));
      article.append(note, retry);
    }
    if (message.state === 'pending') {
      const note = document.createElement('small');
      note.className = 'metrics';
      note.textContent = 'Reply in progress. Your message is saved.';
      article.append(note);
    }
  }
  prompt.value = localStorage.getItem(`draft:${id}`) ?? session.draft;
  resizePrompt();
  ready = true;
  const pending = messages.some(message => message.state === 'pending');
  setBusy(pending);
  status.textContent = pending ? 'Reply in progress. You can refresh safely.' : 'All messages saved';
  if (pending) pollTimer = setTimeout(() => openSession(id, true).catch(showError), 2000);
  if (!polling) await refreshSessions();
  document.body.classList.remove('sidebar-open');
  document.querySelector('#open-sidebar').setAttribute('aria-expanded', 'false');
}

async function newSession() {
  await saveDraft();
  const session = await api('/api/sessions', {});
  await openSession(session.id);
  prompt.focus();
}

document.querySelector('#delete-session').addEventListener('click', async () => {
  if (busy || !currentSession || !confirm('Delete this chat and its automatic backup? This cannot be undone.')) return;
  const id = currentSession;
  setBusy(true);
  clearTimeout(draftTimer);
  clearTimeout(pollTimer);
  try {
    await api('/api/sessions/delete', {session_id: id});
    localStorage.removeItem(`draft:${id}`);
    localStorage.removeItem('last-session');
    currentSession = null;
    await refreshSessions();
    if (sessionIndex.length) await openSession(sessionIndex[0].id);
    else await newSession();
    status.textContent = 'Chat deleted';
  } catch (error) { showError(error); }
  finally { setBusy(false); }
});

async function sendMessage(content, requestId = crypto.randomUUID()) {
  if (busy || !ready || !content.trim()) return;
  if (voice.recognition) voice.stop();
  setBusy(true);
  try {
    await saveDraft();
    status.textContent = 'Saving message and preparing reply…';
    const voiceMode = voice.active && voice.conversation;
    const task = api('/api/chat', {session_id: currentSession, request_id: requestId, message: content,
      thinking: voiceMode ? false : thinking, voice: voiceMode});
    if (!messages.some(message => message.request_id === requestId)) addMessage('user', content);
    localStorage.removeItem(`draft:${currentSession}`);
    prompt.value = '';
    resizePrompt();
    const result = await task;
    localStorage.removeItem(`draft:${currentSession}`);
    prompt.value = '';
    status.textContent = result.truncated ? 'Saved. Reply reached its length limit. Ask to continue.' : 'All messages saved';
    if (voice.active) {
      const spoken = document.createElement('div');
      spoken.innerHTML = DOMPurify.sanitize(marked.parse(result.reply));
      spoken.querySelectorAll('pre, code, table').forEach(element => element.remove());
      const reply = spoken.textContent.trim() || 'The reply is displayed in the conversation.';
      document.querySelector('#voice-response').textContent = reply;
      voice.reply(reply);
    }
    await openSession(currentSession, true);
  } catch (error) {
    voice.stop('Voice stopped because the reply failed.');
    try { await openSession(currentSession, true); } catch {}
    showError(error);
  } finally {
    if (!messages.some(message => message.state === 'pending')) setBusy(false);
    await refreshSessions().catch(showError);
    if (!busy) prompt.focus();
  }
}

form.addEventListener('submit', event => {
  event.preventDefault();
  if (browserMode || computerMode) sendBrowserTask(prompt.value.trim()).catch(showError);
  else sendMessage(prompt.value.trim());
});
async function sendBrowserTask(content) {
  if (busy || !ready || browserAgent.unavailable || !content) return;
  voice.stop();
  const sessionId = currentSession;
  const task = await browserAgent.start(content, computerMode ? 'computer' : 'browser');
  if (task && currentSession === sessionId) {
    if (prompt.value.trim() === content) {
      prompt.value = '';
      resizePrompt();
      await saveDraft();
    }
    status.textContent = 'Agent task saved. Follow progress in the monitor.';
  }
}
prompt.addEventListener('input', () => {
  if (!currentSession) return;
  localStorage.setItem(`draft:${currentSession}`, prompt.value);
  clearTimeout(draftTimer);
  draftTimer = setTimeout(() => saveDraft().catch(showError), 600);
});
thinkingButton.addEventListener('click', () => {
  thinking = !thinking;
  thinkingButton.setAttribute('aria-pressed', String(thinking));
  thinkingButton.textContent = thinking ? 'Thinking: On' : 'Thinking: Off';
});
prompt.addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    form.requestSubmit();
  }
});
reset.addEventListener('click', () => newSession().catch(showError));
document.querySelector('#new-session').addEventListener('click', () => newSession().catch(showError));
document.querySelector('#open-sidebar').addEventListener('click', () => {
  if (matchMedia('(min-width: 761px)').matches) document.body.classList.remove('sidebar-collapsed');
  else document.body.classList.add('sidebar-open');
  document.querySelector('#open-sidebar').setAttribute('aria-expanded', 'true');
  document.querySelector('#close-sidebar').focus();
});
document.querySelector('#close-sidebar').addEventListener('click', () => {
  document.body.classList.remove('sidebar-open');
  if (matchMedia('(min-width: 761px)').matches) document.body.classList.add('sidebar-collapsed');
  document.querySelector('#open-sidebar').setAttribute('aria-expanded', 'false');
  document.querySelector('#open-sidebar').focus();
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') {
    if (document.body.classList.contains('sidebar-open')) document.querySelector('#close-sidebar').click();
    document.querySelector('#model-menu').open = false;
    document.querySelector('#tools-info').open = false;
  }
});
document.querySelector('#save-memory').addEventListener('click', async () => {
  const indicator = document.querySelector('#memory-status');
  try {
    await api('/api/memory', {memory: document.querySelector('#memory').value});
    indicator.textContent = 'Saved. Used in every chat.';
  } catch (error) { indicator.textContent = error.message; }
});
async function boot() {
  setBusy(true);
  try {
    const memory = await api('/api/memory');
    document.querySelector('#memory').value = memory.memory;
    const data = await api('/api/sessions');
    const previous = localStorage.getItem('last-session');
    const existing = data.sessions.find(session => session.id === previous) || data.sessions[0];
    if (existing) await openSession(existing.id);
    else await newSession();
  } catch (error) { showError(error); }
}
checkConnection();
refreshModels().catch(error => { modelStatus.textContent = error.message; });
boot();

async function copyText(text, button, label) {
  try {
    await navigator.clipboard.writeText(text);
    button.textContent = 'Copied';
    setTimeout(() => { button.textContent = label; }, 1800);
  } catch { status.textContent = 'Clipboard unavailable. Select the text to copy it.'; }
}
document.querySelector('#search-chats').addEventListener('input', renderSessions);
document.querySelectorAll('[data-prompt]').forEach(button => {
  button.addEventListener('click', () => {
    if (busy || !ready) return;
    prompt.value = button.dataset.prompt;
    prompt.dispatchEvent(new Event('input'));
    prompt.focus();
  });
});
function resizePrompt() {
  prompt.style.height = 'auto';
  prompt.style.height = `${Math.min(prompt.scrollHeight, 180, innerHeight * .25)}px`;
}
prompt.addEventListener('input', resizePrompt);
document.addEventListener('click', event => {
  for (const id of ['model-menu', 'tools-info']) {
    const details = document.querySelector(`#${id}`);
    if (!details.contains(event.target)) details.open = false;
  }
});
