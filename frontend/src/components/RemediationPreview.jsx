import { formatScore, previewChange } from '../utils/analysis';
import { explainPreview, proposalGuide, relationDescription } from '../utils/remediation';
import EvidenceDetails from './EvidenceDetails';

export function ProposedChange({ fix, findings }) {
  const guide = proposalGuide(fix, findings);
  return <div className="proposed-change">
    <h4 className="recommendation-title">{guide.title}</h4>
    {guide.summary && <p className="recommendation-desc">{guide.summary}</p>}
    {!!guide.edits.length && <>
      <p className="counterfactual-disclaimer">A → B means A depends on B; the dependency type explains how. Expand the changes to see services, protocols and endpoints.</p>
      <details className="remediation-details">
        <summary>View {guide.edits.length} grouped model changes ({fix.edits.length} individual edits)</summary>
        <p>A → B means A depends on B. Direction identifies which service needs changing. HTTP/gRPC describes a modeled call; startup order means A waits for B to start. Different types or endpoints can connect the same two services.</p>
        <ul className="remediation-edit-list">{guide.edits.map((edit, index) => <li key={index}>
          {edit.action.endsWith('_edge') ? <>
            <strong>{edit.action === 'remove_edge' ? 'Remove' : 'Add'}: {edit.from_service} → {edit.to_service}</strong>
            <span>{edit.variants.length > 1 ? 'Multiple recorded relations; their types and endpoints are listed below.' : `${edit.from_service} ${relationDescription(edit).verb} ${edit.to_service}`}</span>
            <ul>{edit.variants.map(variant => <li key={variant}><code>{variant}</code></li>)}</ul>
          </> : <>
            <strong>{edit.action === 'add_node' ? 'Add service' : 'Update service'}: {edit.from_service}</strong>
            {edit.has_circuit_breaker !== undefined && <span>Circuit-breaker protection: {String(edit.has_circuit_breaker)} (hypothetical)</span>}
            {edit.resilient !== undefined && <span>Resilience recorded: {String(edit.resilient)} (hypothetical)</span>}
          </>}
        </li>)}</ul>
      </details>
      <details className="remediation-details">
        <summary>What would I change in the actual project?</summary>
        <ol>{guide.steps.map(step => <li key={step}>{step}</li>)}</ol>
      </details>
    </>}
  </div>;
}

export default function RemediationPreview({ previewData, isLoading, error }) {
  if (isLoading) return <div className="counterfactual-loading" role="status"><span className="spinner-sm" />Checking how the proposed changes affect recorded findings…</div>;
  if (error) return <div className="form-error inline-error" role="alert">{String(error)}</div>;
  if (!previewData) return null;
  const change = previewChange(previewData), result = explainPreview(previewData);
  return <section className={`counterfactual-panel preview-${result.outcome}`} aria-label="Remediation simulation result">
    <div className="counterfactual-header"><strong>Simulation result</strong><span className="counterfactual-mode-tag">Saved architecture · no code changed</span></div>
    <div className="preview-verdict" role="status">
      <h4>{result.headline}</h4><p>{result.explanation}</p>
      {result.moved.map(message => <p key={message}><strong>{message}</strong></p>)}
    </div>
    <div className="counterfactual-scores">
      <div className="counterfactual-score-card before"><span className="cf-label">Current debt score</span><span className="cf-val">{formatScore(previewData.before?.score)}</span><small className="cf-sub">Recorded architecture</small></div>
      <div className="counterfactual-arrow" aria-hidden="true">→</div>
      <div className="counterfactual-score-card after"><span className="cf-label">Proposed debt score</span><span className="cf-val">{formatScore(previewData.after?.score)}</span><small className="cf-sub">After simulated changes</small></div>
      <div className={`counterfactual-score-card ${result.outcome}`}><span className="cf-label">Score change</span><span className="cf-val">{change.text}</span><small className="cf-sub">{change.label}</small></div>
    </div>
    <div className="preview-finding-columns">
      {[['Disappeared in this model', result.resolved], ['Appeared in this model', result.introduced]].map(([label, items]) => <div key={label}>
        <h5>{label} ({items.length})</h5>
        {items.length ? <ul>{items.slice(0, 5).map((finding, index) => <li key={finding.id || index}><strong>{finding.type}</strong><span>{(finding.services || []).join(', ')}</span></li>)}</ul> : <p>None recorded.</p>}
        {items.length > 5 && <details><summary>Show {items.length - 5} more findings</summary><ul>{items.slice(5).map((finding, index) => <li key={finding.id || index}>{finding.type}: {(finding.services || []).join(', ')}</li>)}</ul></details>}
      </div>)}
    </div>
    <div className="preview-next-step"><strong>What to do next</strong><p>{result.next}</p></div>
    <details className="remediation-details"><summary>Why did the score change by {change.text}?</summary>
      {result.rawSummary && <p>{result.rawSummary}</p>}
      <p>The score is calculated from finding counts and their weights, then scaled to 0–100. Moving the same finding to another service leaves its weight unchanged. A small score difference at high debt can still represent substantial finding changes.</p>
      {!!result.contributions.length && <ul>{result.contributions.map(row => <li key={row.key}>{row.label}: {row.before} → {row.after}; weight {row.weight}; {row.reduction > 0 ? 'removes' : 'adds'} {formatScore(Math.abs(row.reduction))} weighted units.</li>)}</ul>}
    </details>
    {!!previewData.warnings?.length && <details className="remediation-details"><summary>Implementation checks</summary><ul>{previewData.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul></details>}
    <p className="counterfactual-disclaimer">This tests a copy of the saved architecture. It does not change code or measure production performance. Validate behavior before adopting the design.</p>
    <EvidenceDetails label="Technical simulation evidence" value={previewData} />
  </section>;
}
