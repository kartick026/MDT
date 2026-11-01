import { useEffect, useState } from 'react';
import { getPolicies, savePolicies } from '../api';
import CustomSelect from './CustomSelect';

export default function ProjectPolicies({ project }) {
  const [data, setData] = useState(null);
  const [source, setSource] = useState('');
  const [target, setTarget] = useState('');
  const [kind, setKind] = useState('forbid');
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    getPolicies(project.id, { signal: controller.signal })
      .then(setData)
      .catch(err => {
        if (!controller.signal.aborted) setError(err.message);
      });
    return () => controller.abort();
  }, [project.id]);

  const save = async rules => {
    setBusy(true);
    setError('');
    try {
      setData(await savePolicies(project.id, rules));
      setReason('');
    } catch (err) {
      setError(
        typeof err.response?.data?.detail === 'string'
          ? err.response.data.detail
          : 'Could not save. Use one rule per service pair and provide a reason.'
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <section>
      <h3>Dependency rules</h3>
      <p>Require or forbid a dependency between two modeled nodes. Rules apply to the captured topology; import a revision to evaluate its structure. They do not change risk scores.</p>
      {error && <p role="alert" className="form-error">{error}</p>}
      {data ? (
        <>
          <ul className="workspace-findings">
            {data.evaluation.rules.map((rule, index) => (
              <li key={`${rule.source}:${rule.target}`}>
                <strong>{rule.kind} {rule.source} → {rule.target}</strong>
                <p>{rule.reason} · {rule.status}</p>
                <button
                  className="btn btn-ghost"
                  disabled={busy}
                  onClick={() => save(data.rules.filter((_, i) => i !== index))}
                >
                  Remove rule
                </button>
              </li>
            ))}
          </ul>
          <form
            className="workspace-form"
            onSubmit={e => {
              e.preventDefault();
              save([...data.rules, { source, target, kind, reason }]);
            }}
          >
            <div className="filter-row">
              <label>
                Rule
                <CustomSelect
                  className="form-select"
                  value={kind}
                  onChange={e => setKind(e.target.value)}
                >
                  <option value="forbid">Forbid dependency</option>
                  <option value="require">Require dependency</option>
                </CustomSelect>
              </label>
              {[
                ['From node', source, setSource],
                ['To node', target, setTarget]
              ].map(([label, value, setter]) => (
                <label key={label}>
                  {label}
                  <CustomSelect
                    className="form-select"
                    value={value}
                    onChange={e => setter(e.target.value)}
                  >
                    <option value="">Select a node</option>
                    {(project.snapshot?.services || []).map(node => (
                      <option key={node.name} value={node.name}>{node.name}</option>
                    ))}
                  </CustomSelect>
                </label>
              ))}
            </div>
            <label>
              Reason
              <input
                className="form-input"
                required
                minLength={3}
                maxLength={500}
                value={reason}
                onChange={e => setReason(e.target.value)}
              />
            </label>
            <button className="btn btn-ghost" disabled={busy || data.rules.length >= 50}>
              {busy ? 'Saving…' : 'Add rule'}
            </button>
          </form>
        </>
      ) : (
        <p role="status">Loading dependency rules…</p>
      )}
    </section>
  );
}
