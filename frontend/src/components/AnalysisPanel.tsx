import React, { useState } from 'react';
import { analyzeImpact, type AnalysisResult } from '../api/client';
import { Play, AlertTriangle, CheckCircle, Info, RefreshCw } from 'lucide-react';

export const AnalysisPanel: React.FC = () => {
  const [repo, setRepo] = useState('https://github.com/example/repo');
  const [commit, setCommit] = useState('abc1234');
  const [files, setFiles] = useState('services/payment_service/main.py, services/user_service/main.py');
  
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState('');

  const handleAnalyze = async () => {
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const changedFiles = files.split(',').map(f => f.trim()).filter(f => f);
      const res = await analyzeImpact(repo, commit, changedFiles);
      setResult(res);
    } catch (err: any) {
      setError(err.message || 'Analysis failed');
    } finally {
      setLoading(false);
    }
  };

  const getSeverityColor = (sev: string) => {
    switch (sev.toLowerCase()) {
      case 'low': return 'var(--success)';
      case 'medium': return 'var(--warning)';
      case 'high':
      case 'critical': return 'var(--danger)';
      default: return 'var(--text-secondary)';
    }
  };

  return (
    <div className="glass-panel mt-8">
      <h2 className="flex items-center gap-2" style={{ marginBottom: '1.5rem' }}>
        <Play size={20} /> Trigger Manual Analysis
      </h2>
      
      <div className="grid grid-cols-2 gap-4" style={{ marginBottom: '1.5rem' }}>
        <div>
          <label style={{ display: 'block', fontSize: '0.9rem', marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>Repository URL</label>
          <input 
            type="text" 
            value={repo} 
            onChange={e => setRepo(e.target.value)}
            style={{ width: '100%', padding: '0.75rem', borderRadius: '8px', border: '1px solid var(--panel-border)', background: 'rgba(0,0,0,0.2)', color: 'white' }}
          />
        </div>
        <div>
          <label style={{ display: 'block', fontSize: '0.9rem', marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>Commit SHA</label>
          <input 
            type="text" 
            value={commit} 
            onChange={e => setCommit(e.target.value)}
            style={{ width: '100%', padding: '0.75rem', borderRadius: '8px', border: '1px solid var(--panel-border)', background: 'rgba(0,0,0,0.2)', color: 'white' }}
          />
        </div>
        <div style={{ gridColumn: 'span 2' }}>
          <label style={{ display: 'block', fontSize: '0.9rem', marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>Changed Files (comma separated)</label>
          <input 
            type="text" 
            value={files} 
            onChange={e => setFiles(e.target.value)}
            style={{ width: '100%', padding: '0.75rem', borderRadius: '8px', border: '1px solid var(--panel-border)', background: 'rgba(0,0,0,0.2)', color: 'white' }}
          />
        </div>
      </div>
      
      <button className="btn-primary" onClick={handleAnalyze} disabled={loading}>
        {loading ? <div className="spin"><RefreshCw size={16} /></div> : <Play size={16} />}
        {loading ? 'Analyzing...' : 'Run Analysis'}
      </button>

      {error && (
        <div className="mt-4" style={{ padding: '1rem', background: 'rgba(239, 68, 68, 0.1)', color: 'var(--danger)', borderRadius: '8px', border: '1px solid rgba(239, 68, 68, 0.3)' }}>
          <div className="flex items-center gap-2">
            <AlertTriangle size={18} /> {error}
          </div>
        </div>
      )}

      {result && (
        <div className="mt-8">
          <h3 style={{ marginBottom: '1rem', borderBottom: '1px solid var(--panel-border)', paddingBottom: '0.5rem' }}>Analysis Results</h3>
          
          <div className="grid grid-cols-3 gap-4" style={{ marginBottom: '1.5rem' }}>
            <div style={{ background: 'rgba(0,0,0,0.2)', padding: '1rem', borderRadius: '8px' }}>
              <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Risk Score</p>
              <h2 style={{ fontSize: '2rem', color: getSeverityColor(result.severity) }}>{result.risk_score.toFixed(1)}</h2>
            </div>
            <div style={{ background: 'rgba(0,0,0,0.2)', padding: '1rem', borderRadius: '8px' }}>
              <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Severity</p>
              <h2 style={{ fontSize: '1.5rem', color: getSeverityColor(result.severity), textTransform: 'uppercase', marginTop: '0.5rem' }}>{result.severity}</h2>
            </div>
            <div style={{ background: 'rgba(0,0,0,0.2)', padding: '1rem', borderRadius: '8px' }}>
              <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Confidence</p>
              <h2 style={{ fontSize: '1.5rem', marginTop: '0.5rem' }}>{(result.confidence * 100).toFixed(0)}%</h2>
            </div>
          </div>

          <div style={{ marginBottom: '1.5rem' }}>
            <h4 style={{ marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>Impacted Services</h4>
            <div className="flex gap-2" style={{ flexWrap: 'wrap' }}>
              {result.impacted_services.length > 0 ? result.impacted_services.map(svc => (
                <span key={svc} style={{ background: 'rgba(59, 130, 246, 0.2)', color: 'var(--accent-hover)', padding: '0.3rem 0.8rem', borderRadius: '999px', fontSize: '0.85rem' }}>
                  {svc}
                </span>
              )) : <span style={{ color: 'var(--success)' }}>None detected</span>}
            </div>
          </div>

          {result.explanation && (
            <div style={{ background: 'rgba(255,255,255,0.03)', padding: '1.25rem', borderRadius: '8px', borderLeft: `4px solid ${getSeverityColor(result.severity)}`, marginBottom: '1.5rem' }}>
              <h4 className="flex items-center gap-2" style={{ marginBottom: '0.5rem', color: 'var(--text-primary)' }}><Info size={16} /> AI Explanation</h4>
              <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>{result.explanation}</p>
            </div>
          )}

          {result.suggested_fixes && result.suggested_fixes.length > 0 && (
            <div>
              <h4 style={{ marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>Suggested Fixes</h4>
              <ul style={{ listStyleType: 'none', padding: 0 }}>
                {result.suggested_fixes.map((fix, idx) => (
                  <li key={idx} className="flex gap-2" style={{ marginBottom: '0.5rem', color: 'var(--text-primary)', background: 'rgba(16, 185, 129, 0.05)', padding: '0.75rem', borderRadius: '8px', border: '1px solid rgba(16, 185, 129, 0.2)' }}>
                    <CheckCircle size={18} style={{ color: 'var(--success)', flexShrink: 0, marginTop: '2px' }} />
                    <span style={{ fontSize: '0.95rem' }}>{fix}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

        </div>
      )}
    </div>
  );
};
