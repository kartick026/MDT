const test = require('node:test');
const assert = require('node:assert/strict');
const { createClient, validateServerUrl, parseGitHubUrl, analysisPayload, resultSummary, webLink, errorMessage } = require('../index');

test('remote credentials require HTTPS and cannot be put into URLs', () => {
  assert.throws(() => validateServerUrl('http://example.com'), /HTTPS/);
  assert.throws(() => validateServerUrl('https://user:secret@example.com'), /credentials/);
  assert.equal(validateServerUrl('http://localhost:8000/'), 'http://localhost:8000');
});

test('expired sessions and HTML endpoints explain the next action', async () => {
  const expired = createClient({ baseUrl: 'https://mdt.example', fetchImpl: async () => ({ ok: false, status: 401, json: async () => ({ detail: 'Invalid token' }) }) });
  await assert.rejects(expired.projects(), error => /fresh MDT session token/.test(errorMessage(error)));
  const website = createClient({ baseUrl: 'https://mdt.example', fetchImpl: async () => ({ ok: true, status: 200, json: async () => { throw new SyntaxError('HTML'); } }) });
  await assert.rejects(website.projects(), /backend, not the web dashboard/);
});

test('job polling forwards cancellation to the request', async () => {
  const controller = new AbortController();
  controller.abort();
  const api = createClient({ baseUrl: 'https://mdt.example', fetchImpl: async (_, options) => {
    assert.equal(options.signal.aborted, true);
    throw Object.assign(new Error('Aborted'), { name: 'AbortError' });
  } });
  await assert.rejects(api.job('job-1', { signal: controller.signal }), /cancelled/);
});
test('GitHub contexts preserve real comparison and PR identity', () => {
  assert.equal(parseGitHubUrl('https://github.com/acme/service/pull/42/files').pull_request, 42);
  assert.deepEqual(analysisPayload(parseGitHubUrl('https://github.com/acme/service/compare/main...feature/a'), {repo_url:'https://github.com/acme/service'}), {source:'commit',base_ref:'main',head_ref:'feature/a',comparison_mode:'merge_base'});
  assert.throws(() => parseGitHubUrl('https://github.com.evil.test/acme/service'), /github/);
  assert.throws(() => parseGitHubUrl('https://github.com/acme/service/pull/99999999999999999999'), /unsupported/);
  assert.throws(() => analysisPayload(parseGitHubUrl('https://github.com/a/b'), {repo_url:'https://github.com/a/c'}), /match/);
});
test('requests carry auth and idempotency without allowing redirects', async () => {
  let observed;
  const api = createClient({baseUrl:'https://mdt.example/api',token:'private-token',fetchImpl:async (url,options) => { observed={url,options}; return {ok:true,status:202,json:async()=>({job_id:'j'})}; }});
  assert.deepEqual(await api.analyze('a/b',{source:'commit',head_ref:'main'},'request-1'), {job_id:'j'});
  assert.equal(observed.url,'https://mdt.example/api/v1/projects/a%2Fb/analyses');
  assert.equal(observed.options.headers.Authorization,'Bearer private-token');
  assert.equal(observed.options.headers['Idempotency-Key'],'request-1');
  assert.equal(observed.options.redirect,'error');
});
test('server errors remain actionable and precise scores survive summaries', async () => {
  const api=createClient({baseUrl:'https://mdt.example',fetchImpl:async()=>({ok:false,status:403,json:async()=>({detail:'Access denied'})})});
  await assert.rejects(api.projects(), error=>error.status===403 && error.message==='Access denied');
  assert.match(resultSummary({architecture_smell_score:86.936,risk_score:0,evidence:{mode:'deterministic_snapshot'}}), /86\.936/);
  assert.equal(webLink('https://mdt.example','p a','j&b'),'https://mdt.example/#/workspace?project=p+a&job=j%26b');
});

test('client summaries preserve insufficient architecture evidence and distinguish missing scores from zero', () => {
  const text=resultSummary({risk_score:'',architecture_health:{score:0,assessment_status:'insufficient_communication_evidence'}});
  assert.match(text,/Commit risk: unavailable/);
  assert.match(text,/Architectural debt: 0/);
  assert.match(text,/insufficient communication evidence/);
  assert.match(text,/Partial coverage/);
  assert.match(text,/zero does not establish/);
});
