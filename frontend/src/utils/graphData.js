// Preserve the captured topology. Only explicit issue evidence marks a target red;
// a normal external service has unknown health, not an assumed outage.
export function snapshotGraph(snapshot) {
  const nodes = (snapshot.services || []).map(service => ({ ...service,
    id: service.name, label: service.name, risk_level: 'UNKNOWN', type: service.node_type || 'service' }));
  const broken = new Map(nodes.filter(node => node.is_broken === true).map(node => [node.id, node]));
  const edges = (snapshot.dependencies || []).map(edge => edge.has_bug || !broken.has(edge.to) ? edge : {
    ...edge, has_bug: true, resolution_reason: broken.get(edge.to).resolution_reason,
  });
  return { nodes, edges };
}
