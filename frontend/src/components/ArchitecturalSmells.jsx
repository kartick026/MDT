import { useEffect, useState } from 'react';
import { getSmells } from '../api';

const ICONS = {
  'Circular Dependency': '↻',
  'God / Bottleneck Service': '⚡',
  'High Coupling': '⚯',
  'Dependency Explosion': '💥',
  'Dead / Isolated Service': '☠',
  'API Instability': '⍻'
};

const SEVERITY_COLORS = {
  CRITICAL: 'var(--red)',
  HIGH: 'var(--orange)',
  MEDIUM: 'var(--yellow)',
  LOW: 'var(--text-dim)',
};

export default function ArchitecturalSmells() {
  const [smells, setSmells] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    getSmells()
      .then(data => {
        setSmells(data);
        setError(null);
      })
      .catch(err => {
        console.error(err);
        setError('Failed to fetch architectural smells from backend.');
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="state-loading"><div className="spinner" /><span>Running smell detection...</span></div>;
  if (error) return <div className="state-error"><span>⚠</span><span>{error}</span></div>;

  return (
    <div className="smells-container">

      {smells.length === 0 ? (
        <div className="card state-empty">
          <p>No architectural smells detected in the current system state. Great job!</p>
        </div>
      ) : (
        <div className="smells-grid">
          {smells.map((smell, idx) => {
            const color = SEVERITY_COLORS[smell.severity?.toUpperCase()] || 'var(--cyan)';
            return (
              <div key={idx} className="smell-card">
                <div className="smell-icon-wrapper" style={{ '--icon-color': color }}>
                  <div className="smell-icon">{ICONS[smell.type] || '⚠'}</div>
                </div>
                <h3 className="smell-title">{smell.type}</h3>
                <p className="smell-desc">{smell.description}</p>
                <div className="smell-meta">
                  Confidence: {smell.confidence || 'unknown'}
                </div>
                {smell.services?.length > 0 && (
                  <div className="smell-services">
                    {smell.services.map(s => (
                      <span key={s} className="tag text-xs">{s.replace('-service', '')}</span>
                    ))}
                  </div>
                )}
                {smell.evidence && (
                  <details className="smell-evidence">
                    <summary>View evidence</summary>
                    <pre>{JSON.stringify(smell.evidence, null, 2)}</pre>
                  </details>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
