const test=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');const vm=require('node:vm');
const MDTClient=require('../../../packages/client');
const defer=()=>{let resolve;const promise=new Promise(done=>resolve=done);return{promise,resolve};};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function popup(sendMessage,permission=true){
  const nodes=new Map();const get=id=>{if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',hidden:false,disabled:false,events:{},addEventListener(name,fn){this.events[name]=fn;},replaceChildren(){},append(){},removeAttribute(key){delete this[key];}});return nodes.get(id);};
  const timers=[];
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../popup.js'),'utf8'),{URL,MDTClient,crypto:require('node:crypto').webcrypto,document:{getElementById:get,createElement:()=>({})},setTimeout:(fn,delay)=>{timers.push({fn,delay});return timers.length;},clearTimeout(){},chrome:{runtime:{sendMessage},tabs:{query:async()=>[{url:'https://github.com/acme/repo'}]},permissions:{request:typeof permission==='function'?permission:async()=>permission}}});
  return{get,timers};
}
test('late popup polling response cannot restore results after disconnect',async()=>{
  const held=defer(),started=defer();
  const p=popup(async message=>{
    if(message.type==='state')return{ok:true,data:{connected:true,connectionId:'old',settings:{baseUrl:'https://api.example',webUrl:'https://web.example'},lastJob:{jobId:'j',projectId:'p'}}};
    if(message.type==='projects')return{ok:true,data:{projects:[{id:'p',name:'Repo',repo_url:'https://github.com/acme/repo'}]}};
    if(message.type==='job'){started.resolve();return held.promise;}
    return{ok:true,data:{disconnected:true}};
  });
  await started.promise;await p.get('disconnect').events.click();
  held.resolve({ok:true,data:{status:'running',result:{risk_score:50,explanation:'private result'}}});await tick();
  assert.equal(p.get('result').hidden,true);assert.equal(p.get('summary').textContent,'');assert.equal(p.get('open-web').href,undefined);assert.equal(p.timers.length,0);
});
test('denied API permission never sends the entered credential to the worker',async()=>{
  const calls=[];const p=popup(async message=>{calls.push(message);return{ok:true,data:{connected:false}};},false);await tick();
  p.get('api-url').value='https://api.example';p.get('web-url').value='https://web.example';p.get('token').value='secret-test';
  await p.get('connect-form').events.submit({preventDefault(){}});
  assert.equal(calls.some(message=>message.type==='connect'),false);assert.match(p.get('error').textContent,/not granted/);
});

function fillConnection(p) {
  p.get('api-url').value='https://api.example';
  p.get('web-url').value='https://web.example';
  p.get('token').value='secret-test';
}
test('pending permission is visible, rejects duplicate submits and offers recovery without sending a token',async()=>{
  const held=defer(),calls=[];let requests=0;
  const p=popup(async message=>{calls.push(message);return{ok:true,data:{connected:false}};},()=>{requests++;return held.promise;});await tick();fillConnection(p);
  const pending=p.get('connect-form').events.submit({preventDefault(){}});await tick();
  assert.match(p.get('status').textContent,/Waiting for browser permission for api.example/);
  assert.equal(p.get('connect-submit').disabled,true);assert.equal(p.get('cancel-connect').hidden,false);
  await p.get('connect-form').events.submit({preventDefault(){}});assert.equal(requests,1);
  p.timers.find(t=>t.delay===15000).fn();assert.match(p.get('error').textContent,/no prompt is visible/);
  assert.equal(calls.some(c=>c.type==='connect'),false);
  held.resolve(false);await pending;assert.equal(p.get('connect-submit').disabled,false);
});

test('cancelling a pending permission clears input and ignores a later grant',async()=>{
  const held=defer(),calls=[];
  const p=popup(async message=>{calls.push(message);return{ok:true,data:{connected:false}};},()=>held.promise);await tick();fillConnection(p);
  const pending=p.get('connect-form').events.submit({preventDefault(){}});await tick();
  await p.get('cancel-connect').events.click();
  assert.equal(p.get('token').value,'');assert.equal(p.get('connect-submit').disabled,false);
  assert.equal(p.get('cancel-connect').hidden,true);assert.match(p.get('status').textContent,/cancelled/);
  held.resolve(true);await pending;
  assert.equal(calls.some(c=>c.type==='connect'),false);assert.match(p.get('status').textContent,/cancelled/);
});

test('a granted permission connects once and clears the sensitive input',async()=>{
  const calls=[];const p=popup(async message=>{calls.push(message);return message.type==='connect'?{ok:true,data:{connectionId:'new',settings:{baseUrl:'https://api.example',webUrl:'https://web.example'},projects:[]}}:{ok:true,data:{connected:false}};});await tick();fillConnection(p);
  await p.get('connect-form').events.submit({preventDefault(){}});
  assert.equal(calls.filter(c=>c.type==='connect').length,1);assert.equal(p.get('token').value,'');
  assert.equal(p.get('connected').hidden,false);assert.equal(p.get('cancel-connect').hidden,true);
});

test('permission API rejection restores retry controls and reports the actual error',async()=>{
  const calls=[];const p=popup(async message=>{calls.push(message);return{ok:true,data:{connected:false}};},async()=>{throw new Error('Could not find an active window.');});await tick();fillConnection(p);
  await p.get('connect-form').events.submit({preventDefault(){}});
  assert.equal(calls.some(c=>c.type==='connect'),false);assert.match(p.get('error').textContent,/active window/);
  assert.equal(p.get('status').textContent,'Connection was not completed.');
  assert.equal(p.get('connect-submit').disabled,false);assert.equal(p.get('cancel-connect').hidden,true);
});
