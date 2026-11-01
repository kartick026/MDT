import ELK from 'elkjs/lib/elk-api.js';
import workerUrl from 'elkjs/lib/elk-worker.min.js?url';
import { layoutRequest, layoutResult } from './graphLayoutPlan.js';
import { createLayoutCache } from './layoutCache.js';

const completedLayouts = createLayoutCache();

// ELK's official worker entry must own its worker message protocol. Nesting its
// bundled fake-worker implementation inside another worker breaks that protocol.
export function startLayout(nodes, edges, direction) {
  const request = layoutRequest(nodes, edges, direction);
  const key = JSON.stringify([nodes.map(node => node.id), request]);
  const cached = completedLayouts.get(key);
  if (cached) return {result: Promise.resolve(cached), terminate() {}};
  const engine = new ELK({ workerUrl, algorithms:['layered'] });
  return {result:engine.layout(request).then(graph => {
      const result = layoutResult(graph,nodes);
      completedLayouts.set(key, result);
      return result;
    }),
    terminate:()=>engine.terminateWorker()};
}
