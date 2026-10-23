'use strict';
const vscode = require('vscode');
const MDT = require('./client');
const { collectChanges } = require('./git');
const { resultTree, statusText } = require('./results');

function activate(context) {
  const output = vscode.window.createOutputChannel('MDT');
  const diagnostics = vscode.languages.createDiagnosticCollection('mdt');
  const changed = new vscode.EventEmitter();
  let currentJob;
  let connectionEpoch = 0;
  const tree = { onDidChangeTreeData: changed.event, getChildren: item => item?.children || resultTree(currentJob), getTreeItem: item => {
    const node = new vscode.TreeItem(item.label, item.children?.length ? (item.expanded ? vscode.TreeItemCollapsibleState.Expanded : vscode.TreeItemCollapsibleState.Collapsed) : vscode.TreeItemCollapsibleState.None);
    node.description = item.description;
    node.tooltip = item.tooltip || item.label;
    if (item.icon) node.iconPath = new vscode.ThemeIcon(item.icon);
    if (item.file_path) node.command = { command: 'mdt.openEvidence', title: 'Open source evidence', arguments: [item] };
    return node;
  } };
  const view = vscode.window.createTreeView('mdt.findings', { treeDataProvider: tree, showCollapseAll: true });
  const statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 20);
  statusBar.name = 'MDT analysis status';
  statusBar.command = 'mdt.showFindings';
  function updateView(job) {
    currentJob = job;
    statusBar.text = statusText(job);
    statusBar.tooltip = job?.result ? MDT.resultSummary(job) : 'MDT architecture findings — select to open';
    changed.fire();
    statusBar.show();
  }
  function clearResults() { diagnostics.clear(); output.clear(); updateView(undefined); }
  updateView();
  context.subscriptions.push(output, diagnostics, changed, view, statusBar);
  const configuration = () => vscode.workspace.getConfiguration('mdt');
  const server = () => MDT.validateServerUrl(configuration().get('apiUrl'));
  const tokenKey = () => `mdt.token.${server()}`;
  async function api() {
    const endpoint = server();
    const epoch = connectionEpoch;
    const token = await context.secrets.get(`mdt.token.${endpoint}`);
    if (endpoint !== server() || epoch !== connectionEpoch) throw new Error('The MDT connection changed. Run the command again.');
    if (!token) throw new Error('Run MDT: Connect to Server first.');
    return MDT.createClient({ baseUrl: endpoint, token });
  }
  function command(name, handler) {
    context.subscriptions.push(vscode.commands.registerCommand(name, async (...args) => {
      try { return await handler(...args); }
      catch (error) { vscode.window.showErrorMessage(`MDT: ${MDT.errorMessage(error)}`); }
    }));
  }
  async function connect() {
    const baseUrl = await vscode.window.showInputBox({ title: 'MDT API URL', value: configuration().get('apiUrl'), ignoreFocusOut: true, validateInput: value => { try { MDT.validateServerUrl(value); } catch (error) { return error.message; } } });
    if (!baseUrl) return;
    const webUrl = await vscode.window.showInputBox({ title: 'MDT web dashboard URL', value: configuration().get('webUrl'), ignoreFocusOut: true, validateInput: value => { try { MDT.validateServerUrl(value); } catch (error) { return error.message; } } });
    if (!webUrl) return;
    const token = await vscode.window.showInputBox({ title: 'MDT session token', prompt: 'Copy your short-lived MDT token from My Account. Do not enter a GitHub or model-provider key.', password: true, ignoreFocusOut: true });
    if (!token) return;
    const endpoint = MDT.validateServerUrl(baseUrl);
    await MDT.createClient({ baseUrl: endpoint, token }).projects();
    await configuration().update('apiUrl', endpoint, vscode.ConfigurationTarget.Global);
    await configuration().update('webUrl', MDT.validateServerUrl(webUrl), vscode.ConfigurationTarget.Global);
    if (server() !== endpoint) throw new Error('The API URL changed during connection. Connect again.');
    await context.secrets.store(`mdt.token.${endpoint}`, token.trim());
    connectionEpoch += 1;
    await context.workspaceState.update('mdt.lastJob', undefined);
    clearResults();
    vscode.window.showInformationMessage('MDT connected. Source is sent only after an Analyze command and upload confirmation.');
  }
  async function refresh(last, { reveal = true, client, signal, epoch = connectionEpoch } = {}) {
    if (epoch !== connectionEpoch) throw new Error('The MDT session changed. Refresh an analysis for the current session.');
    if (last.server !== server()) throw new Error('The connected server changed. Select an analysis for the current connection.');
    const job = await (client || await api()).job(last.jobId, { signal });
    if (last.server !== server() || epoch !== connectionEpoch) return job;
    updateView(job);
    if (reveal) output.show(true);
    output.clear();
    output.appendLine(`MDT job ${last.jobId} — ${job.status}`);
    output.appendLine(job.result ? MDT.resultSummary(job) : job.stage || 'Waiting for the server');
    if (job.error) output.appendLine(typeof job.error === 'string' ? job.error : JSON.stringify(job.error));
    if (job.result) {
      output.appendLine('\nSource evidence and findings:');
      output.appendLine(JSON.stringify(job.result, null, 2));
      diagnostics.clear();
      const findings = job.result.findings || job.result.smells || [];
      for (const finding of findings) {
        if (!finding.file_path || !Number.isInteger(finding.line) || finding.line < 1 || !last.root) continue;
        const path = require('node:path');
        const relative = path.relative(last.root, path.resolve(last.root, finding.file_path));
        if (relative.startsWith('..') || path.isAbsolute(relative)) continue;
        const uri = vscode.Uri.file(path.join(last.root, relative));
        const line = Math.max(0, finding.line - 1);
        const diagnostic = new vscode.Diagnostic(new vscode.Range(line, 0, line, 1), finding.description || finding.message || finding.type, vscode.DiagnosticSeverity.Warning);
        diagnostic.source = 'MDT';
        diagnostics.set(uri, [...(diagnostics.get(uri) || []), diagnostic]);
      }
    }
    return job;
  }
  async function analyze(mode) {
    if (!vscode.workspace.isTrusted) throw new Error('Trust this workspace before reading Git changes.');
    const folders = vscode.workspace.workspaceFolders || [];
    if (!folders.length) throw new Error('Open a Git workspace first.');
    const folder = folders.length === 1 ? folders[0] : (await vscode.window.showQuickPick(folders.map(item => ({ label: item.name, item })), { title: 'Choose a Git workspace' }))?.item;
    if (!folder) return;
    if (folder.uri.scheme !== 'file') throw new Error('This alpha needs a filesystem Git workspace and a desktop/remote Node extension host.');
    if (vscode.workspace.textDocuments.some(document => document.isDirty)) {
      const answer = await vscode.window.showWarningMessage('MDT reads saved files or the Git index. Unsaved editor changes will not be included.', { modal: true }, 'Analyze saved/index contents');
      if (!answer) return;
    }
    const endpoint = server();
    const epoch = connectionEpoch;
    const client = await api();
    const collected = await collectChanges(folder.uri.fsPath, mode);
    const projects = (await client.projects()).filter(project => project.ready !== false);
    const matches = collected.repoUrl ? projects.filter(project => project.repo_url.replace(/\.git$/, '').replace(/\/$/, '').toLowerCase() === collected.repoUrl.replace(/\/$/, '').toLowerCase()) : projects;
    if (!matches.length) throw new Error('No imported MDT project matches this Git remote. Create it in the web workspace first.');
    const project = matches.length === 1 ? matches[0] : (await vscode.window.showQuickPick(matches.map(item => ({ label: item.name, description: item.repo_url, item })), { title: 'Choose an MDT project' }))?.item;
    if (!project) return;
    const approved = await vscode.window.showWarningMessage(`Send full before/after source for ${collected.payload.changed_files.length} ${mode === 'staged' ? 'staged' : 'saved tracked'} files (${Math.ceil(collected.bytes / 1024)} KiB) to ${server()}? Untracked files are excluded.`, { modal: true, detail: collected.payload.changed_files.join('\n') }, 'Send and analyze');
    if (!approved) return;
    if (endpoint !== server() || epoch !== connectionEpoch) throw new Error('The connection changed before upload. Run Analyze again.');
    const payload = { ...collected.payload, snapshot_version: project.snapshot_version };
    const submitted = await client.analyze(project.id, payload, require('node:crypto').randomUUID());
    if (epoch !== connectionEpoch) {
      await client.cancel(submitted.job_id).catch(() => {});
      throw new Error('The session changed during submission; check the original account History for its final state.');
    }
    const last = { jobId: submitted.job_id, projectId: project.id, root: collected.root, server: endpoint };
    await context.workspaceState.update('mdt.lastJob', last);
    await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: 'MDT analysis', cancellable: true }, async (progress, cancellation) => {
      const controller = new AbortController();
      let cancellationResult;
      const abort = cancellation.onCancellationRequested(() => {
        controller.abort();
        cancellationResult = client.cancel(last.jobId).then(job => { if (last.server === server() && epoch === connectionEpoch) updateView(job); })
          .catch(error => output.appendLine(`Cancellation could not be confirmed: ${MDT.errorMessage(error)}`));
      });
      try {
        for (let attempt = 0; attempt < 60 && !cancellation.isCancellationRequested; attempt += 1) {
          const job = await refresh(last, { reveal: attempt === 0, client, signal: controller.signal, epoch });
          progress.report({ message: job.stage || job.status });
          if (MDT.isTerminal(job.status)) {
            const choice = await vscode.window.showInformationMessage(`MDT analysis ${job.status}${job.result?.partial_results ? ' with partial coverage' : ''}.`, 'Open web result');
            if (choice) await open(last);
            return;
          }
          await new Promise(resolve => setTimeout(resolve, 2000));
        }
        output.appendLine('The job can continue on the server. Use MDT: Refresh Last Analysis to resume.');
      } catch (error) {
        if (!cancellation.isCancellationRequested) throw error;
        output.appendLine('MDT polling cancelled. See History for the final server state.');
      } finally { abort.dispose(); await cancellationResult; }
    });
  }
  async function lastJob() {
    const last = context.workspaceState.get('mdt.lastJob');
    if (!last || last.server !== server()) throw new Error('There is no saved analysis for the connected server.');
    return last;
  }
  async function open(last) { await vscode.env.openExternal(vscode.Uri.parse(MDT.webLink(configuration().get('webUrl'), last.projectId, last.jobId))); }
  command('mdt.connect', connect);
  command('mdt.disconnect', async () => { connectionEpoch += 1; await context.secrets.delete(tokenKey()); await context.workspaceState.update('mdt.lastJob', undefined); clearResults(); vscode.window.showInformationMessage('MDT session removed from this extension. Sign out in the web app to revoke it server-side.'); });
  command('mdt.analyzeStaged', () => analyze('staged'));
  command('mdt.analyzeWorking', () => analyze('working'));
  command('mdt.openLastAnalysis', async () => open(await lastJob()));
  command('mdt.refreshLastAnalysis', async () => refresh(await lastJob()));
  command('mdt.showFindings', () => vscode.commands.executeCommand('mdt.findings.focus'));
  command('mdt.openEvidence', async item => {
    const last = await lastJob();
    if (!last.root || typeof item?.file_path !== 'string') return open(last);
    const fs = require('node:fs/promises');
    const path = require('node:path');
    const { inside } = require('./git');
    const root = await fs.realpath(last.root);
    const target = inside(root, item.file_path);
    try {
      const resolved = await fs.realpath(target);
      inside(root, path.relative(root, resolved));
      const document = await vscode.workspace.openTextDocument(vscode.Uri.file(resolved));
      const editor = await vscode.window.showTextDocument(document, { preview: true });
      // Only navigate to a line when the server supplied one; do not invent locations.
      if (Number.isInteger(item.line) && item.line > 0 && item.line <= document.lineCount) {
        const range = new vscode.Range(item.line - 1, 0, item.line - 1, 0);
        editor.selection = new vscode.Selection(range.start, range.end);
        editor.revealRange(range);
      }
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
      await open(last); // Deleted files have no working-tree location.
    }
  });
  context.subscriptions.push(vscode.workspace.onDidChangeConfiguration(event => {
    if (event.affectsConfiguration('mdt.apiUrl')) { connectionEpoch += 1; clearResults(); }
  }));
  // Read-only extension API permits integrations and host tests without exposing credentials or source.
  return { getViewState: () => ({ status: currentJob?.status || 'idle', text: statusBar.text, roots: resultTree(currentJob).map(item => item.label) }) };
}
module.exports = { activate };
