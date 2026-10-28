const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const path=require('node:path');
const esbuild=require('esbuild');
const bundle=esbuild.buildSync({entryPoints:[path.join(__dirname,'../src/web-extension.js')],bundle:true,platform:'browser',format:'cjs',external:['vscode'],write:false,target:'es2022'}).outputFiles[0].text;
const defer=()=>{let resolve;const promise=new Promise(done=>resolve=done);return{promise,resolve};};
function harness({confirm=true,onFetch,onSecretGet}={}){
  const commands=new Map(),secrets=new Map(),state=new Map(),errors=[],requests=[],inputs=[],messages=[];
  const values={apiUrl:'https://api.example',webUrl:'https://web.example'};let configListener;
  const disposable={dispose(){}};
  const vscode={
    EventEmitter:class{event=()=>{};fire(){}dispose(){}},TreeItem:class{constructor(label){this.label=label;}},ThemeIcon:class{},
    TreeItemCollapsibleState:{None:0,Collapsed:1},StatusBarAlignment:{Left:1},ConfigurationTarget:{Global:1},ProgressLocation:{Notification:1},
    commands:{registerCommand(name,fn){commands.set(name,fn);return disposable;},async executeCommand(){}},
    workspace:{isTrusted:false,get fs(){throw new Error('Browser mode must not read workspace source');},getConfiguration(){return{get:key=>values[key],async update(key,value){values[key]=value;configListener?.({affectsConfiguration:name=>name===`mdt.${key}`});}};},onDidChangeConfiguration(fn){configListener=fn;return disposable;}},
    window:{createOutputChannel(){return{...disposable,clear(){},appendLine(value){messages.push(value);},show(){}};},createStatusBarItem(){return{...disposable,show(){}};},createTreeView(){return disposable;},async showInputBox(){return inputs.shift();},async showQuickPick(items){return items[0];},async showWarningMessage(...args){messages.push(args[0]);return confirm?args.at(-1):undefined;},async showInformationMessage(value){messages.push(value);},async showErrorMessage(value){errors.push(value);},async withProgress(_,fn){return fn({report(){}},{isCancellationRequested:false,onCancellationRequested(){return disposable;}});}},
    Uri:{parse:value=>value},env:{async openExternal(value){messages.push(value);}},
  };
  const context={subscriptions:[],secrets:{async get(key){if(onSecretGet)await onSecretGet();return secrets.get(key);},async store(k,v){secrets.set(k,v);},async delete(k){secrets.delete(k);}},workspaceState:{get:k=>state.get(k),async update(k,v){if(v===undefined)state.delete(k);else state.set(k,v);}}};
  const sandbox={module:{exports:{}},URL,URLSearchParams,AbortController,setTimeout,clearTimeout,crypto:require('node:crypto').webcrypto,require:name=>{assert.equal(name,'vscode','The web entry may only require the VS Code shim');return vscode;},fetch:async(url,options)=>{
    requests.push({url,options});if(onFetch)await onFetch(url,options);
    const data=url.endsWith('/projects')?{projects:[{id:'p',name:'Project',repo_url:'https://github.com/acme/repo',branch:'main',ready:true,snapshot_version:'snap'}]}:url.endsWith('/analyses')?{job_id:'j',status:'queued'}:{status:'succeeded',result:{risk_score:12,architecture_smell_score:88.125,evidence:{mode:'deterministic_snapshot'},smells:[]}};
    return{status:200,ok:true,json:async()=>data};
  }};
  vm.runInNewContext(bundle,sandbox);const api=sandbox.module.exports.activate(context);
  return{commands,inputs,errors,requests,secrets,state,values,api,async connect(host='api'){inputs.push(`https://${host}.example`,'https://web.example','test-session');await commands.get('mdt.connect')();}};
}

test('web bundle activates with no Node globals and sends only confirmed revision identifiers',async()=>{
  const h=harness();await h.connect();
  h.inputs.push('https://github.com/acme/repo/commit/abcdef0');await h.commands.get('mdt.analyzeRepository')();
  assert.deepEqual(h.errors,[]);
  const payload=JSON.parse(h.requests.find(r=>r.options.method==='POST').options.body);
  assert.deepEqual(payload,{source:'commit',head_ref:'abcdef0',snapshot_version:'snap'});
  assert.equal(h.api.getViewState().status,'succeeded');
  await h.commands.get('mdt.analyzeStaged')();assert.match(h.errors.at(-1),/requires a trusted desktop/);
});

test('denied confirmation and mismatched repository never submit source or analysis',async()=>{
  const h=harness({confirm:false});await h.connect();h.inputs.push('https://github.com/acme/repo');await h.commands.get('mdt.analyzeRepository')();
  assert.equal(h.requests.some(r=>r.options.method==='POST'),false);
  h.inputs.push('https://github.com/acme/other');await h.commands.get('mdt.analyzeRepository')();
  assert.match(h.errors.at(-1),/does not match/);assert.equal(h.requests.some(r=>r.options.method==='POST'),false);
});

test('web disconnect during submission cancels original job and keeps saved evidence cleared',async()=>{
  const started=defer(),held=defer();const h=harness({onFetch:async(url,options)=>{if(options.method==='POST'){started.resolve();await held.promise;}}});
  await h.connect();h.inputs.push('https://github.com/acme/repo');const pending=h.commands.get('mdt.analyzeRepository')();await started.promise;
  await h.commands.get('mdt.disconnect')();await h.connect('other');held.resolve();await pending;
  assert.equal(h.requests.find(r=>r.options.method==='DELETE').url,'https://api.example/v1/jobs/j');
  assert.equal(h.state.get('mdt.web.lastJob'),undefined);assert.equal(h.api.getViewState().status,'idle');
  assert.match(h.errors.at(-1),/connection changed/);
});

test('configuration change during secret lookup cannot redirect the credential',async()=>{
  const started=defer(),held=defer();let gate=false;const h=harness({onSecretGet:async()=>{if(gate){started.resolve();await held.promise;}}});
  await h.connect();gate=true;const count=h.requests.length;
  const pending=h.commands.get('mdt.analyzeRepository')();await started.promise;h.values.apiUrl='https://other.example';held.resolve();await pending;
  assert.equal(h.requests.length,count);assert.match(h.errors.at(-1),/connection changed/);
});
