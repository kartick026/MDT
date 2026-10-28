import ELK from 'elkjs/lib/elk.bundled.js';
import { layoutRequest, layoutResult } from './graphLayoutPlan.js';
const engine=new ELK({algorithms:['layered']});
export async function layoutGraph(nodes,edges,direction) {
  return layoutResult(await engine.layout(layoutRequest(nodes,edges,direction)),nodes);
}
