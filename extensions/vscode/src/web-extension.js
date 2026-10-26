'use strict';
// Browser-worker entry point: no workspace source, Git process or Node API access.
const vscode = require('vscode');
const MDT = require('../../../packages/client');
const { resultTree, statusText } = require('./results');

function activate(context) {
  let epoch = 0, currentJob, changingSettings = false;
  let writes = Promise.resolve();
  const changed = new vscode.EventEmitter();
  const output = vscode.window.createOutputChannel('MDT');
  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 20);
  status.name = 'MDT analysis status'; status.command = 'mdt.showFindings';
  const view = vscode.window.createTreeView('mdt.findings', { treeDataProvider: {
    onDidChangeTreeData: changed.event,
    getChildren: item => item?.children || resultTree(currentJob, currentJob?.result ? MDT.coverageSummary(currentJob.result) : ''),
    getTreeItem: item => {
      const node = new vscode.TreeItem(item.label, item.children?.length ? vscode.TreeItemCollapsibleState.Collapsed : vscode.TreeItemCollapsibleState.None);
      node.description = item.description; node.tooltip = item.tooltip || item.label;
      if (item.icon) node.iconPath = new vscode.ThemeIcon(item.icon);
      if (item.file_path) node.command = {command:'mdt.openLastAnalysis',title:'Open captured evidence'};
      return node;
    },
  }, showCollapseAll:true });
  function update(job) { currentJob = job; status.text = statusText(job); status.tooltip = job?.result ? MDT.resultSummary(job) : 'MDT architecture review'; status.show(); changed.fire(); }
  function clear() { output.clear(); update(); }
  clear(); context.subscriptions.push(changed, output, status, view);
  vscode.commands.executeCommand('setContext', 'mdt.webHost', true);
  const config = () => vscode.workspace.getConfiguration('mdt');
  const https = value => { const endpoint = MDT.validateServerUrl(value); if (!endpoint.startsWith('https://')) throw new Error('The browser extension host requires an HTTPS MDT endpoint.'); return endpoint; };
  const changedError = () => new Error('The MDT connection changed. Run the command again for the current connection.');
  function serialize(action) { const result = writes.then(action); writes = result.catch(()=>{}); return result; }
  async function session() {
    const generation = epoch, endpoint = https(config().get('apiUrl'));
    const raw = await context.secrets.get('mdt.web.connection');
    if (generation !== epoch || endpoint !== https(config().get('apiUrl'))) throw changedError();
    const saved = raw ? JSON.parse(raw) : null;
    if (!saved?.token || saved.baseUrl !== endpoint) throw new Error('Run MDT: Connect to Server first.');
    return {...saved, generation, client:MDT.createClient({baseUrl:saved.baseUrl,token:saved.token})};
  }
  function check(active) { if (active.generation !== epoch || active.baseUrl !== config().get('apiUrl')) throw changedError(); }
  function command(name, handler) { context.subscriptions.push(vscode.commands.registerCommand(name, async()=>{
    try { return await handler(); } catch(error) { await vscode.window.showErrorMessage(`MDT: ${MDT.errorMessage(error)}${error instanceof TypeError ? ' Check HTTPS, network access and the API CORS configuration for this editor host.' : ''}`); }
  })); }
  async function connect() {
    const generation = ++epoch;
    const validateInput = value => { try { https(value); } catch(error) { return error.message; } };
    const base = await vscode.window.showInputBox({title:'MDT HTTPS API URL',value:config().get('apiUrl'),ignoreFocusOut:true,validateInput});
    if (!base) return;
    const web = await vscode.window.showInputBox({title:'MDT HTTPS web URL',value:config().get('webUrl'),ignoreFocusOut:true,validateInput});
    if (!web) return;
    const token = (await vscode.window.showInputBox({title:'MDT session token',prompt:'Copy your short-lived MDT token from Account. Only the chosen API receives it.',password:true,ignoreFocusOut:true}))?.trim();
    if (!token) return;
    if (token.length > 8192) throw new Error('Invalid MDT session token.');
    const baseUrl=https(base), webUrl=https(web);
    await MDT.createClient({baseUrl,token}).projects();
    await serialize(async()=>{
      if (generation !== epoch) throw changedError();
      changingSettings = true;
      try {
        await config().update('apiUrl',baseUrl,vscode.ConfigurationTarget.Global);
        await config().update('webUrl',webUrl,vscode.ConfigurationTarget.Global);
      } finally { changingSettings = false; }
      if (generation !== epoch) throw changedError();
      await context.secrets.store('mdt.web.connection',JSON.stringify({id:crypto.randomUUID(),baseUrl,webUrl,token}));
      if (generation !== epoch) { await context.secrets.delete('mdt.web.connection'); throw changedError(); }
      await context.workspaceState.update('mdt.web.lastJob',undefined);
      clear();
    });
    await vscode.window.showInformationMessage('MDT connected. Browser mode sends only the selected repository/revision identifier after confirmation. Workspace files are never uploaded.');
  }
  async function savedJob(active) {
    const last = context.workspaceState.get('mdt.web.lastJob');
    if (!last || last.connectionId !== active.id || last.server !== active.baseUrl) throw new Error('No saved analysis for this connection. Run Analyze Repository Revision.');
    return last;
  }
  async function open(active,last) { check(active); await vscode.env.openExternal(vscode.Uri.parse(MDT.webLink(active.webUrl,last.projectId,last.jobId))); }
  async function refresh(active,last,signal) {
    check(active);
    const job=await active.client.job(last.jobId,{signal});
    check(active); update(job); output.clear();
    output.appendLine(`MDT job ${last.jobId}: ${job.status}`);
    output.appendLine(job.result ? MDT.resultSummary(job) : job.stage || 'Waiting for server');
    if(job.error)output.appendLine(typeof job.error==='string'?job.error:JSON.stringify(job.error));
    return job;
  }
  async function analyze() {
    const active=await session();
    const projects=(await active.client.projects()).filter(project=>project.ready!==false);
    check(active);
    if(!projects.length)throw new Error('Import a project in the MDT web app first.');
    const choice=await vscode.window.showQuickPick(projects.map(item=>({label:item.name,description:item.repo_url,item})),{title:'Choose the MDT repository to analyze'});
    if(!choice)return;
    const project=choice.item;
    const url=await vscode.window.showInputBox({title:'GitHub repository, commit, comparison or pull request URL',value:project.repo_url,ignoreFocusOut:true,validateInput:value=>{try{MDT.analysisPayload(MDT.parseGitHubUrl(value),project);}catch(error){return error.message;}}});
    if(!url)return;
    const payload=MDT.analysisPayload(MDT.parseGitHubUrl(url),project);
    const confirmation=await vscode.window.showWarningMessage(`Ask ${active.baseUrl} to analyze ${project.repo_url}?`,{modal:true,detail:`Revision: ${payload.pull_request ? 'PR '+payload.pull_request : payload.head_ref}. Only repository/revision identifiers are sent. No workspace files or unsaved edits are read. The server fetches source within its configured limits.`},'Analyze repository');
    if(confirmation!=='Analyze repository')return;
    check(active);
    const submitted=await active.client.analyze(project.id,payload,crypto.randomUUID());
    if(active.generation!==epoch){await active.client.cancel(submitted.job_id).catch(()=>{});throw changedError();}
    const last={jobId:submitted.job_id,projectId:project.id,server:active.baseUrl,connectionId:active.id};
    await serialize(async()=>{check(active);await context.workspaceState.update('mdt.web.lastJob',last);});
    check(active);
    await vscode.window.withProgress({location:vscode.ProgressLocation.Notification,title:'MDT repository analysis',cancellable:true},async(progress,cancellation)=>{
      const controller=new AbortController();let cancelResult;
      const listener=cancellation.onCancellationRequested(()=>{controller.abort();cancelResult=active.client.cancel(last.jobId).catch(error=>output.appendLine(`Cancellation could not be confirmed: ${MDT.errorMessage(error)}`));});
      try{
        for(let attempt=0;attempt<60&&!cancellation.isCancellationRequested;attempt+=1){
          const job=await refresh(active,last,controller.signal);progress.report({message:job.stage||job.status});
          if(MDT.isTerminal(job.status)){output.show(true);return;}
          await new Promise(resolve=>setTimeout(resolve,2000));
        }
        output.appendLine('Use Refresh Last Analysis to resume. The job may continue on the server.');
      }catch(error){if(!cancellation.isCancellationRequested)throw error;}
      finally{listener.dispose();await cancelResult;}
    });
  }
  command('mdt.connect',connect);
  command('mdt.disconnect',async()=>{++epoch;await serialize(async()=>{await context.secrets.delete('mdt.web.connection');await context.workspaceState.update('mdt.web.lastJob',undefined);clear();});});
  command('mdt.analyzeRepository',analyze);
  command('mdt.analyzeStaged',()=>{throw new Error('Staged Git analysis requires a trusted desktop Git workspace. Use MDT: Analyze Repository Revision in browser mode.');});
  command('mdt.analyzeWorking',()=>{throw new Error('Working-tree analysis requires a trusted desktop Git workspace. Use MDT: Analyze Repository Revision in browser mode.');});
  command('mdt.refreshLastAnalysis',async()=>{const active=await session();return refresh(active,await savedJob(active));});
  command('mdt.openLastAnalysis',async()=>{const active=await session();return open(active,await savedJob(active));});
  command('mdt.showFindings',()=>vscode.commands.executeCommand('mdt.findings.focus'));
  context.subscriptions.push(vscode.workspace.onDidChangeConfiguration(event=>{if(!changingSettings&&(event.affectsConfiguration('mdt.apiUrl')||event.affectsConfiguration('mdt.webUrl'))){++epoch;clear();}}));
  return {getRuntime:()=> 'web',getViewState:()=>({status:currentJob?.status||'idle',text:status.text,roots:resultTree(currentJob).map(item=>item.label)})};
}
module.exports={activate};
