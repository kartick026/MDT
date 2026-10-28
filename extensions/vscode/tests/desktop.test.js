const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// Exercise real command/client code with deterministic UI choices and transport.
// Native dialogs and SecretStorage are separately covered by host acceptance.
function harness({ trusted = true, approve = false, onConsent, cancel = false, expired = false } = {}) {
  const commands = new Map(), secrets = new Map(), state = new Map();
  const requests = [], errors = [], warnings = [], inputs = [];
  const config = { apiUrl: 'http://localhost:8000', webUrl: 'http://localhost:5173' };
  let configListener, cancellation, gitCalls = 0;
  const disposable = { dispose() {} };
  const payload = { source: 'patch', changed_files: ['service.py'], before_files: { 'service.py': 'def before(): pass\n' }, after_files: { 'service.py': 'def after(): pass\n' } };
  const vscode = {
    EventEmitter: class { event = () => {}; fire() {} dispose() {} },
    TreeItem: class { constructor(label) { this.label = label; } }, ThemeIcon: class {},
    TreeItemCollapsibleState: { None: 0, Collapsed: 1 }, StatusBarAlignment: { Left: 1 },
    ConfigurationTarget: { Global: 1 }, ProgressLocation: { Notification: 1 },
    languages: { createDiagnosticCollection: () => ({ ...disposable, clear() {} }) },
    commands: { registerCommand(name, fn) { commands.set(name, fn); return disposable; }, async executeCommand() {} },
    workspace: {
      isTrusted: trusted, textDocuments: [], workspaceFolders: [{ name: 'fixture', uri: { scheme: 'file', fsPath: '/fixture' } }],
      getConfiguration: () => ({ get: key => config[key], async update(key, value) { config[key] = value; configListener?.({ affectsConfiguration: name => name === `mdt.${key}` }); } }),
      onDidChangeConfiguration(fn) { configListener = fn; return disposable; },
    },
    window: {
      createOutputChannel: () => ({ ...disposable, clear() {}, appendLine() {}, show() {} }),
      createStatusBarItem: () => ({ ...disposable, show() {} }), createTreeView: () => disposable,
      async showInputBox() { return inputs.shift(); }, async showQuickPick(items) { return items[0]; },
      async showWarningMessage(...args) { warnings.push(args); if (onConsent) await onConsent(config); return approve ? args.at(-1) : undefined; },
      async showErrorMessage(message) { errors.push(message); }, async showInformationMessage() {},
      async withProgress(_, fn) {
        const callbacks = [];
        const token = { isCancellationRequested: false, onCancellationRequested(cb) { callbacks.push(cb); return disposable; } };
        cancellation = () => { token.isCancellationRequested = true; callbacks.forEach(cb => cb()); };
        return fn({ report() {} }, token);
      },
    },
    Uri: { parse: value => value }, env: { async openExternal() {} },
  };
  const context = {
    subscriptions: [], secrets: { async get(k) { return secrets.get(k); }, async store(k, v) { secrets.set(k, v); }, async delete(k) { secrets.delete(k); } },
    workspaceState: { get: k => state.get(k), async update(k, v) { v === undefined ? state.delete(k) : state.set(k, v); } },
  };
  let authenticated = false;
  const sandbox = {
    module: { exports: {} }, URL, URLSearchParams, AbortController, setTimeout, clearTimeout,
    crypto: require('node:crypto').webcrypto,
    fetch: async (url, options) => {
      requests.push({ url, options });
      if (expired && authenticated) return { ok: false, status: 401, json: async () => ({ detail: 'Session expired' }) };
      let body;
      if (url.endsWith('/projects')) body = { projects: [{ id: 'p', repo_url: 'https://github.com/acme/repo', name: 'Fixture', ready: true, snapshot_version: 'snapshot' }] };
      else if (options.method === 'POST') body = { job_id: 'j', status: 'queued' };
      else if (options.method === 'DELETE') body = { status: 'cancelled' };
      else {
        if (cancel) { cancellation(); throw new Error('Request aborted'); }
        body = { status: 'succeeded', result: { risk_score: 0, smells: [] } };
      }
      return { ok: true, status: 200, json: async () => body };
    },
  };
  const env = vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../../../packages/client/index.js'), 'utf8'), env);
  const client = sandbox.module.exports;
  sandbox.module = { exports: {} };
  sandbox.require = name => name === 'vscode' ? vscode : name === './client' ? client : name === './git' ? {
    async collectChanges() { gitCalls++; return { payload, bytes: 38, repoUrl: 'https://github.com/acme/repo', root: '/fixture' }; },
  } : name === './results' ? require('../src/results') : require(name);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../src/extension.js'), 'utf8'), env);
  const api = sandbox.module.exports.activate(context);
  return { requests, errors, warnings, payload, api, state, gitCalls: () => gitCalls,
    async run(name) { return commands.get(name)(); },
    async connect() { inputs.push(config.apiUrl, config.webUrl, 'disposable-test-token'); await commands.get('mdt.connect')(); authenticated = true; },
  };
}

test('desktop Restricted Mode refuses both source commands before Git or network access', async () => {
  const h = harness({ trusted: false });
  await h.run('mdt.analyzeStaged'); await h.run('mdt.analyzeWorking');
  assert.equal(h.gitCalls(), 0); assert.equal(h.requests.length, 0);
  assert.equal(h.errors.length, 2); assert.ok(h.errors.every(e => /Trust this workspace/.test(e)));
});

test('declining desktop source consent sends no analysis or file contents', async () => {
  const h = harness(); await h.connect(); await h.run('mdt.analyzeStaged');
  assert.deepEqual(h.errors, []); assert.equal(h.gitCalls(), 1);
  assert.match(h.warnings[0][0], /full before\/after source/);
  assert.equal(h.warnings[0][1].detail, 'service.py');
  assert.equal(h.requests.some(r => r.options.method === 'POST'), false);
});

test('approved desktop upload preserves paired source and saved result identity', async () => {
  const h = harness({ approve: true }); await h.connect(); await h.run('mdt.analyzeWorking');
  assert.deepEqual(h.errors, []);
  const submission = h.requests.find(r => r.options.method === 'POST');
  assert.equal(submission.url, 'http://localhost:8000/v1/projects/p/analyses');
  assert.deepEqual(JSON.parse(submission.options.body), { ...h.payload, snapshot_version: 'snapshot' });
  assert.equal(h.state.get('mdt.lastJob').jobId, 'j'); assert.equal(h.api.getViewState().status, 'succeeded');
});

test('changing API while source consent is open prevents the upload', async () => {
  const h = harness({ approve: true, onConsent: config => { config.apiUrl = 'https://different.example'; } });
  await h.connect(); await h.run('mdt.analyzeStaged');
  assert.equal(h.requests.some(r => r.options.method === 'POST'), false);
  assert.match(h.errors.at(-1), /connection changed before upload/);
});

test('expired desktop credentials prevent analysis submission', async () => {
  const h = harness({ approve: true, expired: true }); await h.connect(); await h.run('mdt.analyzeStaged');
  assert.equal(h.requests.some(r => r.options.method === 'POST'), false);
  assert.equal(h.warnings.length, 0); assert.ok(h.errors.length);
});

test('desktop progress cancellation requests cancellation of the submitted job', async () => {
  const h = harness({ approve: true, cancel: true }); await h.connect(); await h.run('mdt.analyzeWorking');
  assert.deepEqual(h.errors, []);
  assert.equal(h.requests.find(r => r.options.method === 'DELETE').url, 'http://localhost:8000/v1/jobs/j');
  assert.equal(h.api.getViewState().status, 'cancelled');
});
