'use strict';
// Local-only native UI acceptance. No automatic dialog answers or source from this checkout.
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { spawn, execFileSync } = require('node:child_process');

async function run() {
  const api = 'http://localhost:8000';
  const username = process.env.MDT_QA_USERNAME, password = process.env.MDT_QA_PASSWORD;
  if (!username || !password || !process.env.MDT_QA_DEMO_REPO_URL) throw new Error('Set MDT_QA_USERNAME, MDT_QA_PASSWORD and MDT_QA_DEMO_REPO_URL for the local test API.');
  const executable = process.env.VSCODE_EXECUTABLE || path.join(process.env.LOCALAPPDATA, 'Programs/Microsoft VS Code/Code.exe');
  const reportPath = path.resolve(process.env.MDT_HOST_TEST_REPORT || path.join(__dirname, '../../../../scratch/release-2026-10-25/vscode-interactive.json'));
  await fs.mkdir(path.dirname(reportPath), { recursive: true });
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'mdt-vscode-interactive-'));
  let token, project;
  const request = async (route, method = 'GET', body) => {
    const response = await fetch(api + route, { method, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) });
    if (!response.ok) throw new Error(`Local API ${method} ${route}: ${response.status}`);
    return response.status === 204 ? undefined : response.json();
  };
  try {
    token = (await request('/auth/login', 'POST', { username, password })).access_token;
    project = await request('/v1/projects', 'POST', { name: 'Disposable VS Code consent check', repo_url: process.env.MDT_QA_DEMO_REPO_URL, use_demo: true });
    const fixture = path.join(root, 'fixture');
    await fs.mkdir(fixture);
    const git = (...args) => execFileSync('git', ['-c', 'core.hooksPath=', ...args], { cwd: fixture, stdio: 'pipe', windowsHide: true });
    git('init'); git('config', 'user.name', 'MDT Host Test'); git('config', 'user.email', 'host-test@example.invalid');
    git('remote', 'add', 'origin', project.repo_url);
    await fs.writeFile(path.join(fixture, 'service.py'), 'def before(): pass\n');
    git('add', '.'); git('commit', '-m', 'Disposable consent fixture');
    await fs.writeFile(path.join(fixture, 'service.py'), 'def staged(): pass\n'); git('add', 'service.py');
    await fs.writeFile(path.join(fixture, 'service.py'), 'def working(): pass\n');
    const userData = path.join(root, 'user-data');
    await fs.mkdir(path.join(userData, 'User'), { recursive: true });
    await fs.writeFile(path.join(userData, 'User/settings.json'), JSON.stringify({ 'update.mode': 'none', 'extensions.autoUpdate': false, 'extensions.autoCheckUpdates': false }));
    // VS Code suppresses native modal dialogs under --extensionTestsPath.
    // A separate disposable development driver runs the manual checks without that flag.
    const driver = path.join(root, 'driver');
    await fs.mkdir(driver);
    await fs.writeFile(path.join(driver, 'package.json'), JSON.stringify({
      name: 'mdt-native-acceptance-driver', publisher: 'mdt-test', version: '0.0.0',
      engines: { vscode: '^1.95.0' }, main: './index.js', activationEvents: ['onStartupFinished']
    }));
    await fs.writeFile(path.join(driver, 'index.js'), `const vscode = require('vscode');
exports.activate = () => {
  setTimeout(() => require(${JSON.stringify(path.join(__dirname, 'interactive.js'))}).run()
    .catch(error => console.error(error.message))
    .finally(() => vscode.commands.executeCommand('workbench.action.quit')), 1000);
};\n`);
    const env = { ...process.env, MDT_HOST_TEST_TOKEN: token, MDT_HOST_TEST_PROJECT: project.id, MDT_HOST_TEST_REPORT: reportPath, MDT_HOST_TEST_USER_DATA: userData };
    delete env.ELECTRON_RUN_AS_NODE; delete env.MDT_QA_USERNAME; delete env.MDT_QA_PASSWORD;
    const result = await new Promise((resolve, reject) => {
      const child = spawn(executable, [fixture, '--no-sandbox', '--disable-gpu', '--disable-extensions', '--disable-workspace-trust', '--skip-welcome', '--skip-release-notes',
        `--user-data-dir=${userData}`, `--extensions-dir=${path.join(root, 'extensions')}`,
        `--extensionDevelopmentPath=${path.resolve(__dirname, '../..')}`, `--extensionDevelopmentPath=${driver}`], { env, windowsHide: false, stdio: 'inherit' });
      let activity = Date.now();
      const timer = setInterval(async () => {
        const stat = await fs.stat(reportPath + '.progress.json').catch(() => null);
        if (stat) activity = Math.max(activity, stat.mtimeMs);
        if (Date.now() - activity > 15 * 60 * 1000) {
          clearInterval(timer); child.kill(); reject(new Error('Native UI acceptance inactive for fifteen minutes.'));
        }
      }, 10000);
      child.once('error', error => { clearTimeout(timer); reject(error); });
      child.once('exit', code => { clearTimeout(timer); resolve(code); });
    });
    const report = JSON.parse(await fs.readFile(reportPath, 'utf8'));
    console.log(JSON.stringify(report, null, 2));
    if (result !== 0 || report.passed !== 4 || report.error) throw new Error(`Interactive extension host exited with ${result}; completed ${report.passed || 0}/4 checks. Last phase: ${report.phase || 'unknown'}`);
  } finally {
    if (project) await request(`/v1/projects/${project.id}`, 'DELETE').catch(error => console.error('Test-project cleanup: ' + error.message));
    if (token) await request('/auth/logout', 'POST', {}).catch(error => console.error('Test-session cleanup: ' + error.message));
    const resolved = path.resolve(root);
    if (path.dirname(resolved) === path.resolve(os.tmpdir()) && path.basename(resolved).startsWith('mdt-vscode-interactive-')) await fs.rm(resolved, { recursive: true, force: true, maxRetries: 5, retryDelay: 300 });
  }
}
run().catch(error => { console.error(error.message); process.exitCode = 1; });
