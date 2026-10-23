const test=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');const vm=require('node:vm');
const MDTClient=require('../../../packages/client');
const defer=()=>{let resolve;const promise=new Promise(done=>resolve=done);return{promise,resolve};};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function popup(sendMessage,permission=true){
  const nodes=new Map();const get=id=>{if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',hidden:false,disabled:false,events:{},addEventListener(name,fn){this.events[name]=fn;},replaceChildren(){},append(){},removeAttribute(key){delete this[key];}});return nodes.get(id);};
  const timers=[];
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../popup.js'),'utf8'),{URL,MDTClient,crypto:require('node:crypto').webcrypto,document:{getElementById:get,createElement:()=>({})},setTimeout:(fn,delay)=>{timers.push({fn,delay});return timers.length;},clearTimeout(){},chrome:{runtime:{sendMessage},tabs:{query:async()=>[{url:'https://github.com/acme/repo'}]},permissions:{request:async()=>permission}}});
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
