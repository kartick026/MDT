'use strict';
// Separate real host run with Workspace Trust enabled and fresh user data.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const vscode = require('vscode');

async function run() {
  assert.equal(vscode.workspace.isTrusted, false, 'This run must actually be in Restricted Mode');
  const extension = vscode.extensions.getExtension('mdt-local-alpha.mdt-architecture-review');
  // Detect attempts before they reach any local Git process or network service.
  const childProcess = require('node:child_process');
  const originalExec = childProcess.execFile;
  const originalFetch = globalThis.fetch;
  let gitCalls = 0;
  let networkCalls = 0;
  childProcess.execFile = () => { gitCalls++; throw new Error('Unexpected Git process in Restricted Mode'); };
  globalThis.fetch = () => { networkCalls++; throw new Error('Unexpected network request in Restricted Mode'); };
  try {
    // Install sentinels before activation: git.js captures execFile at import.
    const api = await extension.activate();
    assert.equal(extension.isActive, true, 'Read-only features remain available');
    await vscode.commands.executeCommand('mdt.showFindings');
    assert.equal(api.getViewState().status, 'idle');
    await vscode.commands.executeCommand('mdt.analyzeStaged');
    await vscode.commands.executeCommand('mdt.analyzeWorking');
    assert.equal(gitCalls, 0, 'Untrusted commands must not read Git source');
    assert.equal(networkCalls, 0, 'Untrusted commands must not make API requests');
    assert.equal(api.getViewState().status, 'idle');
  } finally {
    childProcess.execFile = originalExec;
    globalThis.fetch = originalFetch;
  }
  await fs.writeFile(process.env.MDT_HOST_TEST_REPORT, JSON.stringify({
    vscode: vscode.version, trusted: vscode.workspace.isTrusted, passed: 4,
    checks: ['actual untrusted workspace', 'limited activation', 'findings view available', 'both source commands make no Git or network calls'],
    limitations: ['Native upload consent and credential UI require separate acceptance'],
  }, null, 2));
}

module.exports = { run };
