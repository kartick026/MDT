const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
test('browser package has no passive browsing or remote script access',()=>{
  const manifest=JSON.parse(fs.readFileSync(path.join(__dirname,'../manifest.json'),'utf8'));
  assert.equal(manifest.manifest_version,3);
  assert.deepEqual(manifest.permissions,['activeTab','storage']);
  assert.equal(manifest.content_scripts,undefined);
  assert.equal(manifest.host_permissions,undefined);
  assert.match(manifest.content_security_policy.extension_pages,/script-src 'self'/);
  const html=fs.readFileSync(path.join(__dirname,'../popup.html'),'utf8');
  assert.doesNotMatch(html,/<script[^>]+src="https?:/);
});
