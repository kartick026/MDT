import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { layoutGraph } from '../src/utils/graphLayoutEngine.js';
import { fitGraph } from '../src/utils/graphLayout.js';
import { groupRelations } from '../src/utils/graphRelations.js';

const intersects = (a,b) => a.x < b.x+b.w-0.01 && a.x+a.w > b.x+0.01 && a.y < b.y+b.h-0.01 && a.y+a.h > b.y+0.01;

function verify(layout,nodes,edges) {
  const boxes=Object.values(layout.positions);
  assert.equal(boxes.length,nodes.length);
  assert.ok(boxes.every(p=>Object.values(p).every(Number.isFinite)));
  for(let i=0;i<boxes.length;i++) for(let j=i+1;j<boxes.length;j++) assert.ok(!intersects(boxes[i],boxes[j]),'node rectangles intersect');
  let count=0;
  edges.forEach((edge,index)=>{
    if(!layout.positions[edge.from] || !layout.positions[edge.to]) return;
    count++;
    const route=layout.routes[index];assert.ok(route,'every valid edge has a route');
    assert.ok(!/NaN|Infinity/.test(route.path));
    for(const [i,a] of route.points.entries()) {
      assert.ok(a.x>=0 && a.y>=0 && a.x<=layout.width+0.01 && a.y<=layout.height+0.01,'route is within canvas');
      if(i===0) continue;
      const b=route.points[i-1];
      assert.ok(Math.abs(a.x-b.x)<0.01 || Math.abs(a.y-b.y)<0.01,'orthogonal segment');
      for(const [id,node] of Object.entries(layout.positions)) {
        // Interior check includes source and destination: routes must leave and
        // enter their borders, never cut through any service's card.
        const segment={x:Math.min(a.x,b.x),y:Math.min(a.y,b.y),w:Math.max(Math.abs(a.x-b.x),0.001),h:Math.max(Math.abs(a.y-b.y),0.001)};
        assert.ok(!intersects(segment,node),`edge ${index} crosses node ${id}`);
      }
    }
    if(route.label) {
      const label={...route.label,w:route.label.width,h:route.label.height};
      assert.ok(boxes.every(node=>!intersects(label,node)),'endpoint badge intersects node');
    }
  });
  assert.equal(Object.keys(layout.routes).length,count);
  const labels=Object.values(layout.routes).filter(r=>r.label).map(r=>({...r.label,w:r.label.width,h:r.label.height}));
  for(let i=0;i<labels.length;i++)for(let j=i+1;j<labels.length;j++) assert.ok(!intersects(labels[i],labels[j]),'endpoint badges overlap each other');
}

function routeCrossings(layout) {
  const lines=Object.entries(layout.routes).flatMap(([id,r])=>r.points.slice(1).map((p,i)=>({id,a:r.points[i],b:p})));
  let overlaps=0,crossings=0;
  for(let i=0;i<lines.length;i++)for(let j=i+1;j<lines.length;j++) {
    const a=lines[i],b=lines[j];if(a.id===b.id)continue;
    const av=a.a.x===a.b.x,bv=b.a.x===b.b.x;
    if(av===bv) {
      const c=av?'x':'y',d=av?'y':'x';
      if(Math.abs(a.a[c]-b.a[c])<0.01 && Math.min(Math.max(a.a[d],a.b[d]),Math.max(b.a[d],b.b[d]))-Math.max(Math.min(a.a[d],a.b[d]),Math.min(b.a[d],b.b[d]))>0.01)overlaps++;
    } else {
      const v=av?a:b,h=av?b:a;
      if(v.a.x>Math.min(h.a.x,h.b.x)&&v.a.x<Math.max(h.a.x,h.b.x)&&h.a.y>Math.min(v.a.y,v.b.y)&&h.a.y<Math.max(v.a.y,v.b.y))crossings++;
    }
  }
  return {overlapping_edge_segments:overlaps,edge_crossings:crossings};
}

test('renaming services leaves geometry unchanged, including reverse edges, loops and parallel relations', async()=>{
  const nodes=['user-service','order-service','notification-service'].map(id=>({id,label:'same width'}));
  const edges=[{from:nodes[0].id,to:nodes[1].id},{from:nodes[1].id,to:nodes[0].id},{from:nodes[1].id,to:nodes[1].id},
    {from:nodes[1].id,to:nodes[2].id,endpoint:'/long/endpoint'},{from:nodes[1].id,to:nodes[2].id,endpoint:'/another'}];
  const layout=await layoutGraph(nodes,edges);verify(layout,nodes,edges);
  const renamed=nodes.map((n,i)=>({...n,id:`renamed-${i}`}));
  const mapped=edges.map(e=>({...e,from:renamed[nodes.findIndex(n=>n.id===e.from)].id,to:renamed[nodes.findIndex(n=>n.id===e.to)].id}));
  const second=await layoutGraph(renamed,mapped);verify(second,renamed,mapped);
  nodes.forEach((n,i)=>assert.deepEqual(layout.positions[n.id],second.positions[renamed[i].id]));
  assert.deepEqual(layout.routes,second.routes);
  assert.notEqual(layout.routes[3].path,layout.routes[4].path,'parallel relations have distinct ports/routes');
});

test('60 cyclic, disconnected and long-name nodes have obstacle-avoiding routes',async()=>{
  const nodes=Array.from({length:60},(_,i)=>({id:`node-${i}`,label:'An unusually long service name'}));
  const edges=nodes.slice(0,20).map((n,i)=>({from:n.id,to:nodes[(i+1)%20].id}));
  const layout=await layoutGraph(nodes,edges);verify(layout,nodes,edges);
});

test('empty, isolated and dangling-input graphs stay finite without fabricated relations',async()=>{
  verify(await layoutGraph([],[]),[],[]);
  const nodes=[{id:'architecture'},{id:'edge-0'}];
  const edges=[{from:'architecture',to:'missing'}];
  verify(await layoutGraph(nodes,edges),nodes,edges);
});

test('fit uses both viewport dimensions and never upscales a small graph',()=>{
  assert.equal(fitGraph(1000,2000,1024,624),0.3);
  assert.equal(fitGraph(100,100,1024,624),1);
  assert.ok(Number.isFinite(fitGraph(0,0,0,0)));
});

test('saved live repository graphs and demo keep nodes, routes and labels separate in both directions',async()=>{
  const live=JSON.parse(await readFile(new URL('../../docs/benchmarks/live-website-2026-10-21.json',import.meta.url),'utf8'));
  const demo=JSON.parse(await readFile(new URL('../public/demo.json',import.meta.url),'utf8'));
  const graphs=[...live.results.filter(r=>r.nodes!=null).map(r=>({name:r.repo,graph:r.graph})),{name:'MDT recorded demo',graph:demo.snapshot}];
  const results=[];
  for(const {name,graph} of graphs) {
    const nodes=graph.services.map(s=>({id:s.name,label:s.name})),edges=graph.dependencies;
    for(const direction of ['DOWN','RIGHT']) {
      const start=performance.now();
      const layout=await layoutGraph(nodes,edges,direction);verify(layout,nodes,edges);
      const crossings=routeCrossings(layout);
      assert.equal(crossings.overlapping_edge_segments,0,`${name} has shared overlapping routes`);
      results.push({name,direction,nodes:nodes.length,edges:edges.length,width:layout.width,height:layout.height,
        layout_ms:Math.round(performance.now()-start),node_overlaps:0,edge_node_intersections:0,label_node_intersections:0,...crossings});
    }
  }
  const folder=new URL('../../scratch/graph-ui-2026-10-21/',import.meta.url);
  await mkdir(folder,{recursive:true});
  await writeFile(new URL('layout-checks.json',folder),JSON.stringify(results,null,2));
});

test('updated repository topologies remain separated in connection and individual-relation views', async () => {
  const replay=JSON.parse(await readFile(new URL('../../docs/benchmarks/backend-evidence-2026-10-22.json',import.meta.url),'utf8'));
  const demo=JSON.parse(await readFile(new URL('../public/demo.json',import.meta.url),'utf8'));
  const graphs=[...replay.results.filter(r=>r.graph).map(r=>({name:r.repo,graph:r.graph})),{name:'MDT recorded demo',graph:demo.snapshot}];
  const results=[];
  for (const {name,graph} of graphs) {
    const nodes=graph.services.map(s=>({id:s.name,label:s.name}));
    for (const mode of ['connections','relations']) for (const direction of ['DOWN','RIGHT']) {
      const edges=mode==='connections' ? groupRelations(graph.dependencies) : graph.dependencies;
      const start=performance.now(),layout=await layoutGraph(nodes,edges,direction);
      verify(layout,nodes,edges);
      results.push({name,mode,direction,nodes:nodes.length,relations:graph.dependencies.length,drawn_edges:edges.length,
        layout_ms:Math.round(performance.now()-start),node_overlaps:0,edge_node_intersections:0,label_node_intersections:0,...routeCrossings(layout)});
    }
  }
  const folder=new URL('../../scratch/graph-completion-2026-10-23/',import.meta.url);
  await mkdir(folder,{recursive:true});
  await writeFile(new URL('layout-checks.json',folder),JSON.stringify(results,null,2));
});
