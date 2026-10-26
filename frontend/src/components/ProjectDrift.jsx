import { useEffect, useState } from 'react';
import { getDrift, getSnapshots, setBaseline } from '../api';
import { formatScore } from '../utils/analysis';
import EvidenceDetails from './EvidenceDetails';
import CoverageIndicators from './CoverageIndicators';

export default function ProjectDrift({ projectId }) {
  const [data, setData] = useState(null);
  const [base, setBase] = useState('');
  const [target, setTarget] = useState('');
  const [comparison, setComparison] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    getSnapshots(projectId, { signal: controller.signal })
      .then(value => {
        setData(value);
        setBase(value.baseline_version || value.snapshots.at(-1)?.snapshot_version || '');
        setTarget(value.snapshots[0]?.snapshot_version || '');
      })
      .catch(err => {
        if (!controller.signal.aborted) setError(err.response?.data?.detail || err.message);
      });
    return () => controller.abort();
  }, [projectId]);

  useEffect(() => {
    if (!base || !target) return;
    const controller = new AbortController();
    setComparison(null);
    setBusy(true);
    setError('');
    getDrift(projectId, { base_version: base, target_version: target }, { signal: controller.signal })
      .then(setComparison)
      .catch(err => {
        if (!controller.signal.aborted) setError(err.response?.data?.detail || err.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false);
      });
    return () => controller.abort();
  }, [projectId, base, target]);

  const save = async () => {
    setBusy(true);
    setNotice('');
    try {
      await setBaseline(projectId, base);
      setData(previous => ({ ...previous, baseline_version: base }));
      setNotice('✓ Baseline successfully saved for this project.');
      setTimeout(() => setNotice(''), 3000);
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card workspace-account">
      <div className="findings-header">
        <div className="findings-header-text">
          <h2>Architecture drift</h2>
          <p className="text-dim">
            Compare captured source topologies across revisions to detect structural debt evolution and dependency drift.
          </p>
        </div>
      </div>

      {data && (
        <>
          <div className="filter-row" style={{ marginTop: '12px' }}>
            <label>
              Baseline Snapshot
              <select className="form-select" value={base} onChange={e => setBase(e.target.value)}>
                {data.snapshots.map(snapshot => (
                  <option key={snapshot.snapshot_version} value={snapshot.snapshot_version}>
                    {snapshot.revision?.slice(0, 10) || snapshot.snapshot_version.slice(0, 10)}
                    {snapshot.captured_at ? ` · ${new Date(snapshot.captured_at * 1000).toLocaleString()}` : ''}
                    {snapshot.snapshot_version === data.baseline_version ? ' (Current Baseline)' : ''}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Target Snapshot
              <select className="form-select" value={target} onChange={e => setTarget(e.target.value)}>
                {data.snapshots.map(snapshot => (
                  <option key={snapshot.snapshot_version} value={snapshot.snapshot_version}>
                    {snapshot.revision?.slice(0, 10) || snapshot.snapshot_version.slice(0, 10)}
                    {snapshot.captured_at ? ` · ${new Date(snapshot.captured_at * 1000).toLocaleString()}` : ''}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="workspace-actions" style={{ marginTop: '10px' }}>
            <button
              type="button"
              className="btn btn-ghost"
              disabled={busy || !base || base === data.baseline_version}
              onClick={save}
            >
              {base === data.baseline_version ? '✓ Current baseline' : '📌 Set selected as baseline'}
            </button>
            {data.snapshots.length < 2 && (
              <span className="text-dim" style={{ fontSize: '12px' }}>
                {data.snapshots.length === 0
                  ? 'No captured snapshot is available yet. Wait for the project import to finish.'
                  : 'Only 1 captured snapshot is available. Import another revision in Analyze to compare changes.'}
              </span>
            )}
          </div>
        </>
      )}

      {busy && (
        <div className="counterfactual-loading" style={{ margin: '14px 0' }}>
          <span className="spinner-sm" />
          <span>Comparing captured topology graph snapshots…</span>
        </div>
      )}
      {notice && <p role="status" className="badge badge-success" style={{ margin: '10px 0', display: 'inline-block' }}>{notice}</p>}
      {error && <p role="alert" className="form-error">{String(error)}</p>}

      {comparison && (
        <div style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Score comparison */}
          <div className="workspace-scores">
            <div className="score-card">
              <span className="score-label">Baseline Debt</span>
              <strong className="score-value">{formatScore(comparison.scores?.base)}</strong>
              <small>Anchor topology</small>
            </div>
            <div className="score-card">
              <span className="score-label">Target Debt</span>
              <strong className="score-value">{formatScore(comparison.scores?.target)}</strong>
              <small className={comparison.scores?.delta < 0 ? 'text-green' : comparison.scores?.delta > 0 ? 'text-red' : ''}>
                {comparison.scores?.direction} · delta {formatScore(comparison.scores?.delta)}
              </small>
            </div>
            <div className="score-card">
              <span className="score-label">Findings Delta</span>
              <strong className="score-value text-cyan">
                +{comparison.findings.introduced.length} / −{comparison.findings.resolved.length}
              </strong>
              <small>{comparison.findings.unchanged_count} unchanged</small>
            </div>
          </div>

          <aside className="evidence-summary">
            <strong>
              {comparison.evidence.same_snapshot
                ? 'Same captured snapshot'
                : comparison.evidence.revision_comparison
                ? 'Captured revision comparison'
                : 'Captured topology comparison'}
            </strong>
            {comparison.evidence.warnings && comparison.evidence.warnings.map((warning, index) => (
              <p key={index}>{warning}</p>
            ))}
          </aside>

          <details className="evidence-summary" open>
            <summary>Coverage recorded for each capture</summary>
            {[['Baseline', base], ['Target', target]].map(([label, version]) => (
              <section key={label} aria-label={`${label} captured coverage`}>
                <h3>{label} capture</h3>
                <CoverageIndicators result={{ topology_coverage: data?.snapshots.find(snapshot => snapshot.snapshot_version === version)?.coverage || {} }} label={`${label} coverage indicators`} />
              </section>
            ))}
          </details>

          {/* Structured Drift Diff Grid */}
          <div className="drift-grid">
            {['services', 'dependencies', 'contracts'].map(kind => {
              const diff = comparison[kind] || { added: [], removed: [], modified: [] };
              const addedCount = diff.added?.length || 0;
              const removedCount = diff.removed?.length || 0;
              const modifiedCount = diff.modified?.length || 0;

              return (
                <section key={kind} className="drift-card">
                  <div className="drift-card-header">
                    <h3 style={{ margin: 0, fontSize: '15px', textTransform: 'capitalize' }}>{kind}</h3>
                    <span style={{ fontSize: '11px', color: 'var(--text-dim)' }}>
                      {addedCount} added · {removedCount} removed{diff.modified ? ` · ${modifiedCount} modified` : ''}
                    </span>
                  </div>

                  <div className="drift-changes">
                    {diff.added && diff.added.map((item, i) => (
                      <span key={i} className="edit-pill" style={{ color: 'var(--green)', borderColor: 'rgba(0,255,136,0.3)', background: 'rgba(0,255,136,0.05)' }}>
                        + {typeof item === 'string' ? item : item.from && item.to ? `${item.from} → ${item.to}` : JSON.stringify(item)}
                      </span>
                    ))}
                    {diff.removed && diff.removed.map((item, i) => (
                      <span key={i} className="edit-pill" style={{ color: 'var(--red)', borderColor: 'rgba(255,45,85,0.3)', background: 'rgba(255,45,85,0.05)' }}>
                        − {typeof item === 'string' ? item : item.from && item.to ? `${item.from} → ${item.to}` : JSON.stringify(item)}
                      </span>
                    ))}
                    {diff.modified && diff.modified.map((item, i) => (
                      <span key={i} className="edit-pill" style={{ color: 'var(--yellow)', borderColor: 'rgba(251,191,36,0.3)', background: 'rgba(251,191,36,0.05)' }}>
                        ✎ {typeof item === 'string' ? item : JSON.stringify(item)}
                      </span>
                    ))}
                    {addedCount === 0 && removedCount === 0 && modifiedCount === 0 && (
                      <span style={{ fontSize: '12px', color: 'var(--text-dim)' }}>No changes detected between snapshots.</span>
                    )}
                  </div>

                  <EvidenceDetails label={`Inspect raw ${kind} JSON`} value={diff} />
                </section>
              );
            })}
          </div>

          <EvidenceDetails label="Full comparison evidence payload" value={comparison} />
        </div>
      )}
    </section>
  );
}
