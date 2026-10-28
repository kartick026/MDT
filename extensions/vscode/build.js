const fs=require('node:fs');
const path=require('node:path');
const output=path.join(__dirname,'dist');
fs.mkdirSync(output,{recursive:true});
for(const file of ['extension.js','git.js','results.js']) fs.copyFileSync(path.join(__dirname,'src',file),path.join(output,file));
fs.copyFileSync(path.join(__dirname,'../../packages/client/index.js'),path.join(output,'client.js'));
require('esbuild').buildSync({entryPoints:[path.join(__dirname,'src/web-extension.js')],outfile:path.join(output,'web-extension.js'),bundle:true,platform:'browser',format:'cjs',external:['vscode'],target:'es2022'});
console.log(`Built desktop and browser extension entries at ${output}`);
