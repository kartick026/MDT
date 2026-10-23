'use strict';
// Uses the documented --extensionDevelopmentPath / --extensionTestsPath host interface.
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { spawn, execFileSync } = require('node:child_process');

async function run() {
  const executable = process.env.VSCODE_EXECUTABLE || (process.platform === 'win32' ? path.join(process.env.LOCALAPPDATA, 'Programs/Microsoft VS Code/Code.exe') : 'code');
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'mdt-vscode-host-'));
  const fixture = path.join(root, 'fixture');
  const web = process.env.MDT_HOST_KIND === 'web';
  const report = web ? path.join(fixture, 'web-host-result.json') : path.join(root, 'result.json');
  await fs.mkdir(fixture);
  const git = (...args) => execFileSync('git', ['-c', 'core.hooksPath=', ...args], { cwd: fixture, stdio: 'pipe', windowsHide: true });
  git('init'); git('config', 'user.name', 'MDT Host Test'); git('config', 'user.email', 'host-test@example.invalid');
  await fs.writeFile(path.join(fixture, 'service.py'), 'def before(): pass\n');
  git('add', '.'); git('commit', '-m', 'Fixture baseline');
  await fs.writeFile(path.join(fixture, 'service.py'), 'def staged(): pass\n'); git('add', 'service.py');
  await fs.writeFile(path.join(fixture, 'service.py'), 'def working(): pass\n');
  try {
    const env = { ...process.env, MDT_HOST_TEST_REPORT: report };
    delete env.ELECTRON_RUN_AS_NODE;
    const code = await new Promise((resolve, reject) => {
      const child = spawn(executable, [fixture, '--no-sandbox', '--disable-gpu', '--disable-extensions', '--skip-welcome', '--skip-release-notes', '--disable-workspace-trust',
        `--user-data-dir=${path.join(root, 'user-data')}`, `--extensions-dir=${path.join(root, 'extensions')}`,
        ...(web ? ['--extensionDevelopmentKind=web'] : []),
        `--extensionDevelopmentPath=${path.resolve(__dirname, '../..')}`, `--extensionTestsPath=${path.join(__dirname, web ? 'web.js' : 'index.js')}`], { env, windowsHide: true, stdio: 'inherit' });
      const timer = setTimeout(() => { child.kill(); reject(new Error('VS Code host tests exceeded 90 seconds.')); }, 90000);
      child.once('error', error => { clearTimeout(timer); reject(error); });
      child.once('exit', result => { clearTimeout(timer); resolve(result); });
    });
    if (code !== 0) throw new Error(`VS Code extension host exited with ${code}.`);
    const result = JSON.parse(await fs.readFile(report, 'utf8'));
    console.log(JSON.stringify(result, null, 2));
  } finally {
    const resolved = path.resolve(root);
    if (path.dirname(resolved) === path.resolve(os.tmpdir()) && path.basename(resolved).startsWith('mdt-vscode-host-')) {
      await fs.rm(resolved, { recursive: true, force: true, maxRetries: 5, retryDelay: 300 });
    }
  }
}

run().catch(error => { console.error(error); process.exitCode = 1; });
