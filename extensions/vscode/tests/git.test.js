const test=require('node:test');
const assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const fs=require('node:fs/promises');
const os=require('node:os');
const path=require('node:path');
const {collectChanges,inside}=require('../src/git');

test('staged analysis reads index content even when the working file differs',async()=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'mdt-extension-test-'));
  const run=(...args)=>execFileSync('git',['-c','core.hooksPath=',...args],{cwd:root,stdio:'pipe',windowsHide:true});
  try {
    run('init'); run('config','user.name','MDT Test'); run('config','user.email','test@example.invalid');
    await fs.writeFile(path.join(root,'service.py'),'def before():\n    return 1\n'); run('add','.'); run('commit','-m','Fixture baseline');
    await fs.writeFile(path.join(root,'service.py'),'def staged():\n    return 2\n'); run('add','service.py');
    await fs.writeFile(path.join(root,'service.py'),'def working():\n    return 3\n');
    const staged=await collectChanges(root,'staged');
    assert.match(staged.payload.before_files['service.py'],/def before/);
    assert.match(staged.payload.after_files['service.py'],/def staged/);
    assert.doesNotMatch(staged.payload.after_files['service.py'],/working/);
    assert.match(staged.payload.base_ref,/^[0-9a-f]{40}$/);
    const working=await collectChanges(root,'working');
    assert.match(working.payload.after_files['service.py'],/def working/);
    await fs.writeFile(path.join(root,'new.py'),'print("new")\n'); run('add','new.py');
    const added=await collectChanges(root,'staged');
    assert.equal(added.payload.before_files['new.py'],undefined);
    assert.match(added.payload.after_files['new.py'],/new/);
    await fs.writeFile(path.join(root,'__proto__'),'untrusted filename\n'); run('add','__proto__');
    const unusual=await collectChanges(root,'staged');
    assert.equal(JSON.parse(JSON.stringify(unusual.payload)).after_files['__proto__'],'untrusted filename\n');
    run('rm','-f','service.py');
    const deleted=await collectChanges(root,'staged');
    assert.equal(deleted.payload.after_files['service.py'],undefined);
  } finally {
    const resolved=path.resolve(root);
    if(path.dirname(resolved)===path.resolve(os.tmpdir()) && path.basename(resolved).startsWith('mdt-extension-test-')) await fs.rm(resolved,{recursive:true,force:true});
  }
});
test('paths cannot escape the selected repository',()=>{
  assert.throws(()=>inside(path.resolve('fixture'),'../secret'),/Unsafe/);
});
