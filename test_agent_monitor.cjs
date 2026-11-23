const {test} = require('node:test');
const assert = require('node:assert/strict');
const {AgentMonitor, createAgentMonitorView} = require('./public/agent-monitor.js');

test('browser monitor is available without a browser global', () => {
  assert.equal(typeof AgentMonitor, 'function');
});

test('computer mode is explicitly sent when creating a task', async () => {
  const {monitor, calls} = setup(path => path.includes('?session_id=') ? {tasks: []} : {...task(), mode: 'computer'});
  await monitor.openSession('session-a');
  await monitor.start('Open Notepad', 'computer');
  assert.equal(calls.find(call => call.path === '/api/agent/tasks').data.mode, 'computer');
});

test('desktop approval shows exact operation and sends only its fingerprint', () => {
  const nodes = new Map(), calls = [];
  const element = () => ({dataset: {}, children: [], textContent: '',
    replaceChildren() { this.children = []; }, append(...items) { this.children.push(...items); }});
  const root = {...element(), querySelector(selector) {
    if (!nodes.has(selector)) nodes.set(selector, element());
    return nodes.get(selector);
  }};
  const previousDocument = globalThis.document;
  globalThis.document = {createElement: element};
  try {
    const monitor = {control(...args) { calls.push(args); }};
    const render = createAgentMonitorView(root, monitor, () => {});
    const pending = {...task('awaiting_approval'), mode: 'computer', approval: {
      fingerprint: 'exact', expires: Date.now() / 1000 + 300,
      reason: 'Physical input moves your mouse.', action: {tool: 'desktop_action', action: 'type', value: '<script>data</script>'}}};
    render({task: pending, error: '', pending: false});
    assert.equal(root.querySelector('.agent-approval').hidden, false);
    assert.match(root.querySelector('.agent-approval-detail').textContent, /<script>data<\/script>/);
    assert.equal(root.querySelector('.agent-resume').hidden, true);
    root.querySelector('.agent-approve').onclick();
    assert.deepEqual(calls, [['approve', {fingerprint: 'exact'}]]);
    render({task: {...pending, approval: {...pending.approval, expires: 0}}, error: '', pending: false});
    assert.equal(root.querySelector('.agent-approve').disabled, true);
    render({task: {...task('completed'), autonomous: true, result: 'Finished'}, error: '', pending: false});
    assert.equal(root.hidden, true, 'Final answer belongs in the normal chat transcript');
    assert.equal(root.querySelector('.agent-result').hidden, true);
  } finally { globalThis.document = previousDocument; }
});

test('default timers preserve the browser global receiver', async () => {
  const originalSet = globalThis.setTimeout, originalClear = globalThis.clearTimeout;
  let scheduled = 0, cleared = 0;
  globalThis.setTimeout = function () {
    assert.equal(this, globalThis, 'timer requires its global receiver');
    scheduled++; return 42;
  };
  globalThis.clearTimeout = function () {
    assert.equal(this, globalThis, 'timer requires its global receiver');
    cleared++;
  };
  try {
    const monitor = new AgentMonitor({api: async path => path.includes('?session_id=') ? {tasks: [task()]} : {connected: true}});
    await monitor.openSession('session-a');
    monitor.stopWatching();
    assert.equal(scheduled, 1);
    assert.ok(cleared > 0);
  } finally {
    globalThis.setTimeout = originalSet;
    globalThis.clearTimeout = originalClear;
  }
});

const task = (state = 'executing', id = 'task-1') => ({id, session_id: 'session-a', request: 'Find a source',
  state, steps: [], events: [], tabs: {}, approval: null, result: '', error: ''});
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return {promise, resolve}; };
function setup(handler) {
  const calls = [], renders = [], timers = new Map(); let nextTimer = 0;
  const monitor = new AgentMonitor({api: async (path, data) => {
    calls.push({path, data});
    if (path === '/api/agent/neo/status' || path === '/api/agent/desktop/status') return {available: true, connected: true};
    return handler(path, data);
  }, render: view => renders.push(view), schedule: callback => { timers.set(++nextTimer, callback); return nextTimer; },
  unschedule: id => timers.delete(id)});
  return {monitor, calls, renders, timers};
}

test('restoring an active task blocks duplicate creation and schedules one poll', async () => {
  const {monitor, calls, timers} = setup(() => ({tasks: [task()]}));
  await monitor.openSession('session-a');
  assert.equal(monitor.active, true);
  assert.equal(await monitor.start('duplicate'), null);
  assert.equal(calls.filter(call => call.data).length, 0);
  assert.equal(timers.size, 1);
});

test('late task restoration cannot replace a newly selected session', async () => {
  const old = deferred();
  const {monitor} = setup(path => path.includes('session-a') ? old.promise : {tasks: [task('completed', 'task-b')]});
  const first = monitor.openSession('session-a');
  await monitor.openSession('session-b');
  old.resolve({tasks: [task()]}); await first;
  assert.equal(monitor.sessionId, 'session-b');
  assert.equal(monitor.task.id, 'task-b');
  assert.equal(monitor.active, false);
});

test('creation is single-flight and late responses cannot cross sessions', async () => {
  const created = deferred();
  const {monitor, calls} = setup((path, data) => data ? created.promise : {tasks: []});
  await monitor.openSession('session-a');
  const first = monitor.start('Find a source');
  assert.equal(await monitor.start('duplicate'), null);
  await monitor.openSession('session-b');
  created.resolve(task()); await first;
  assert.equal(monitor.task, null);
  assert.equal(calls.filter(call => call.path === '/api/agent/tasks').length, 1);
});

test('approval sends the displayed fingerprint once and resume acknowledges uncertainty only when requested', async () => {
  const awaiting = {...task('awaiting_approval'), approval: {fingerprint: 'exact-123', action: {type: 'click', value: 'Publish'},
    target: 'Publish', url: 'https://example.org/post', reason: 'Publishes text', expires: '2099-01-01T00:00:00Z'}};
  const control = deferred();
  const {monitor, calls} = setup((path, data) => data ? control.promise : {tasks: [awaiting]});
  await monitor.openSession('session-a');
  const approval = monitor.control('approve', {fingerprint: 'exact-123'});
  assert.equal(await monitor.control('approve', {fingerprint: 'exact-123'}), null);
  control.resolve({...task('paused'), steps: [{state: 'uncertain'}]}); await approval;
  assert.deepEqual(calls.find(call => call.path.endsWith('/approve')).data, {fingerprint: 'exact-123'});
  assert.equal(monitor.active, false);
  assert.equal(monitor.uncertain, true);
  await monitor.control('resume', {acknowledge_uncertain: true});
  assert.deepEqual(calls.find(call => call.path.endsWith('/resume')).data, {acknowledge_uncertain: true});
});

test('poll errors retain the task, recover automatically, and stop polling after completion', async () => {
  let disconnected = true;
  const {monitor, timers} = setup(path => {
    if (path.includes('?session_id=')) return {tasks: [task()]};
    if (disconnected) throw new Error('Server unavailable');
    return task('completed');
  });
  await monitor.openSession('session-a');
  await monitor.poll();
  assert.match(monitor.error, /Server unavailable/);
  assert.equal(monitor.task.id, 'task-1');
  assert.equal(timers.size, 1);
  disconnected = false;
  await monitor.poll();
  assert.equal(monitor.error, '');
  assert.equal(monitor.task.state, 'completed');
  assert.equal(timers.size, 0);
});

test('a stale approval is not sent after the monitor has observed another approval', async () => {
  const {monitor, calls} = setup(() => ({tasks: [{...task('awaiting_approval'), approval: {fingerprint: 'new'}}]}));
  await monitor.openSession('session-a');
  assert.equal(await monitor.control('approve', {fingerprint: 'old'}), null);
  assert.equal(calls.some(call => call.path.endsWith('/approve')), false);
});

test('paused tasks reserve their browser slot until stopped or resumed', async () => {
  const {monitor, calls} = setup(() => ({tasks: [task('paused')]}));
  await monitor.openSession('session-a');
  assert.equal(await monitor.start('new task'), null);
  assert.equal(calls.some(call => call.path === '/api/agent/tasks'), false);
});

test('a slow poll cannot restore an old approval after approval has been submitted', async () => {
  const stale = deferred();
  const approvalTask = {...task('awaiting_approval'), approval: {fingerprint: 'exact'}};
  const {monitor} = setup((path, data) => path.includes('?session_id=') ? {tasks: [approvalTask]} : data ? task() : stale.promise);
  await monitor.openSession('session-a');
  const poll = monitor.poll();
  await monitor.control('approve', {fingerprint: 'exact'});
  stale.resolve(approvalTask); await poll;
  assert.equal(monitor.task.state, 'executing');
});

test('failed session restoration cannot create a duplicate task before reconnecting', async () => {
  const {monitor, calls} = setup(() => { throw new Error('Offline'); });
  await monitor.openSession('session-a');
  assert.equal(await monitor.start('new task'), null);
  assert.equal(calls.some(call => call.path === '/api/agent/tasks'), false);
});

test('paused browser tasks resume without an acknowledgement or approval prompt', () => {
  const nodes = new Map(), controls = [];
  const element = () => ({dataset: {}, children: [], textContent: '',
    replaceChildren() { this.children = []; }, append(...items) { this.children.push(...items); }});
  const root = {...element(), querySelector(selector) {
    if (!nodes.has(selector)) nodes.set(selector, element());
    return nodes.get(selector);
  }};
  const previousDocument = globalThis.document;
  globalThis.document = {createElement: element};
  try {
    const monitor = {uncertain: true, pending: false, control(...args) { controls.push(args); }};
    const render = createAgentMonitorView(root, monitor, () => {});
    render({task: {...task('paused'), steps: [{state: 'uncertain'}]}, error: '', pending: false});
    assert.doesNotMatch(root.innerHTML, /I checked the site|Approve this action|Review this action/);
    assert.equal(root.querySelector('.agent-resume').disabled, false);
    root.querySelector('.agent-resume').onclick();
    assert.deepEqual(controls, [['resume']]);
  } finally {
    if (previousDocument === undefined) delete globalThis.document;
    else globalThis.document = previousDocument;
  }
});
