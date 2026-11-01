import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { groupRelations } from '../src/utils/graphRelations.js';

test('actual SVG badges toggle grouped endpoints and preserve unresolved-target warnings', async () => {
  const { createServer } = await import('vite');
  const server = await createServer({ server: { middlewareMode:true, hmr:false, ws:false }, appType:'custom' });
  try {
    const { EdgeBadge } = await server.ssrLoadModule('/src/components/DependencyGraph.jsx');
    const [edge] = groupRelations([
      {from:'web',to:'api',method:'GET',endpoint:'/users'},
      {from:'web',to:'api',method:'POST',endpoint:'/users'},
    ]);
    const render = (value, enabled) => renderToStaticMarkup(React.createElement('svg', null,
      React.createElement(EdgeBadge, {edge:{...value,endpointLabels:enabled},edgeGeo:{badgePoint:{x:100,y:100}},showEndpoints:enabled})));
    const off = render(edge, false), on = render(edge, true), broken = render({...edge,has_bug:true}, true);
    assert.doesNotMatch(off, /<tspan[^>]*>GET \/users/);
    assert.match(on, /<tspan[^>]*>GET \/users/);
    assert.match(on, /<tspan[^>]*>POST \/users/);
    assert.match(broken, /⚠ BROKEN LINK/);
    assert.match(broken, /<tspan[^>]*>POST \/users/);
    assert.match(broken, /data-endpoint-labels="true"/);
    assert.equal(render({from:'a',to:'b',type:'startup'},false), '<svg></svg>');
  } finally { await server.close(); }
});
