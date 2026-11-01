'use strict';
// Runs inside the actual VS Code extension host, not a mocked vscode module.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const vscode = require('vscode');

async function run() {
  const extension = vscode.extensions.getExtension('mdt-local-alpha.mdt-architecture-review');
  assert.ok(extension, 'Development extension must be discovered by VS Code');
  const api = await extension.activate();
  assert.equal(extension.isActive, true);
  assert.deepEqual(api.getViewState(), { status: 'idle', text: '$(shield) MDT', roots: ['No analysis loaded'] });
  const commands = await vscode.commands.getCommands(true);
  for (const name of ['mdt.connect', 'mdt.disconnect', 'mdt.analyzeStaged', 'mdt.analyzeWorking', 'mdt.openLastAnalysis', 'mdt.refreshLastAnalysis', 'mdt.showFindings', 'mdt.openEvidence']) assert.ok(commands.includes(name), `${name} registered`);
  await vscode.commands.executeCommand('mdt.showFindings');
  assert.equal(api.getViewState().status, 'idle');
  const config = vscode.workspace.getConfiguration('mdt');
  assert.equal(config.get('apiUrl'), 'http://localhost:8000');
  assert.equal(config.inspect('apiUrl').workspaceValue, undefined);
  const { collectChanges } = require(path.join(extension.extensionPath, 'dist/git'));
  const folder = vscode.workspace.workspaceFolders[0].uri.fsPath;
  const staged = await collectChanges(folder, 'staged');
  const working = await collectChanges(folder, 'working');
  assert.match(staged.payload.after_files['service.py'], /def staged/);
  assert.match(working.payload.after_files['service.py'], /def working/);
  assert.notEqual(staged.payload.after_files['service.py'], working.payload.after_files['service.py']);
  await fs.writeFile(process.env.MDT_HOST_TEST_REPORT, JSON.stringify({
    vscode: vscode.version, passed: 5,
    checks: ['extension activation and idle view', 'command registration', 'real findings view focus', 'application configuration defaults', 'real staged and working Git collection in extension host'],
    limitations: ['No UI upload confirmation or credential-entry automation', 'No store installation or browser extension host test'],
  }, null, 2));
  console.log('MDT: 5 extension-host checks passed.');
}

module.exports = { run };
