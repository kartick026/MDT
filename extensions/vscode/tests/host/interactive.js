'use strict';
// Human-operated native UI; observes real transport without replacing its results.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const vscode = require('vscode');
const { terminalResult, assertAnalyzed } = require('./terminal');

async function run() {
  const reportPath = process.env.MDT_HOST_TEST_REPORT;
  const progressPath = reportPath + '.progress.json';
  const projectId = process.env.MDT_HOST_TEST_PROJECT;
  const token = process.env.MDT_HOST_TEST_TOKEN;
  delete process.env.MDT_HOST_TEST_TOKEN;
  const originalFetch = globalThis.fetch;
  const originalInputBox = vscode.window.showInputBox;
  const originalWarning = vscode.window.showWarningMessage;
  const originalError = vscode.window.showErrorMessage;
  const originalPicker = vscode.window.showQuickPick;
  const requests = [];
  let currentMode = 'staged';
  let requestedChoice = 'Cancel';
  let activeRun;
  const report = { vscode: vscode.version, checks: [], limitations: ['Disposable synthetic Git fixture and local API only; no deployed service, other OS or marketplace acceptance', 'Harness prefills the native password field and selects only its own fixture project. The human submits credentials and answers actual upload dialogs.'] };
  const write = async (filename, value) => {
    await fs.writeFile(filename + '.next', JSON.stringify(value, null, 2));
    await fs.rename(filename + '.next', filename);
  };
  const phase = async step => {
    await write(progressPath, { step });
    await write(reportPath, { ...report, phase: step });
    console.log('MDT interactive: ' + step);
  };
  try {
    assert.ok(token && projectId, 'Runner must provide a disposable session and project');
    report.consent = [];
    report.errors = [];
    report.projectSelections = [];
    vscode.window.showWarningMessage = async (...args) => {
      const item = { message: args[0], detail: args[1]?.detail, selection: null };
      report.consent.push(item);
      await phase('Native source-upload dialog requested: ' + args[0]);
      const shown = [...args];
      shown[1] = { ...args[1], detail: `NATIVE ACCEPTANCE CHECK: choose ${requestedChoice} on this dialog.\n\n${args[1]?.detail || ''}` };
      const choice = await originalWarning.apply(vscode.window, shown);
      item.selection = choice ?? null;
      await phase('Native upload choice recorded: ' + (choice || 'Cancel'));
      return choice;
    };
    vscode.window.showErrorMessage = (...args) => {
      report.errors.push(args[0]);
      return originalError.apply(vscode.window, args);
    };
    vscode.window.showQuickPick = async (items, options, cancellation) => {
      if (options?.title === 'Choose an MDT project') {
        const fixture = items.find(item => item.item?.id === projectId);
        assert.ok(fixture, 'Disposable fixture project must be present');
        report.projectSelections.push({ label: fixture.label, selection: 'harness setup' });
        return fixture;
      }
      const choice = await originalPicker.call(vscode.window, items,
        { ...options, placeHolder: 'For this test, select Disposable VS Code consent check.' }, cancellation);
      report.projectSelections.push(choice?.label ?? null);
      return choice;
    };
    globalThis.fetch = async (url, options = {}) => {
      if (new URL(url).origin !== 'http://localhost:8000') return originalFetch(url, options);
      const pathname = new URL(url).pathname;
      const entry = { path: pathname, method: options.method || 'GET' };
      requests.push(entry);
      if (entry.method === 'POST' && pathname.endsWith('/analyses')) {
        assert.equal(pathname, `/v1/projects/${projectId}/analyses`, 'Only the disposable test project may receive source');
        const submitted = JSON.parse(options.body);
        assert.deepEqual(submitted.changed_files, ['service.py']);
        assert.equal(submitted.before_files['service.py'], 'def before(): pass\n');
        assert.equal(submitted.after_files['service.py'], currentMode === 'staged' ? 'def staged(): pass\n' : 'def working(): pass\n');
        activeRun.pairedSourceVerified = true;
      }
      const response = await originalFetch(url, options);
      entry.status = response.status;
      if (entry.method === 'POST' && pathname.endsWith('/analyses')) {
        const body = await response.clone().json();
        activeRun.jobId = body.job_id;
        await phase('Upload accepted; waiting for the actual server result.');
      }
      if (activeRun && entry.method === 'GET' && pathname === `/v1/jobs/${activeRun.jobId}` && response.ok) {
        const job = await response.clone().json();
        const terminal = terminalResult(job);
        if (terminal) {
          Object.assign(activeRun, terminal);
          await phase('Server finished with status: ' + job.status);
        }
      }
      return response;
    };
    const extension = vscode.extensions.getExtension('mdt-local-alpha.mdt-architecture-review');
    assert.ok(extension);
    const api = await extension.activate();
    assert.equal(vscode.workspace.isTrusted, true);
    vscode.window.showInputBox = async (options, cancellation) => {
      await phase('Native input: ' + options.title + ' — accept the prefilled value with Enter.');
      return originalInputBox.call(vscode.window, options.title === 'MDT session token' && options.password ? {
        ...options, value: token,
        prompt: 'TEST: a fresh temporary token is already filled. Press Enter; do not paste an older token.',
        validateInput: value => value === token ? undefined : 'This test needs its prefilled temporary token. Press Escape to restart the test connection.'
      } : options, cancellation);
    };
    await phase('Connect: press Enter for both local URL defaults and the prefilled masked temporary token.');
    await vscode.commands.executeCommand('mdt.connect');
    vscode.window.showInputBox = originalInputBox;
    assert.ok(requests.some(r => r.path === '/v1/projects' && r.status === 200), 'Native connection must authenticate');
    const configFile = path.join(process.env.MDT_HOST_TEST_USER_DATA, 'User/settings.json');
    assert.equal((await fs.readFile(configFile, 'utf8').catch(() => '')).includes(token), false);
    report.checks.push('native API/web/token input authenticates against local API; token absent from settings JSON');

    let denied = false, approved = false;
    report.runs = [];
    for (let attempt = 0; attempt < 4 && !(denied && approved); attempt++) {
      requestedChoice = denied ? 'Send and analyze' : 'Cancel';
      currentMode = attempt % 2 ? 'working' : 'staged';
      activeRun = { mode: currentMode };
      report.runs.push(activeRun);
      const consentIndex = report.consent.length;
      const postsBefore = requests.filter(r => r.method === 'POST').length;
      await phase(`Upload check ${attempt + 1}: choose ${requestedChoice}; the instruction is also in the native dialog.`);
      let settled = false;
      const analysis = vscode.commands.executeCommand(currentMode === 'staged' ? 'mdt.analyzeStaged' : 'mdt.analyzeWorking').finally(() => { settled = true; });
      while (!activeRun.jobStatus && !settled) await new Promise(resolve => setTimeout(resolve, 250));
      if (settled) await analysis;
      assert.equal(report.consent.length, consentIndex + 1, 'Source-upload dialog must actually be reached; errors: ' + report.errors.join('; '));
      activeRun.selection = report.consent[consentIndex].selection;
      if (activeRun.selection === null) {
        assert.equal(requests.filter(r => r.method === 'POST').length, postsBefore, 'Declined consent must send no source');
        if (!denied) report.checks.push('native upload cancellation submits no analysis');
        denied = true;
      } else {
        assert.equal(activeRun.selection, 'Send and analyze');
        assertAnalyzed(activeRun);
        assert.equal(activeRun.pairedSourceVerified, true);
        assert.equal(requests.filter(r => r.method === 'POST').length, postsBefore + 1);
        // The fetch observer sees the result just before the client consumes it.
        const viewDeadline = Date.now() + 5000;
        while (api.getViewState().status !== activeRun.jobStatus && Date.now() < viewDeadline) {
          await new Promise(resolve => setTimeout(resolve, 25));
        }
        assert.equal(api.getViewState().status, activeRun.jobStatus);
        if (!approved) report.checks.push('native upload approval sends exact mode-specific before/after fixture once and displays actual server result');
        approved = true;
      }
      if (!(denied && approved)) {
        const nextChoice = denied ? 'Send and analyze' : 'Cancel';
        await phase(`Verified ${activeRun.selection || 'Cancel'}. Continue in the editor, then choose ${nextChoice} on the next upload.`);
        const next = await vscode.window.showInformationMessage(`That check passed. On the next source-upload dialog, choose ${nextChoice}.`, { modal: true }, 'Continue consent check');
        assert.equal(next, 'Continue consent check', 'Remaining consent check was not started');
      }
    }
    assert.ok(denied && approved, 'Both native denial and approval must be observed');

    const beforeDisconnect = requests.length;
    await vscode.commands.executeCommand('mdt.disconnect');
    await vscode.commands.executeCommand('mdt.analyzeStaged');
    assert.equal(requests.length, beforeDisconnect, 'Disconnected command must stop before network access');
    assert.equal(api.getViewState().status, 'idle');
    report.checks.push('disconnect clears view and credential; subsequent source command makes no network call');
    report.passed = report.checks.length;
    await phase('Passed; closing the disposable editor and revoking its test token.');
  } catch (error) {
    report.error = error.message;
    await phase('Stopped: ' + error.message);
    await vscode.window.showErrorMessage('The MDT interactive test stopped before all checks completed.', { modal: true, detail: report.errors.join('\n') || error.message }, 'Close test');
    throw error;
  } finally {
    globalThis.fetch = originalFetch;
    vscode.window.showInputBox = originalInputBox;
    vscode.window.showWarningMessage = originalWarning;
    vscode.window.showErrorMessage = originalError;
    vscode.window.showQuickPick = originalPicker;
    report.requests = requests;
    await write(reportPath, report);
  }
}

module.exports = { run };
