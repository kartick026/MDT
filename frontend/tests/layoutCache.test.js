import test from 'node:test';
import assert from 'node:assert/strict';
import { createLayoutCache } from '../src/utils/layoutCache.js';

test('completed graph layouts reuse geometry and evict the least recently used entry', () => {
  const cache = createLayoutCache(2);
  const geometry = {positions: {a: {x: 0, y: 0}}, routes: {}};
  cache.set('down', geometry);
  cache.set('right', {positions: {}});
  assert.equal(cache.get('down'), geometry);
  cache.set('different-topology', {});
  assert.equal(cache.get('right'), undefined);
  assert.equal(cache.get('down'), geometry);
  assert.equal(cache.get('missing'), undefined);
});
