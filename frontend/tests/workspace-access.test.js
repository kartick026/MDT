import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { canManageProjects } from '../src/utils/access.js';

test('project creation is available to analysts and admins, not read-only or unknown roles', () => {
  assert.equal(canManageProjects({role:'analyst'}),true);
  assert.equal(canManageProjects({role:'admin'}),true);
  for (const user of [null,{}, {role:'viewer'}, {role:'unknown'}]) assert.equal(canManageProjects(user),false);
});

test('actual workspace shows creation for analysts and a clear read-only state for viewers', async () => {
  const { createServer } = await import('vite');
  const server = await createServer({server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
  const previousLocation = globalThis.location;
  globalThis.location = {hash:'#/projects'};
  try {
    const {default: Workspace} = await server.ssrLoadModule('/src/components/Workspace.jsx');
    const {AuthContext} = await server.ssrLoadModule('/src/context/useAuth.js');
    const render = role => renderToStaticMarkup(React.createElement(AuthContext.Provider,
      {value:{isAuthenticated:true,user:{username:'test-user',role}}},React.createElement(Workspace)));
    const viewer = render('viewer'), analyst = render('analyst');
    assert.match(viewer,/This account is read-only/);
    assert.doesNotMatch(viewer,/Create project/);
    assert.match(analyst,/Create project/);
    assert.doesNotMatch(analyst,/This account is read-only/);
  } finally {
    if (previousLocation === undefined) delete globalThis.location;
    else globalThis.location = previousLocation;
    await server.close();
  }
});
