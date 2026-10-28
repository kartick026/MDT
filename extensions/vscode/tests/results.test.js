const test = require('node:test');
const assert = require('node:assert/strict');
const { resultTree, statusText } = require('../src/results');
const { coverageSummary } = require('../../../packages/client');

test('tree presents canonical smells and exact source provenance without guessed lines', () => {
  const roots = resultTree({ status: 'succeeded', result: {
    risk_score: 12.125, architecture_smell_score: 86.936, partial_results: true,
    base_sha: 'base', commit_sha: 'head', snapshot_version: 'snapshot', warnings: ['parser coverage limited'],
    evidence: { mode: 'deterministic_snapshot', semantic_used: false, topology_source: 'repository' },
    smells: [{ type: 'CyclicDependency', severity: 'HIGH', services: ['a', 'b'], description: 'A cycle', evidence: { cycle: ['a', 'b', 'a'] } }],
    affected_files: [{ file_path: 'service.py', parser_coverage: 'python_ast', extraction_status: 'complete', contract_changes: { removed: [{ method: 'GET', path: '/orders' }] } }],
  } });
  assert.equal(roots[0].label, 'Commit risk: 12.125 / 100');
  assert.equal(roots[1].label, 'Architectural debt: 86.936 / 100');
  assert.match(roots[2].label, /Partial evidence/);
  assert.ok(roots[2].children.some(item => item.label === 'Base: base'));
  assert.ok(roots[2].children.some(item => item.label === 'Semantic retrieval: not used'));
  assert.equal(roots[3].children[0].label, 'CyclicDependency');
  assert.equal(roots[3].children[0].line, undefined);
  assert.ok(roots[4].children[0].children.some(item => item.label === 'removed: GET /orders'));
  assert.equal(roots[4].children[0].line, undefined);
});

test('status represents idle, active, and partial jobs without fabricated risk', () => {
  assert.equal(statusText(), '$(shield) MDT');
  assert.match(statusText({ status: 'running' }), /sync~spin.*running/);
  assert.match(statusText({ status: 'succeeded', result: { risk_score: 0, partial_results: true } }), /warning.*0 \/ 100/);
  assert.match(resultTree({ status: 'failed', error: 'Source unavailable' })[0].tooltip, /Source unavailable/);
});

test('editor evidence includes the architecture assessment even without the legacy partial flag', () => {
  const job={status:'succeeded',result:{risk_score:'',architecture_health:{score:0,assessment_status:'insufficient_communication_evidence',detector_version:'test-engine'}}};
  const tree=resultTree(job);
  assert.match(tree[0].label,/unavailable/);
  assert.match(tree[1].label,/0 \/ 100/);
  assert.match(tree[1].description,/insufficient communication evidence/);
  assert.match(tree[1].tooltip,/zero does not establish/);
  assert.equal(tree[2].icon,'warning');
  assert.match(statusText(job),/warning.*unavailable/);
});

test('editor tree shows three independent coverage dimensions supplied by the shared formatter', () => {
  const job = { status:'partial', result: { coverage: { candidate_files:161, files_read:100, source:'static_source', parsers:{ast:1,tree_sitter:52,heuristic:45,failed:2} } } };
  const tree = resultTree(job, coverageSummary(job.result));
  const indicators = tree[2].children.find(child => child.label === 'Coverage indicators').children;
  assert.ok(indicators.some(child => child.label.startsWith('Source scan: 100 / 161')));
  assert.ok(indicators.some(child => child.label.startsWith('Parser support: 53 / 100')));
  assert.ok(indicators.some(child => child.label === 'Runtime verification: Not measured'));
});
