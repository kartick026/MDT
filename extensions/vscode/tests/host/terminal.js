'use strict';
const assert = require('node:assert/strict');
const MDT = require('../../../../packages/client');

function terminalResult(job) {
  if (!MDT.isTerminal(job.status)) return undefined;
  return {
    jobStatus: job.status,
    hasResult: !!job.result && typeof job.result === 'object',
    riskScore: job.result?.risk_score ?? null,
    partialResults: job.result?.partial_results ?? null,
  };
}

function assertAnalyzed(run) {
  assert.ok(['succeeded', 'completed', 'partial'].includes(run.jobStatus),
    `Approved source did not produce an analysis: ${run.jobStatus}`);
  assert.equal(run.hasResult, true, 'A completed analysis must include its actual result');
  if (run.jobStatus === 'partial') assert.equal(run.partialResults, true,
    'A partial job must retain its limited-evidence flag');
}

module.exports = { terminalResult, assertAnalyzed };
