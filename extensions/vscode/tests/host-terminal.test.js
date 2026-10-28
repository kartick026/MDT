const test = require('node:test');
const assert = require('node:assert/strict');
const { terminalResult, assertAnalyzed } = require('./host/terminal');

test('native acceptance completes on a real partial result while preserving missing scores', () => {
  const result = terminalResult({ status: 'partial', result: { partial_results: true, risk_score: null } });
  assert.equal(result.jobStatus, 'partial');
  assert.equal(result.riskScore, null);
  assert.doesNotThrow(() => assertAnalyzed(result));
  assert.equal(terminalResult({ status: 'running' }), undefined);
  for (const status of ['completed', 'succeeded']) {
    assert.doesNotThrow(() => assertAnalyzed(terminalResult({ status, result: {} })));
  }
});

test('native acceptance stops on failed or cancelled jobs and refuses absent or inconsistent results', () => {
  for (const status of ['failed', 'cancelled']) {
    const result = terminalResult({ status });
    assert.equal(result.jobStatus, status);
    assert.throws(() => assertAnalyzed(result), /did not produce an analysis/);
  }
  assert.throws(() => assertAnalyzed(terminalResult({ status: 'succeeded' })), /actual result/);
  assert.throws(() => assertAnalyzed(terminalResult({ status: 'partial', result: {} })), /limited-evidence flag/);
});
