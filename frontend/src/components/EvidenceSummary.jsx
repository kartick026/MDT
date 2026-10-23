import { evidenceSummary, architectureSummary } from '../utils/analysis';

export default function EvidenceSummary({ result }) {
  const evidence = evidenceSummary(result);
  const architecture = architectureSummary(result);
  return (
    <aside className="evidence-summary" aria-label="Analysis evidence">
      <strong>{evidence.partial ? 'Partial analysis — review coverage before relying on this result' : 'Analysis evidence'}</strong>
      <p>Mode: {evidence.mode}. Parser coverage: {evidence.parser}.</p>
      <p><strong>{architecture.label}.</strong> {architecture.interpretation}</p>
      {Object.keys(architecture.evidence).length > 0 && <p>
        Startup relations: {architecture.evidence.startup_relations ?? 'not recorded'} · Configuration references: {architecture.evidence.configuration_relations ?? 'not recorded'} · Static/modeled calls: {architecture.evidence.static_or_modeled_calls ?? 'not recorded'}.
        {architecture.evidence.runtime_traffic_measured === false && ' Runtime traffic was not measured.'}
      </p>}
      {architecture.detectorVersion && <p>Recorded detector: {architecture.detectorVersion}. Saved results keep their original evidence; import and analyze again to use updated detection.</p>}
      {result.confidence_evidence?.kind === 'evidence_completeness' && <p>
        Evidence completeness: {Math.round((result.confidence || 0) * 100)}%. This measures available static evidence, not prediction accuracy.
        {result.assessment_status === 'insufficient_evidence' && ' There is insufficient evidence for an architecture risk assessment; the score is provisional.'}
        {result.assessment_status === 'no_semantic_change' && ' The supplied changes are equivalent under the supported parser.'}
        {result.assessment_status === 'no_changes' && ' No changed source was supplied.'}
      </p>}
      <p>{evidence.semantic ? 'Historical semantic evidence was used.' : 'This result does not confirm historical semantic evidence.'} Scores are engineering indicators, not calibrated incident probabilities.</p>
      {result.evidence?.topology_reextracted === false && <p>Change impact uses the captured project topology{result.evidence.topology_revision ? ` at ${result.evidence.topology_revision}` : ''}. Import a new revision to measure structural drift.</p>}
      {evidence.warnings.length > 0 && <ul>{evidence.warnings.map((warning, index) => <li key={index}>{String(warning)}</li>)}</ul>}
    </aside>
  );
}
