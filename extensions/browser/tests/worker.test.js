const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

function storageArea(values={}) {
  return {values,async get(keys){const selected=typeof keys==='string'?[keys]:keys;return Object.fromEntries(selected.filter(key=>key in values).map(key=>[key,values[key]]));},async set(items){Object.assign(values,items);},async remove(keys){for(const key of typeof keys==='string'?[keys]:keys)delete values[key];},async clear(){for(const key of Object.keys(values))delete values[key];}};
}
function worker(storage,requests,onRequest) {
  let listener;
  const sandbox={URL,URLSearchParams,AbortController,setTimeout,clearTimeout,crypto:require('node:crypto').webcrypto,fetch:async(url,options)=>{
    requests.push({url,options});
    if(onRequest)await onRequest(url,options);
    const data=url.endsWith('/v1/projects')?{projects:[{id:'p1',name:'Example',repo_url:'https://github.com/acme/example',branch:'main',ready:true}]}:url.endsWith('/analyses')?{job_id:'j1',status:'queued'}:{job_id:'j1',status:'succeeded',result:{risk_score:12,architecture_smell_score:86.936}};
    return {ok:true,status:200,json:async()=>data};
  },chrome:{storage,runtime:{id:'extension',getURL:()=> 'chrome-extension://extension/',onMessage:{addListener(fn){listener=fn;}}}}};
  const context=vm.createContext(sandbox);
  sandbox.importScripts=()=>vm.runInContext(fs.readFileSync(path.join(__dirname,'../../../packages/client/index.js'),'utf8'),context);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../background.js'),'utf8'),context);
  return message=>new Promise(resolve=>listener(message,{id:'extension',url:'chrome-extension://extension/popup.html'},resolve));
}

test('service worker restart resumes the session job without persisting token locally',async()=>{
  const storage={local:storageArea(),session:storageArea()};
  const requests=[];
  let send=worker(storage,requests);
  const connected=await send({type:'connect',baseUrl:'https://mdt.example/api',webUrl:'https://web.example',token:'session-test-token'});
  assert.equal(connected.ok,true);
  const connectionId=connected.data.connectionId;
  assert.equal(connected.data.token,undefined);
  assert.equal(storage.local.values.token,undefined);
  const created=await send({type:'analyze',connectionId,url:'https://github.com/acme/example/pull/14',projectId:'p1',requestId:'test-request'});
  assert.equal(created.data.jobId,'j1');
  assert.equal(JSON.parse(requests.at(-1).options.body).pull_request,14);
  send=worker(storage,requests);
  assert.equal((await send({type:'state'})).data.lastJob.jobId,'j1');
  assert.equal((await send({type:'job',connectionId,jobId:'j1'})).data.status,'succeeded');
  await send({type:'disconnect'});
  assert.equal((await send({type:'state'})).data.connected,false);
  assert.equal(storage.session.values.lastJob,undefined);
});

test('project mismatch does not submit an analysis',async()=>{
  const storage={local:storageArea(),session:storageArea({connection:{id:'test-connection',baseUrl:'https://mdt.example',webUrl:'https://web.example',token:'test'}})};
  const requests=[];
  const send=worker(storage,requests);
  const response=await send({type:'analyze',connectionId:'test-connection',url:'https://github.com/acme/other/commit/1234567',projectId:'p1'});
  assert.equal(response.ok,false);
  assert.match(response.error,/does not match/);
  assert.equal(requests.filter(item=>item.options.method==='POST').length,0);
});

const deferred=()=>{let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};};
const connect=(send,host,token)=>send({type:'connect',baseUrl:`https://${host}.example`,webUrl:`https://${host}-web.example`,token});

test('connection snapshots ignore conflicting local defaults and reject stale popup requests',async()=>{
  const storage={local:storageArea(),session:storageArea()};const requests=[];const send=worker(storage,requests);
  const a=(await connect(send,'a','token-a')).data;
  await storage.local.set({settings:{baseUrl:'https://evil.example',webUrl:'https://evil.example'}});
  await send({type:'projects',connectionId:a.connectionId});
  assert.equal(requests.at(-1).url,'https://a.example/v1/projects');
  assert.equal(requests.at(-1).options.headers.Authorization,'Bearer token-a');
  const b=(await connect(send,'b','token-b')).data;
  const count=requests.length;
  assert.equal((await send({type:'cancel',jobId:'j1',connectionId:a.connectionId})).ok,false);
  assert.equal(requests.length,count);
  await send({type:'projects',connectionId:b.connectionId});
  assert.equal(requests.at(-1).options.headers.Authorization,'Bearer token-b');
  assert.equal(JSON.stringify((await send({type:'state'})).data).includes('token-b'),false);
});

test('late submission cancels on its original server without restoring a job',async()=>{
  const held=deferred(),started=deferred();const storage={local:storageArea(),session:storageArea()};const requests=[];
  const send=worker(storage,requests,async(url,options)=>{if(options.method==='POST'){started.resolve();await held.promise;}});
  const a=(await connect(send,'a','token-a')).data;
  const submit=send({type:'analyze',connectionId:a.connectionId,url:'https://github.com/acme/example',projectId:'p1'});
  await started.promise;await send({type:'disconnect'});await connect(send,'b','token-b');held.resolve();
  assert.equal((await submit).ok,false);
  const cancellation=requests.find(item=>item.options.method==='DELETE');
  assert.equal(cancellation.url,'https://a.example/v1/jobs/j1');
  assert.equal(cancellation.options.headers.Authorization,'Bearer token-a');
  const state=(await send({type:'state'})).data;
  assert.equal(state.settings.baseUrl,'https://b.example');assert.equal(state.lastJob,undefined);
});

test('disconnect invalidates a connection still being validated',async()=>{
  const held=deferred(),started=deferred();const storage={local:storageArea(),session:storageArea()};
  const send=worker(storage,[],async()=>{started.resolve();await held.promise;});
  const pending=connect(send,'a','token-a');await started.promise;
  await send({type:'disconnect'});held.resolve();
  assert.equal((await pending).ok,false);
  assert.equal((await send({type:'state'})).data.connected,false);
  assert.equal(storage.session.values.connection,undefined);
});

test('reconnect during a storage write rolls back before worker restart',async()=>{
  const storage={local:storageArea(),session:storageArea()};const send=worker(storage,[]);
  const a=(await connect(send,'a','token-a')).data;
  const original=storage.session.set;const held=deferred(),started=deferred();
  storage.session.set=async items=>{if(items.connection?.baseUrl==='https://b.example'){started.resolve();await held.promise;}await original(items);};
  const pending=connect(send,'b','token-b');await started.promise;
  assert.equal((await send({type:'connect',baseUrl:'http://unsafe.example',webUrl:'https://web.example',token:'invalid'})).ok,false);
  held.resolve();assert.equal((await pending).ok,false);
  const restarted=worker(storage,[]);
  assert.equal((await restarted({type:'state'})).data.connectionId,a.connectionId);
  assert.equal(storage.session.values.connection.token,'token-a');
});

test('legacy unbound credentials require reconnect instead of guessing their server',async()=>{
  const storage={local:storageArea({settings:{baseUrl:'https://a.example'}}),session:storageArea({token:'legacy',lastJob:{jobId:'old'}})};
  const send=worker(storage,[]);
  assert.equal((await send({type:'state'})).data.connected,false);
  assert.equal(storage.session.values.token,undefined);
  assert.equal((await send({type:'projects'})).ok,false);
});
