import { formatScore, numericScore } from './analysis.js';

const unique = values => [...new Set(values.filter(Boolean))];
const names = values => unique(values).join(', ');

export function relationDescription(edit) {
  const kind = String(edit.dependency_type || '').toLowerCase();
  if (kind === 'startup') return { label: 'Startup order', verb: 'waits for' };
  if (['http', 'https', 'grpc'].includes(kind)) return { label: kind.toUpperCase(), verb: 'calls' };
  if (['database', 'postgresql', 'postgres', 'mysql', 'mongodb', 'redis', 'sql'].includes(kind)) {
    return { label: kind, verb: 'accesses' };
  }
  return { label: kind || 'Dependency type unspecified', verb: 'depends on' };
}

// Group only for display. Keep every protocol/endpoint and the submitted edits intact.
export function groupGraphEdits(edits = []) {
  const groups = new Map();
  for (const edit of edits) {
    const key = JSON.stringify([edit.action, edit.from_service, edit.to_service,
      edit.has_circuit_breaker, edit.resilient, edit.node_type]);
    if (!groups.has(key)) groups.set(key, { ...edit, variants: [], count: 0 });
    const group = groups.get(key);
    group.count += 1;
    if (edit.action.endsWith('_edge')) {
      const relation = relationDescription(edit);
      const detail = `${relation.label} · ${edit.endpoint || 'endpoint not recorded'}`;
      if (!group.variants.includes(detail)) group.variants.push(detail);
    }
  }
  return [...groups.values()];
}

export function proposalGuide(fix = {}, findings = []) {
  if (typeof fix === 'string') return { title: fix, summary: '', steps: [], edits: [] };
  const edits = fix.edits || [];
  const linked = findings.find(f => f.id && (fix.finding_id === f.id || fix.finding_ids?.includes(f.id)));
  const nodes = edits.filter(e => e.action === 'add_node');
  const removed = edits.filter(e => e.action === 'remove_edge');
  const added = edits.filter(e => e.action === 'add_edge');
  const updated = edits.filter(e => e.action === 'update_node');
  const steps = [];
  let title = fix.title || (linked ? `Explore a change for ${linked.type}` : 'Explore a possible architecture change');
  let summary = fix.text || fix.description || '';
  if (nodes.length) {
    title = fix.title || `Try routing through ${names(nodes.map(e => e.from_service))}`;
    const routes = nodes.map(node => {
      const incoming = unique(added.filter(e => e.to_service === node.from_service).map(e => e.from_service));
      const outgoing = unique(added.filter(e => e.from_service === node.from_service).map(e => e.to_service));
      return incoming.length && outgoing.length
        ? `Introduce ${node.from_service} between ${incoming.length} service${incoming.length === 1 ? '' : 's'} (${incoming.slice(0, 4).join(', ')}${incoming.length > 4 ? ', …' : ''}) and ${names(outgoing)}.`
        : `Add ${node.from_service} to the modeled architecture.`;
    });
    summary = `${routes.join(' ')} The preview checks whether this reduces findings or moves them elsewhere.`;
    steps.push(`Define and implement the responsibility and API of ${names(nodes.map(e => e.from_service))}; adding a name to the graph does not create a service.`);
    steps.push('Update the affected callers and connection settings to use the proposed route. Preserve required endpoints and data access.');
  } else if (updated.length) {
    title = fix.title || `Test resilience changes for ${names(updated.map(e => e.from_service))}`;
    summary = 'Change the recorded resilience properties and recalculate findings. The preview does not install or verify runtime protection.';
    steps.push('Implement the proposed resilience settings in the service code or proxy, including timeouts, failure handling and recovery tests.');
  } else if (removed.length) {
    title = fix.title || `Test removing a dependency from ${names(removed.map(e => e.from_service))}`;
    steps.push(`Inspect why ${names(removed.map(e => e.from_service))} needs ${names(removed.map(e => e.to_service))}. Remove the dependency only after replacing or retiring the required behavior.`);
  } else if (added.length) {
    steps.push('Confirm the proposed dependency exists in the intended design, then implement its caller and receiving endpoint. An extra graph connection alone is not a fix.');
  }
  if (edits.some(e => e.dependency_type === 'startup')) {
    steps.push('Startup-order edits change deployment sequencing; they do not change runtime calls. Review them separately.');
  }
  if (edits.length) steps.push('Run contract and integration tests, capture a new analysis, then compare findings again. This preview changes no source files.');
  return { title, summary, steps, edits: groupGraphEdits(edits), finding: linked };
}

export function explainPreview(preview = {}) {
  const resolved = preview.findings?.resolved || [];
  const introduced = preview.findings?.introduced || [];
  const beforeRaw = numericScore(preview.before?.raw_score), afterRaw = numericScore(preview.after?.raw_score);
  const raw = numericScore(preview.delta?.raw_debt_reduction) ??
    (beforeRaw !== null && afterRaw !== null ? beforeRaw - afterRaw : null);
  const score = numericScore(preview.delta?.score_reduction);
  const delta = raw ?? score;
  const outcome = delta === null ? 'unknown' : delta > 0 ? 'improved' : delta < 0 ? 'worse' : 'unchanged';
  const moved = unique(resolved.map(f => f.type)).flatMap(type => {
    const old = resolved.filter(f => f.type === type), next = introduced.filter(f => f.type === type);
    if (!next.length) return [];
    const from = names(old.flatMap(f => f.services || [])), to = names(next.flatMap(f => f.services || []));
    return from && to && from !== to ? [`${type} disappears on ${from} but appears on ${to}.`] : [];
  });
  let headline, explanation, next;
  if (outcome === 'unchanged') {
    headline = 'No modeled improvement';
    explanation = resolved.length || introduced.length
      ? 'Some findings changed, but the removed and introduced findings leave the weighted debt total unchanged.'
      : 'These edits did not change the tracked findings. This model has not demonstrated a benefit.';
    next = moved.length
      ? 'Revise the design to reduce or distribute the responsibility causing the finding; routing everything through another service can move the same problem.'
      : 'Review the remaining findings and try a change that addresses their cause. Use runtime tests to assess benefits this model cannot measure.';
  } else if (outcome === 'improved') {
    headline = score === 0 ? 'Small modeled improvement; displayed score rounds to zero' : 'Lower modeled debt';
    explanation = introduced.length ? 'Removed findings outweigh the new findings in the scoring model. Review the new problems before choosing this change.'
      : 'The proposed architecture has a lower weighted total of tracked findings.';
    next = 'Use this as a candidate design. Implement it in code and configuration, then verify contracts, failure handling and performance.';
  } else if (outcome === 'worse') {
    headline = 'Higher modeled debt';
    explanation = 'The proposed architecture adds more weighted debt than it removes.';
    next = 'Revise this proposal before implementing it. Inspect the introduced findings to see what made the result worse.';
  } else {
    headline = 'Result unavailable';
    explanation = 'The response does not contain enough score evidence to judge improvement.';
    next = 'Run the preview again before using this proposal to make a decision.';
  }
  const weights = preview.before?.weights || {};
  const contributions = Object.keys(weights).filter(key =>
    numericScore(preview.before?.smells?.[key]) !== null && numericScore(preview.after?.smells?.[key]) !== null &&
    preview.before.smells[key] !== preview.after.smells[key])
    .map(key => ({ key, label: key.replaceAll('_', ' '), before: preview.before.smells[key], after: preview.after.smells[key],
      weight: weights[key], reduction: (preview.before.smells[key] - preview.after.smells[key]) * weights[key] }));
  return { outcome, headline, explanation, next, moved, resolved, introduced, contributions,
    rawSummary: beforeRaw !== null && afterRaw !== null ? `Weighted finding total: ${formatScore(beforeRaw)} → ${formatScore(afterRaw)}.` : null };
}
