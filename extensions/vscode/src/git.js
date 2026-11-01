'use strict';
const { execFile } = require('node:child_process');
const { promisify } = require('node:util');
const { isUtf8 } = require('node:buffer');
const fs = require('node:fs/promises');
const path = require('node:path');
const execute = promisify(execFile);
const MAX_FILES = 100;
const MAX_SOURCE_BYTES = 1024 * 1024;

async function git(cwd, args) {
  const result = await execute('git', ['-c', 'core.fsmonitor=false', ...args], { cwd, encoding: 'buffer', maxBuffer: 3 * MAX_SOURCE_BYTES, windowsHide: true, timeout: 15000 });
  return result.stdout;
}
function text(buffer, name) {
  if (buffer.includes(0) || !isUtf8(buffer)) throw new Error(`Cannot analyze binary or non-UTF-8 source: ${name}. Exclude it or use a committed revision analysis.`);
  return buffer.toString('utf8');
}
function inside(root, filename) {
  const target = path.resolve(root, filename);
  const relative = path.relative(root, target);
  if (!relative || relative.startsWith('..' + path.sep) || relative === '..' || path.isAbsolute(relative)) throw new Error(`Unsafe source path: ${filename}`);
  return target;
}
async function optionalGitContent(cwd, spec, name) {
  try { return text(await git(cwd, ['show', spec]), name); }
  catch (error) {
    // Missing files are legitimate on one side of an addition or deletion.
    if (error.stderr && /does not exist|exists on disk, but not in|not in the index|does not exist in/i.test(error.stderr.toString())) return undefined;
    throw error;
  }
}

async function collectChanges(folder, mode = 'staged') {
  if (!['staged', 'working'].includes(mode)) throw new Error('Unsupported change mode');
  const root = (await git(folder, ['rev-parse', '--show-toplevel'])).toString('utf8').trim();
  const realRoot = await fs.realpath(root);
  const base = (await git(root, ['rev-parse', '--verify', 'HEAD'])).toString('utf8').trim();
  const diffArgs = ['diff', '--no-ext-diff', '--no-textconv', '--no-renames', ...(mode === 'staged' ? ['--cached'] : []), 'HEAD'];
  const names = (await git(root, [...diffArgs, '--name-only', '-z', '--'])).toString('utf8').split('\0').filter(Boolean);
  if (!names.length) throw new Error('No tracked changes found. Stage new files first. Working mode reads saved files only.');
  if (names.length > MAX_FILES) throw new Error(`This alpha accepts at most ${MAX_FILES} changed files; found ${names.length}.`);
  // Git filenames are untrusted keys (including names such as __proto__).
  const before = Object.create(null);
  const after = Object.create(null);
  let totalBytes = 0;
  for (const name of names) {
    const target = inside(root, name);
    const oldContent = await optionalGitContent(root, `${base}:${name}`, name);
    let newContent;
    if (mode === 'staged') {
      const indexEntry = (await git(root, ['ls-files', '--stage', '--', name])).toString('utf8');
      if (indexEntry.startsWith('120000 ') || indexEntry.startsWith('160000 ')) throw new Error(`Symlinks and submodules require committed analysis: ${name}`);
      newContent = await optionalGitContent(root, `:${name}`, name);
    } else {
      try {
        const info = await fs.lstat(target);
        if (!info.isFile() || info.isSymbolicLink()) throw new Error(`Only regular source files can be uploaded: ${name}`);
        const resolved = await fs.realpath(target);
        inside(realRoot, path.relative(realRoot, resolved));
        newContent = text(await fs.readFile(target), name);
      } catch (error) { if (error.code !== 'ENOENT') throw error; }
    }
    if (oldContent !== undefined) before[name] = oldContent;
    if (newContent !== undefined) after[name] = newContent;
    totalBytes += Buffer.byteLength(oldContent || '') + Buffer.byteLength(newContent || '');
    if (totalBytes > MAX_SOURCE_BYTES) throw new Error('Changed source exceeds the 1 MiB alpha upload limit. Analyze a smaller change.');
  }
  const patch = text(await git(root, [...diffArgs, '--unified=3', '--']), 'diff');
  if (Buffer.byteLength(patch) > 2 * MAX_SOURCE_BYTES) throw new Error('Patch exceeds the 2 MiB limit.');
  let repoUrl = '';
  try { repoUrl = (await git(root, ['remote', 'get-url', 'origin'])).toString('utf8').trim().replace(/^git@github\.com:/, 'https://github.com/').replace(/\.git$/, ''); } catch { /* User can choose an owned project explicitly. */ }
  return { root, repoUrl, bytes: totalBytes, payload: { source: 'patch', base_ref: base, head_ref: base, changed_files: names, patch, before_files: before, after_files: after } };
}
module.exports = { collectChanges, inside, MAX_SOURCE_BYTES, MAX_FILES };
