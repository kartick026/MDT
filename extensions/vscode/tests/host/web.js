'use strict';
// Executed by the real VS Code browser worker. No Node globals or test framework.
const vscode = require('vscode');
const assert = (condition, message) => { if (!condition) throw new Error(message); };
async function run() {
  assert(typeof process === 'undefined', 'Tests must run inside the browser worker');
  const extension = vscode.extensions.getExtension('mdt-local-alpha.mdt-architecture-review');
  assert(extension, 'Extension is discoverable');
  const api = await extension.activate();
  assert(api.getRuntime() === 'web', 'Browser entry is active');
  assert(api.getViewState().status === 'idle', 'Findings view initializes without credentials');
  const commands = await vscode.commands.getCommands(true);
  for (const command of ['mdt.connect','mdt.disconnect','mdt.analyzeRepository','mdt.refreshLastAnalysis','mdt.showFindings']) assert(commands.includes(command), `${command} is registered`);
  await vscode.commands.executeCommand('mdt.showFindings');
  const report = vscode.Uri.joinPath(vscode.workspace.workspaceFolders[0].uri, 'web-host-result.json');
  await vscode.workspace.fs.writeFile(report, new TextEncoder().encode(JSON.stringify({passed:4,host:vscode.version,runtime:'web-worker',checks:['no Node globals','browser entry activation','commands registered','findings view opens']})));
}
module.exports = {run};
