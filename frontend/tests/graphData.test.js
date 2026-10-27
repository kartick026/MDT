import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { snapshotGraph } from '../src/utils/graphData.js';
import { groupRelations } from '../src/utils/graphRelations.js';
import { layoutGraph } from '../src/utils/graphLayoutEngine.js';

test('demo broken target and incoming connection survive the real graph adapter and layout', async () => {
  const demo = JSON.parse(await readFile(new URL('../public/demo.json', import.meta.url), 'utf8'));
  const graph = snapshotGraph(demo.snapshot);
  const missing = graph.nodes.find(node => node.id === 'inventory-service');
  assert.equal(missing.is_broken, true);
  assert.match(missing.resolution_reason, /Illustrative/);
  const broken = graph.edges.find(edge => edge.from === 'order-service' && edge.to === 'inventory-service');
  assert.equal(broken.has_bug, true);
  for (const direction of ['DOWN', 'RIGHT']) {
    const grouped = groupRelations(graph.edges);
    const layout = await layoutGraph(graph.nodes, grouped, direction);
    assert.ok(layout.positions['inventory-service']);
    const route = layout.routes[grouped.findIndex(edge => edge === broken)];
    assert.ok(route.path);
  }
});

test('external resources remain unobserved unless explicit unresolved evidence exists', () => {
  const snapshot = { services: [{ name:'api' }, { name:'external-provider', node_type:'external' }],
    dependencies: [{from:'api',to:'external-provider',type:'https'}] };
  const copy = structuredClone(snapshot), graph = snapshotGraph(snapshot);
  assert.ok(!graph.nodes[1].is_broken);
  assert.ok(!graph.edges[0].has_bug);
  assert.equal(graph.nodes[1].risk_level, 'UNKNOWN');
  assert.deepEqual(snapshot, copy);
});
