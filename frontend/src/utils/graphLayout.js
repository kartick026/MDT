import { edgeBadgeLines } from './graphRelations.js';

export const NODE_W = 190, NODE_H = 64;

export function getNodeWidth(label) {
  return Math.min(300, Math.max(NODE_W, 65 + String(label || '').length * 7.2));
}

export function edgeLabel(edge) {
  return edgeBadgeLines(edge, edge.endpointLabels).join('\n');
}

export function edgeBadgeMetrics(edge) {
  const lines = edgeBadgeLines(edge, edge.endpointLabels);
  return { lines, width: Math.max(0, ...lines.map(line => line.length)) * 6.8 + 20,
    height: Math.max(24, lines.length * 16 + 8) };
}

// Share the engine's routed geometry and reserved label rectangle between
// the line and badge; neither is recomputed by the rendering components.
export function sectionGeometry(section, label) {
  const points = [section.startPoint, ...(section.bendPoints || []), section.endPoint];
  const lengths = points.slice(1).map((p, i) => Math.hypot(p.x-points[i].x, p.y-points[i].y));
  let distance = lengths.reduce((a,b) => a+b,0) / 2;
  let mid = points[0];
  for (let i=0;i<lengths.length;i++) {
    if (distance <= lengths[i]) {
      const t = lengths[i] ? distance/lengths[i] : 0;
      mid = {x:points[i].x+(points[i+1].x-points[i].x)*t,y:points[i].y+(points[i+1].y-points[i].y)*t};
      break;
    }
    distance -= lengths[i];
  }
  const end = points.at(-1), previous = points.at(-2);
  return {points, path:points.map((p,i)=>`${i?'L':'M'} ${p.x} ${p.y}`).join(' '),
    start:points[0],end,mid,label,
    badgePoint:label ? {x:label.x+label.width/2,y:label.y+label.height/2} : mid,
    tangentAngle:Math.atan2(end.y-previous.y,end.x-previous.x)};
}

export function fitGraph(width, height, viewportWidth, viewportHeight) {
  return Math.max(0.05, Math.min(1, (viewportWidth-24)/Math.max(width,1), (viewportHeight-24)/Math.max(height,1)));
}
