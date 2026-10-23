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
