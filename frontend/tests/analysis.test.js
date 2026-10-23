import test from 'node:test';
import assert from 'node:assert/strict';
import { formatScore, scoreDelta, evidenceSummary, analysisExport, readableExport, readRoute, routeHash, graphEditLabel, previewChange, architectureSummary, jobResult } from '../src/utils/analysis.js';
import { clearAnalysisSession, attachSession, rejectsCurrentSession } from '../src/utils/session.js';
import { AxiosHeaders } from 'axios';

test('debt precision survives formatting and export', () => {
  const scores = [86.936, 85.372, 83.384, 80.769, 77.178];
  assert.equal(new Set(scores.map(formatScore)).size, 5);
  assert.equal(formatScore(0), '0');
  assert.equal(formatScore(100), '100');
  assert.equal(formatScore(undefined), 'Unavailable');
  assert.equal(JSON.parse(analysisExport({ architecture_smell_score: 86.936 })).analysis.architecture_smell_score, 86.936);
});

test('counterfactual labels reflect the actual score direction and API edit fields', () => {
  assert.deepEqual(previewChange({delta:{score_reduction:-1.125}}), {text:'+1.125 pts',label:'Higher recorded debt',improved:false});
  assert.equal(previewChange({delta:{score_reduction:0}}).label, 'Debt unchanged');
  assert.equal(previewChange({delta:{score_reduction:2.001}}).text, '−2.001 pts');
  assert.equal(previewChange({}).text, 'Unavailable');
  assert.equal(graphEditLabel({action:'add_edge',from_service:'a',to_service:'b'}), '+ Edge: a → b');
  assert.equal(graphEditLabel({action:'add_node',from_service:'facade'}), '+ Node: facade');
});

test('historical comparisons keep missing measurements distinct from measured zero', () => {
  assert.equal(scoreDelta(null, 40), null);
  assert.equal(scoreDelta(40, undefined), null);
  assert.equal(scoreDelta('', 40), null);
  assert.equal(scoreDelta(40, 'invalid'), null);
  assert.equal(scoreDelta(40, 0), -40);
  assert.equal(scoreDelta(0, 40), 40);
  assert.equal(formatScore(scoreDelta(86.936, 85.372)), '-1.564');
});

test('missing and partial architecture scores never produce a reassuring low-debt assessment', () => {
  for (const value of [null, undefined, '', ' ', false, NaN, Infinity]) {
    assert.equal(formatScore(value), 'Unavailable');
    assert.equal(architectureSummary({architecture_smell_score:value}).tone,'neutral');
  }
  const result={architecture_health:{score:0,severity:'LOW',assessment_status:'insufficient_communication_evidence',
    evidence:{startup_relations:5,static_or_modeled_calls:0,configuration_relations:0,runtime_traffic_measured:false}}};
  assert.equal(architectureSummary(result).score,0);
  assert.equal(architectureSummary(result).insufficient,true);
  assert.equal(architectureSummary(result).tone,'neutral');
  assert.equal(evidenceSummary(result).partial,true);
  for (const format of ['html','md']) {
    assert.match(readableExport(result,format),/Insufficient communication evidence/);
    assert.match(readableExport(result,format),/zero does not establish/);
    assert.match(readableExport(result,format),/Startup relations/);
  }
  assert.equal(architectureSummary({architecture_health:{score:0,severity:'LOW',assessment_status:'modeled_graph'}}).tone,'success');
});

test('import results retain findings and correct project/job destinations without inventing commit risk', () => {
  const job={id:'import-job',project:'owned-project',result:{kind:'import',smells:[{id:'finding'}],
    project:{repo_url:'https://github.com/example/repo'},risk_score:null}};
  const result=jobResult(job);
  assert.equal(result.analysis_id,'import-job');
  assert.equal(result.project_id,'owned-project');
  assert.equal(result.smells,job.result.smells);
  assert.equal(result.risk_score,null);
  assert.equal(job.result.analysis_id,undefined);
  assert.equal(jobResult({}),null);
});

test('missing evidence never becomes a semantic or complete claim', () => {
  assert.equal(evidenceSummary({}).semantic, false);
  assert.match(evidenceSummary({}).mode, /not supplied/);
  assert.equal(evidenceSummary({ coverage: { partial: true } }).partial, true);
  assert.equal(evidenceSummary({ assessment_status: 'insufficient_evidence' }).partial, true);
  assert.match(readableExport({ confidence: 0, confidence_evidence: {kind:'evidence_completeness'}, assessment_status:'insufficient_evidence' }), /not prediction accuracy/);
});

test('links preserve project and job without allowing unknown tabs', () => {
  const route = { projectId: 'project a', jobId: 'job&b' };
  assert.deepEqual(readRoute(routeHash('workspace', route)), { tab: 'projects', ...route, view: 'summary' });
  assert.equal(readRoute('#/unknown').tab, 'projects');
  assert.equal(readRoute('#/graph?project=a').view, 'graph');
  assert.equal(readRoute('#/projects?view=unknown').view, 'summary');
  assert.deepEqual(readRoute(routeHash('projects', { ...route, view: 'findings' })), { tab:'projects', ...route, view:'findings' });
});

test('shareable reports escape repository-controlled markup and preserve score precision', () => {
  const result = { repo_url: '<script>alert(1)</script>', architecture_smell_score:86.936, smells:[{ type:'<img src=x onerror=alert(1)>', description:'[click](javascript:alert(1))',services:['a'] }], warnings:['<iframe src=x>'] };
  const html = readableExport(result,'html');
  assert.ok(!html.includes('<script>') && !html.includes('<img') && !html.includes('<iframe'));
  assert.ok(html.includes('&lt;script&gt;') && html.includes('86.936'));
  const md = readableExport(result,'md');
  assert.ok(!md.includes('[click]('));
  assert.ok(md.includes('86\\.936') && md.includes('&lt;script&gt;'));
});

test('logout clears only MDT session records', () => {
  const values = new Map([['mdt_cached_impact_analysis', 'private'], ['mdt_project', 'a'], ['other_app', 'keep']]);
  const storage = { get length() { return values.size; }, key: index => [...values.keys()][index], removeItem: key => values.delete(key) };
  clearAnalysisSession(storage);
  assert.deepEqual([...values], [['other_app', 'keep']]);
});

test('in-flight old sessions cannot revoke or clear a renewed session', () => {
  const logoutHeaders = new AxiosHeaders({ Authorization: 'Bearer previous' });
  attachSession(logoutHeaders, 'renewed');
  assert.equal(logoutHeaders.Authorization, 'Bearer previous');
  assert.equal(rejectsCurrentSession({ response: { status: 401 }, config: { headers: logoutHeaders } }, 'renewed'), false);
  const currentHeaders = attachSession(new AxiosHeaders(), 'renewed');
  assert.equal(rejectsCurrentSession({ response: { status: 401 }, config: { headers: currentHeaders } }, 'renewed'), true);
  assert.equal(rejectsCurrentSession({ response: { status: 401 } }, 'renewed'), false);
});
