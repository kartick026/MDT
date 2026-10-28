import { NODE_H, getNodeWidth, edgeLabel, edgeBadgeMetrics, sectionGeometry } from './graphLayout.js';

export function layoutRequest(nodes, edges, direction = 'DOWN') {
  const ids = new Set(nodes.map(n=>n.id));
  const internalIds = new Map(nodes.map((n,index)=>[n.id,`node-${index}`]));
  const validEdges = edges.map((edge,index)=>({...edge,index})).filter(e=>ids.has(e.from)&&ids.has(e.to));
  return {
    id:'architecture',
    layoutOptions:{
      'elk.algorithm':'layered', 'elk.direction':direction, 'elk.edgeRouting':'ORTHOGONAL',
      'elk.padding':'[top=36,left=36,bottom=36,right=36]',
      'elk.spacing.nodeNode':'48', 'elk.spacing.edgeNode':'24', 'elk.spacing.edgeEdge':'16',
      'elk.layered.spacing.nodeNodeBetweenLayers':'100',
      'elk.layered.spacing.edgeNodeBetweenLayers':'28',
      'elk.layered.spacing.edgeEdgeBetweenLayers':'16',
      'elk.layered.crossingMinimization.strategy':'LAYER_SWEEP',
      'elk.layered.nodePlacement.strategy':'NETWORK_SIMPLEX',
      'elk.layered.mergeEdges':'false', 'elk.separateConnectedComponents':'true',
      'elk.randomSeed':'1',
    },
    children:nodes.map(n=>({id:internalIds.get(n.id),width:getNodeWidth(n.label||n.id),height:NODE_H})),
    edges:validEdges.map(e=>({id:`edge-${e.index}`,sources:[internalIds.get(e.from)],targets:[internalIds.get(e.to)],
      labels:edgeLabel(e) ? [{text:edgeLabel(e),width:edgeBadgeMetrics(e).width,height:edgeBadgeMetrics(e).height,
        layoutOptions:{'elk.edgeLabels.placement':'CENTER'}}] : []})),
  };
}

export function layoutResult(graph,nodes) {
  const positions=Object.fromEntries((graph.children||[]).map(n=>[nodes[Number(n.id.slice(5))].id,{x:n.x,y:n.y,w:n.width,h:n.height}]));
  const routes={};
  for(const edge of graph.edges||[]) {
    if(!edge.sections?.length) throw new Error('The layout engine returned an incomplete relation route.');
    routes[edge.id.slice(5)] = sectionGeometry(edge.sections[0],edge.labels?.[0]);
  }
  return {positions,routes,width:Math.max(graph.width||0,100),height:Math.max(graph.height||0,100)};
}
