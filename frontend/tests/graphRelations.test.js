import test from 'node:test';
import assert from 'node:assert/strict';
import { groupRelations, relationDescription, endpointRoutes, edgeBadgeLines } from '../src/utils/graphRelations.js';
import { edgeLabel, edgeBadgeMetrics } from '../src/utils/graphLayout.js';

test('connection view preserves endpoint, method and provenance records without changing the snapshot', () => {
  const edges = [
    {from:'checkout',to:'account',type:'http',method:'GET',endpoint:'/users/1',evidence_kind:'source_inferred'},
    {from:'checkout',to:'account',type:'http',method:'POST',endpoint:'/users/1',evidence_kind:'source_inferred'},
    {from:'checkout',to:'account',type:'startup',evidence_kind:'compose_startup_order'},
    {from:'account',to:'checkout',type:'http',endpoint:'/status'},
  ];
  const original=JSON.stringify(edges), grouped=groupRelations(edges);
  assert.equal(grouped.length,2);
  assert.deepEqual(grouped[0].relations,edges.slice(0,3));
  assert.equal(grouped[1],edges[3]);
  assert.equal(grouped[0].endpoint,undefined);
  assert.equal(edgeLabel(grouped[0]),'3 relations');
  assert.match(relationDescription(edges[0]),/GET http: \/users\/1/);
  assert.equal(JSON.stringify(edges),original);
});

test('connection grouping retains self loops, unresolved evidence, broken records and arbitrary names', () => {
  const grouped=groupRelations([
    {from:'a->b',to:'c',type:'startup'}, {from:'a',to:'b->c',type:'http'},
    {from:'self',to:'self',endpoint:'/one'}, {from:'self',to:'self',endpoint:'/two',has_bug:true},
  ]);
  assert.equal(grouped.length,3);
  assert.equal(grouped[2].relations.length,2);
  assert.equal(grouped[2].has_bug,true);
  assert.match(relationDescription(grouped[0]),/endpoint not observed/);
  assert.deepEqual(groupRelations([]),[]);
});

test('endpoint labels expose grouped methods and paths while retaining broken warnings', () => {
  const edges = [
    {from:'web',to:'api',type:'http',method:'GET',endpoint:'/users'},
    {from:'web',to:'api',type:'http',method:'POST',endpoint:'/users',has_bug:true},
    {from:'web',to:'api',type:'startup'},
  ];
  const original = JSON.stringify(edges), [connection] = groupRelations(edges);
  assert.deepEqual(edgeBadgeLines(connection), ['⚠ BROKEN LINK']);
  assert.deepEqual(endpointRoutes(connection), ['GET /users', 'POST /users']);
  assert.deepEqual(edgeBadgeLines(connection, true), ['⚠ BROKEN LINK', '3 relations', 'GET /users', 'POST /users']);
  assert.deepEqual(edgeBadgeLines({...edges[1]}, true), ['⚠ BROKEN LINK', 'POST /users']);
  assert.deepEqual(endpointRoutes({type:'startup'}), []);
  assert.deepEqual(endpointRoutes({endpoint:'   '}), []);
  assert.equal(JSON.stringify(edges), original);
});

test('long and numerous routes fit the reserved badge with remaining routes inspectable', () => {
  const relations = Array.from({length:5}, (_,i) => ({from:'a',to:'b',method:'GET',endpoint:`/route/${i}/` + 'long'.repeat(15)}));
  const [connection] = groupRelations([...relations, {...relations[0], source_file:'another.py'}]);
  const metrics = edgeBadgeMetrics({...connection, endpointLabels:true});
  assert.equal(metrics.lines[0], '6 relations');
  assert.equal(metrics.lines.at(-1), '+2 more routes');
  assert.equal(metrics.lines.length, 5);
  assert.ok(metrics.lines.every(line => line.length <= 34));
  assert.equal(endpointRoutes(connection).length, 5);
  assert.equal(connection.relations.length, 6);
  assert.ok(metrics.height >= metrics.lines.length * 16);
});
