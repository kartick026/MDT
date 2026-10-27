import { useEffect, useState } from 'react';
import { listAnalyses, listProjects } from '../api';
import { useAuth } from '../context/useAuth';
import { formatScore, scoreDelta, readRoute, routeHash } from '../utils/analysis';
import CustomSelect from './CustomSelect';


const formatDate = value => {
  if (!value) return 'Unknown date';
  const d = new Date(value * 1000);
  return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
};

export default function ProjectHistory({ onSignIn }) {
  const { isAuthenticated } = useAuth();
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState(() => {
    const id = readRoute(location.hash).projectId;
    return id === 'demo' ? '' : id;
  });
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('');
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [retry, setRetry] = useState(0);
  const [selected, setSelected] = useState([]);
  const debtDelta = scoreDelta(selected[0]?.architecture_smell_score, selected[1]?.architecture_smell_score);

  useEffect(() => {
    if (!isAuthenticated) return;
    const controller = new AbortController();
    listProjects({ signal: controller.signal })
      .then(setProjects)
      .catch(err => {
        if (!controller.signal.aborted) setError(err.message);
      });
    return () => controller.abort();
  }, [isAuthenticated]);

  useEffect(() => {
    if (!isAuthenticated) return;
    const controller = new AbortController();
    setLoading(true);
    setError('');
    const timer = setTimeout(() => {
      listAnalyses(
        { project_id: projectId || undefined, status: status || undefined, q: query || undefined, limit: 20, offset },
        { signal: controller.signal }
      )
        .then(setData)
        .catch(err => {
          if (!controller.signal.aborted) setError(err.response?.data?.detail || err.message);
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [isAuthenticated, projectId, status, query, offset, retry]);

  const choose = item => {
    setSelected(previous =>
      previous.some(entry => entry.id === item.id)
        ? previous.filter(entry => entry.id !== item.id)
        : [...previous, item].slice(-2)
    );
  };

  return (
    <div className="workspace">
      <header className="workspace-heading">
        <div>
          <h1 className="page-title">Analysis history</h1>
          <p className="page-sub">Find saved results, inspect captured evidence, and compare recorded scores across revisions.</p>
        </div>
      </header>

      {!isAuthenticated ? (
        <section className="card workspace-account">
          <h2>Your saved analyses</h2>
          <p>Sign in with an invited account to access and compare your historical analyses.</p>
          <button className="btn btn-primary" onClick={onSignIn}>Sign in</button>
        </section>
      ) : (
        <>
          <section className="card workspace-account">
            {/* Filter toolbar */}
            <div className="filter-row">
              <label style={{ flex: '1 1 240px' }}>
                Search
                <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                  <input
                    className="form-input"
                    placeholder="Repository, project, commit revision, or job ID…"
                    value={query}
                    onChange={e => { setQuery(e.target.value); setOffset(0); }}
                    style={{ width: '100%', paddingRight: '28px' }}
                  />
                  {query && (
                    <button
                      type="button"
                      className="btn-clear-search"
                      aria-label="Clear history search"
                      style={{ position: 'absolute', right: '8px' }}
                      onClick={() => { setQuery(''); setOffset(0); }}
                    >
                      ✕
                    </button>
                  )}
                </div>
              </label>

              <label>
                Project
                <CustomSelect
                  className="form-select"
                  aria-label="Project"
                  value={projectId}
                  onChange={e => { setProjectId(e.target.value); setOffset(0); setSelected([]); }}
                >
                  <option value="">All projects ({projects.length})</option>
                  {projects.map(p => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </CustomSelect>
              </label>

              <label>
                Status
                <CustomSelect
                  className="form-select"
                  aria-label="Status"
                  value={status}
                  onChange={e => { setStatus(e.target.value); setOffset(0); }}
                >
                  <option value="">All statuses</option>
                  {['succeeded', 'partial', 'running', 'queued', 'failed', 'cancelled'].map(val => (
                    <option key={val} value={val}>{val[0].toUpperCase() + val.slice(1)}</option>
                  ))}
                </CustomSelect>
              </label>

              <button
                type="button"
                className="btn btn-ghost"
                style={{ alignSelf: 'flex-end', height: '42px' }}
                onClick={() => setRetry(v => v + 1)}
              >
                Refresh
              </button>
            </div>

            {/* Quick status pill buttons */}
            <div className="severity-overview" style={{ marginTop: '8px' }}>
              {[
                { label: 'All', val: '' },
                { label: 'Succeeded', val: 'succeeded' },
                { label: 'Partial results', val: 'partial' },
                { label: 'Failed', val: 'failed' }
              ].map(item => (
                <button
                  key={item.label}
                  type="button"
                  className={`severity-pill ${status === item.val ? 'active' : ''}`}
                  onClick={() => { setStatus(item.val); setOffset(0); }}
                >
                  <span className="severity-pill-label">{item.label}</span>
                </button>
              ))}
            </div>

            {error && <p className="form-error" role="alert" style={{ marginTop: '10px' }}>{String(error)}</p>}

            {/* Selection compare indicator */}
            {selected.length > 0 && (
              <div style={{
                margin: '12px 0',
                padding: '10px 16px',
                background: 'rgba(0, 212, 255, 0.08)',
                border: '1px solid rgba(0, 212, 255, 0.25)',
                borderRadius: '8px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: '8px'
              }}>
                <span style={{ fontSize: '13px', color: 'var(--text)' }}>
                  {selected.length === 1
                    ? '📌 1 analysis selected. Select 1 more to compare.'
                    : '✓ 2 analyses selected for side-by-side comparison.'}
                </span>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => setSelected([])}
                >
                  Clear selection
                </button>
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', margin: '14px 0 8px' }}>
              <span className="text-dim" style={{ fontSize: '12.5px' }}>
                {loading ? 'Loading analyses…' : `${data?.total || 0} analyses recorded`}
              </span>
            </div>

            {!loading && data?.analyses?.length === 0 && (
              <p className="text-dim">No historical analyses match active filters.</p>
            )}

            {!loading && !!data?.analyses?.length && (
              <div className="table-scroll">
                <table className="history-table">
                  <caption>Select any 2 completed analyses to compare scores and structural debt.</caption>
                  <thead>
                    <tr>
                      <th scope="col" style={{ width: '60px' }}>Compare</th>
                      <th scope="col">Project / Revision</th>
                      <th scope="col">Status</th>
                      <th scope="col">Risk / Debt</th>
                      <th scope="col">Date</th>
                      <th scope="col" style={{ width: '80px' }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.analyses.map(item => {
                      const isSelected = selected.some(entry => entry.id === item.id);
                      const isSelectable = ['succeeded', 'partial'].includes(item.status) && item.kind !== 'import';
                      return (
                        <tr key={item.id} className={isSelected ? 'selected-row' : ''}>
                          <td>
                            <input
                              type="checkbox"
                              aria-label={`Compare ${item.project_name || 'project'} ${item.commit_sha || item.id}`}
                              checked={isSelected}
                              disabled={!isSelectable}
                              onChange={() => choose(item)}
                            />
                          </td>
                          <th scope="row">
                            <a href={routeHash('projects', { projectId: item.project, jobId: item.id })}>
                              {item.project_name || 'Project'}
                            </a>
                            <small className="font-mono">
                              {item.kind === 'import' ? 'Topology import' : item.commit_sha?.slice(0, 10) || item.id.slice(0, 10)}
                            </small>
                          </th>
                          <td>
                            <span className={`badge ${item.status === 'succeeded' ? 'badge-success' : item.status === 'partial' ? 'badge-warning' : 'badge-danger'}`}>
                              {item.status}
                            </span>
                            {item.partial_results && (
                              <small style={{ display: 'block', color: 'var(--yellow)', fontSize: '11px' }}>
                                Limited evidence · open details
                              </small>
                            )}
                          </td>
                          <td>
                            <strong>{formatScore(item.risk_score)}</strong>
                            <span className="text-dim"> / </span>
                            <span style={{ color: 'var(--cyan)' }}>{formatScore(item.architecture_smell_score)}</span>
                          </td>
                          <td>{formatDate(item.created)}</td>
                          <td>
                            <a
                              href={routeHash('projects', { projectId: item.project, jobId: item.id })}
                              className="btn btn-ghost btn-sm"
                            >
                              Open
                            </a>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {/* Pagination controls */}
            <div className="workspace-actions" style={{ justifyContent: 'center', marginTop: '16px' }}>
              <button
                className="btn btn-ghost"
                disabled={loading || !offset}
                onClick={() => setOffset(Math.max(0, offset - 20))}
              >
                ← Previous
              </button>
              <span className="pagination-current" style={{ alignSelf: 'center', padding: '0 10px', fontSize: '13px' }}>
                Page {Math.floor(offset / 20) + 1}
              </span>
              <button
                className="btn btn-ghost"
                disabled={loading || offset + 20 >= (data?.total || 0)}
                onClick={() => setOffset(offset + 20)}
              >
                Next →
              </button>
            </div>
          </section>

          {/* Comparison section */}
          {selected.length > 0 && (
            <section className="card workspace-account" style={{ border: '1px solid rgba(0, 212, 255, 0.35)', animation: 'fadeUp 0.25s ease' }}>
              <div className="findings-header-text" style={{ marginBottom: '12px' }}>
                <h2>Historical score comparison</h2>
                <p className="text-dim">Evaluate architecture debt and risk scores between two saved checkpoints.</p>
              </div>

              {selected.length === 1 ? (
                <p className="text-dim">Check one more completed change analysis above to display the side-by-side delta.</p>
              ) : selected[0].project !== selected[1].project ? (
                <p className="form-error">Please select two analyses from the same project to calculate meaningful comparative drift.</p>
              ) : (
                <>
                  <div className="workspace-scores">
                    {selected.map((item, index) => (
                      <div key={item.id} className="score-card">
                        <span className="score-label">
                          {index === 0 ? 'Checkpoint A (First selection)' : 'Checkpoint B (Second selection)'}
                        </span>
                        <code style={{ fontSize: '12px', color: 'var(--cyan)' }}>
                          {item.commit_sha?.slice(0, 10) || item.id.slice(0, 10)}
                        </code>
                        <strong className="score-value" style={{ margin: '4px 0' }}>
                          {formatScore(item.architecture_smell_score)} debt
                        </strong>
                        <small className="text-dim">Risk score: {formatScore(item.risk_score)}</small>
                        <small className="text-dim">{formatDate(item.created)}</small>
                        <a
                          href={routeHash('projects', { projectId: item.project, jobId: item.id })}
                          className="btn btn-ghost btn-sm"
                          style={{ marginTop: '8px' }}
                        >
                          Open evidence
                        </a>
                      </div>
                    ))}

                    <div className="score-card" style={{ borderLeft: '1px solid var(--border-md)', background: 'var(--cyan-dim)' }}>
                      <span className="score-label">Debt Score Delta (B − A)</span>
                      <strong className="score-value" style={{ color: debtDelta == null ? 'var(--text-dim)' : debtDelta < 0 ? 'var(--green)' : debtDelta > 0 ? 'var(--orange)' : 'var(--text)' }}>
                        {debtDelta == null ? 'Unavailable' : `${formatScore(debtDelta)} pts`}
                      </strong>
                      <small className="text-dim">
                        {!selected[0].snapshot_version || !selected[1].snapshot_version
                          ? 'Captured topology identity is unavailable for this comparison.'
                          : selected[0].snapshot_version === selected[1].snapshot_version
                          ? 'Both analyses evaluated against the same captured topology.'
                          : 'Topologies differ between these analyses.'}
                      </small>
                      <a
                        href={routeHash('projects', { projectId: selected[0].project, view: 'drift' })}
                        className="btn btn-primary-ghost"
                        style={{ marginTop: '8px', fontSize: '11px' }}
                      >
                        Inspect in Drift View →
                      </a>
                    </div>
                  </div>
                </>
              )}
            </section>
          )}
        </>
      )}
    </div>
  );
}
