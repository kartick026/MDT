import test from 'node:test';
import assert from 'node:assert/strict';
import { groupGraphEdits, proposalGuide, explainPreview, relationDescription } from '../src/utils/remediation.js';

const finding = (type, service) => ({ type, services: [service] });
const moved = {
  before: { score: 89.573, raw_score: 315, weights: { bottleneck_service: 20 }, smells: { bottleneck_service: 1 } },
  after: { score: 89.573, raw_score: 315, smells: { bottleneck_service: 1 } },
  delta: { score_reduction: 0, raw_debt_reduction: 0 },
  findings: { resolved: [finding('God / Bottleneck Service', 'flagd')], introduced: [finding('God / Bottleneck Service', 'flagd_facade')] },
};

test('equal-score replacement findings explain the moved problem without declaring success', () => {
  const result = explainPreview(moved);
  assert.equal(result.outcome, 'unchanged');
  assert.equal(result.headline, 'No modeled improvement');
  assert.match(result.moved[0], /disappears on flagd but appears on flagd_facade/);
  assert.match(result.explanation, /weighted debt total unchanged/);
  assert.match(result.next, /reduce or distribute/);
  assert.equal(result.rawSummary, 'Weighted finding total: 315 → 315.');
});

test('unknown measurements, a no-op and rounded improvements have distinct explanations', () => {
  assert.equal(explainPreview({}).outcome, 'unknown');
  assert.equal(explainPreview({ delta: { score_reduction: '' } }).outcome, 'unknown');
  assert.match(explainPreview({ delta: { score_reduction: 0 } }).explanation, /did not change/);
  assert.match(explainPreview({ delta: { score_reduction: 0, raw_debt_reduction: 1 } }).headline, /rounds to zero/);
  assert.equal(explainPreview({ delta: { score_reduction: -1 } }).outcome, 'worse');
});

test('score explanation uses response weights and discloses newly introduced findings', () => {
  const result = explainPreview({ before: { raw_score: 60, weights: { test_rule: 30 }, smells: { test_rule: 2 } },
    after: { raw_score: 30, smells: { test_rule: 1 } }, delta: { score_reduction: 12 }, findings: { introduced: [finding('New problem', 'b')] } });
  assert.equal(result.outcome, 'improved');
  assert.equal(result.contributions[0].reduction, 30);
  assert.match(result.explanation, /Review the new problems/);
});

test('grouping retains distinct startup, protocol and endpoint evidence without mutating edits', () => {
  const edits = ['startup', 'http', 'grpc'].map(dependency_type => ({action:'remove_edge',from_service:'ad',to_service:'flagd',dependency_type}));
  edits.push({action:'remove_edge',from_service:'ad',to_service:'flagd',dependency_type:'http',endpoint:'/flags'});
  const original = structuredClone(edits), groups = groupGraphEdits(edits);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].count, 4);
  assert.equal(groups[0].variants.length, 4);
  assert.match(groups[0].variants.join(' '), /Startup order.*HTTP.*GRPC.*\/flags/);
  assert.deepEqual(edits, original);
  assert.equal(relationDescription(edits[0]).verb, 'waits for');
  assert.equal(relationDescription({dependency_type:'reference'}).verb, 'depends on');
});

test('node-property proposals do not collapse opposite resilience edits', () => {
  const edits = [true, false].map(has_circuit_breaker => ({ action:'update_node',from_service:'api',has_circuit_breaker }));
  assert.equal(groupGraphEdits(edits).length, 2);
});

test('intermediary proposals explain the actual route and concrete implementation steps', () => {
  const fix = { edits: [
    { action:'add_node', from_service:'flagd_facade' },
    { action:'remove_edge', from_service:'ad', to_service:'flagd', dependency_type:'startup' },
    { action:'add_edge', from_service:'ad', to_service:'flagd_facade' },
    { action:'add_edge', from_service:'flagd_facade', to_service:'flagd' },
  ] };
  const guide = proposalGuide(fix);
  assert.match(guide.summary, /between 1 service \(ad\) and flagd/);
  assert.match(guide.steps.join(' '), /does not create a service/);
  assert.match(guide.steps.join(' '), /Startup-order edits/);
  assert.match(guide.steps.join(' '), /contract and integration tests/);
});

test('legacy recommendations resolve a singular finding id for a meaningful title', () => {
  const guide = proposalGuide({ finding_id:'real', text:'Review responsibilities', edits:[] }, [{id:'real', type:'High Coupling'}]);
  assert.equal(guide.title, 'Explore a change for High Coupling');
  assert.equal(proposalGuide('Review the contract').title, 'Review the contract');
});

test('actual preview component renders a neutral verdict, named findings and collapsed details', async () => {
  const { createServer } = await import('vite');
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' });
  try {
    const { default: Preview, ProposedChange } = await server.ssrLoadModule('/src/components/RemediationPreview.jsx');
    const { renderToStaticMarkup } = await import('react-dom/server');
    const { createElement } = await import('react');
    const html = renderToStaticMarkup(createElement(Preview, { previewData: moved }));
    assert.match(html, /preview-unchanged/);
    assert.match(html, /No modeled improvement/);
    assert.match(html, /flagd_facade/);
    assert.match(html, /What to do next/);
    assert.doesNotMatch(html, /pulse-dot|reduction verified|<details open/);
    const plan = renderToStaticMarkup(createElement(ProposedChange, { fix: { edits: [
      { action:'remove_edge',from_service:'<script>alert(1)</script>',to_service:'flagd',dependency_type:'http',endpoint:'/flags' },
    ] } }));
    assert.doesNotMatch(plan, /<script>/);
    assert.match(plan, /endpoint|\/flags/);
    assert.match(plan, /What would I change in the actual project/);
  } finally { await server.close(); }
});
