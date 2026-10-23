import test from 'node:test';
import assert from 'node:assert/strict';
import { groupRelations, relationDescription } from '../src/utils/graphRelations.js';
import { edgeLabel } from '../src/utils/graphLayout.js';

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
