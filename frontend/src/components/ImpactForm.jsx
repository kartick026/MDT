import { useState } from 'react';
import { analyzeImpact } from '../api';

const RISK_COLORS = {
  LOW: 'var(--green)', MEDIUM: 'var(--yellow)',
  HIGH: 'var(--orange)', CRITICAL: 'var(--red)',
  low: 'var(--green)', medium: 'var(--yellow)',
  high: 'var(--orange)', critical: 'var(--red)'
};

function ScoreGauge({ score, level }) {
  const r = 50, cx = 60, cy = 60;
  const circumference = 2 * Math.PI * r;
  const offset = circumference - (score / 100) * circumference;
  const color = RISK_COLORS[level] || 'var(--text-faint)';
  return (
    <div className="gauge-wrap">
      <svg width="120" height="120" viewBox="0 0 120 120">
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="9" />
        <circle
          cx={cx} cy={cy} r={r} fill="none"
          stroke={color} strokeWidth="9"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform={`rotate(-90 ${cx} ${cy})`}
          style={{ transition: 'stroke-dashoffset .9s cubic-bezier(0.16,1,.3,1), stroke .4s' }}
        />
        <text x={cx} y={cy - 5} textAnchor="middle" fill="white" fontSize="22" fontWeight="700" fontFamily="'JetBrains Mono', monospace">{score}</text>
        <text x={cx} y={cy + 14} textAnchor="middle" fill={color} fontSize="10" fontFamily="Inter,sans-serif" fontWeight="600" style={{textTransform:'uppercase'}}>{level}</text>
      </svg>
    </div>
  );
}

export default function ImpactForm({ onAnalysis }) {
  const [repoUrl, setRepoUrl] = useState('https://github.com/kartick026/MDT');
  const [commitSha, setCommitSha] = useState('main');
  const [files, setFiles] = useState('services/payment_service/main.py, services/user_service/main.py');

  const [result,  setResult]  = useState(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    if (!repoUrl || !commitSha || !files) return;
    setLoading(true); setError(null);
    try {
      const changedFiles = files.split(',').map(f => f.trim()).filter(f => f);
      const data = await analyzeImpact({
        repo_url: repoUrl,
        commit_sha: commitSha,
        changed_files: changedFiles,
      });
      setResult(data);
      onAnalysis?.();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Backend unreachable — is it running on :8000?');
    } finally {
      setLoading(false);
    }
  };

  const loadSample = () => {
    setRepoUrl('https://github.com/kartick026/MDT');
    setCommitSha('main');
    setFiles('services/payment_service/main.py');
  };

  return (
    <div className="impact-split">
      {/* Left: Form */}
      <div className="impact-panel">
        <div>
          <div className="panel-title">Configure Analysis</div>
          <div className="text-dim text-sm">Target a repository and commit to run the HMDA drift analysis</div>
        </div>

        <form onSubmit={submit} style={{display:'flex',flexDirection:'column',gap:18}}>
          <div className="form-field">
            <label className="form-label">Repository URL</label>
            <input className="form-input" type="url" value={repoUrl} onChange={e => setRepoUrl(e.target.value)} required />
          </div>

          <div className="form-field">
            <label className="form-label">Commit SHA (or branch ref)</label>
            <input className="form-input" type="text" value={commitSha} onChange={e => setCommitSha(e.target.value)} required />
          </div>

          <div className="form-field">
            <div className="diff-toolbar">
              <label className="form-label">Changed Files (comma separated)</label>
              <button type="button" className="btn btn-ghost" onClick={loadSample}>Load sample</button>
            </div>
            <textarea
              className="diff-editor"
              placeholder={`e.g. services/order_service/main.py, services/user_service/models.py`}
              value={files}
              onChange={e => setFiles(e.target.value)}
              rows={4}
              required
            />
          </div>

          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? <><span className="spinner-xs" /> Analyzing…</> : '⚡ Run HMDA Analysis'}
          </button>
          {error && <div className="form-error">{error}</div>}
        </form>
      </div>

      {/* Right: Result */}
      <div className="impact-panel">
        <div>
          <div className="panel-title">Analysis Result</div>
          <div className="text-dim text-sm">Live output from the HMDA engine</div>
        </div>

        {!result && !loading && (
          <div className="result-placeholder">
            <div className="result-placeholder-icon">⚡</div>
            <p className="text-sm">Submit a commit to see the impact report</p>
          </div>
        )}

        {loading && (
          <div className="state-loading" style={{minHeight:340}}>
            <div className="spinner" />
            <span className="text-dim">Cloning & Running HMDA engine…</span>
          </div>
        )}

        {result && !loading && (
          <div className="result-panel anim-fade-in">
            <div className="result-header">
              <div className="result-meta">
                <div className="result-service">Commit {result.commit?.substring(0, 7)}</div>
                <div className="result-ts text-dim text-xs">Confidence: {(result.confidence * 100).toFixed(0)}%</div>
              </div>
              <ScoreGauge score={Math.round(result.risk_score)} level={result.severity} />
            </div>

            {result.explanation && (
              <div className="explain-box">{result.explanation.replace(/\*\*/g,'')}</div>
            )}

            {result.impacted_services?.length > 0 && (
              <div>
                <div className="section-label">Downstream Impact</div>
                <div className="downstream-tags">
                  {result.impacted_services.map(s => <span key={s} className="dtag">{s.replace('_service','')}</span>)}
                </div>
              </div>
            )}

            {result.affected_files?.length > 0 && (
              <div style={{ marginTop: '1.5rem' }}>
                <div className="section-label">Affected Files</div>
                <div className="recs-list" style={{ gap: '0.25rem' }}>
                  {result.affected_files.map((f, i) => (
                    <div key={i} className="rec-item" style={{ fontSize: '0.85rem', padding: '0.5rem' }}>
                      <span style={{ color: f.change_type === 'added' ? 'var(--green)' : f.change_type === 'deleted' ? 'var(--red)' : 'var(--yellow)', marginRight: '0.5rem', fontWeight: 'bold' }}>
                        [{f.change_type.toUpperCase()}]
                      </span>
                      {f.path} ({f.lines_changed} lines changed)
                    </div>
                  ))}
                </div>
              </div>
            )}

            {result.suggested_fixes?.length > 0 && (
              <div style={{ marginTop: '1.5rem' }}>
                <div className="section-label">Recommendations</div>
                <div className="recs-list">
                  {result.suggested_fixes.map((r,i) => <div key={i} className="rec-item">{r}</div>)}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
