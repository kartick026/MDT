// Group only the presentation. Every captured record remains available for inspection.
export function groupRelations(edges) {
  const pairs = new Map();
  for (const edge of edges) {
    const key = JSON.stringify([edge.from, edge.to]);
    if (!pairs.has(key)) pairs.set(key, []);
    pairs.get(key).push(edge);
  }
  return [...pairs.values()].map(relations => relations.length === 1 ? relations[0] : {
    from: relations[0].from, to: relations[0].to, type: 'multiple', relations,
    has_bug: relations.some(edge => edge.has_bug),
  });
}

export function relationDescription(edge) {
  if (edge.relations) return `${edge.relations.length} recorded relations`;
  return `${edge.method ? `${edge.method} ` : ''}${edge.type || 'unresolved'}: ${edge.endpoint || 'endpoint not observed'}`;
}

export function endpointRoutes(edge) {
  return [...new Set((edge.relations || [edge]).flatMap(relation => {
    const endpoint = typeof relation.endpoint === 'string' ? relation.endpoint.trim() : '';
    if (!endpoint) return [];
    return [`${relation.method ? `${relation.method.toUpperCase()} ` : ''}${endpoint}`];
  }))];
}

export function edgeBadgeLines(edge, showEndpoints = false) {
  const lines = [];
  if (edge.has_bug) lines.push('⚠ BROKEN LINK');
  if (edge.relations && (!edge.has_bug || showEndpoints)) lines.push(`${edge.relations.length} relations`);
  if (showEndpoints || (!edge.relations && !edge.has_bug)) {
    const routes = endpointRoutes(edge);
    lines.push(...routes.slice(0, 3));
    if (routes.length > 3) lines.push(`+${routes.length - 3} more routes`);
  }
  return lines.map(line => line.length > 34 ? `${line.slice(0, 31)}…` : line);
}
