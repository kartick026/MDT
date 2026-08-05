import { useEffect, useState } from 'react';
import { getGraph } from '../api';

const RISK_COLOR = {
  LOW:      '#00ff88',
  MEDIUM:   '#fbbf24',
  HIGH:     '#f97316',
  CRITICAL: '#ff2d55',
  UNKNOWN:  '#3a3f5c',
};

const NODE_W = 160, NODE_H = 52;

/* Fixed layout positions keyed by service name */
const POS = {
  'user-service':         { x: 230, y: 40  },
  'order-service':        { x: 230, y: 175 },
  'payment-service':      { x: 80,  y: 310 },
  'notification-service': { x: 380, y: 310 },
};

/* Animated dashed arrow between two nodes */
function Edge({ from, to, idx }) {
  const fx = from.x + NODE_W / 2, fy = from.y + NODE_H;
  const tx = to.x   + NODE_W / 2, ty = to.y;
  const mx = (fx + tx) / 2,       my = (fy + ty) / 2 - 20;
  const d = `M ${fx} ${fy} Q ${mx} ${my} ${tx} ${ty}`;
  return (
    <g>
      <path
        d={d} fill="none" stroke="rgba(0,212,255,0.18)" strokeWidth="1.5"
        strokeDasharray="6 5"
        style={{ animation: `graphDash${idx} 3s linear infinite` }}
      />
      <polygon
        points={`${tx},${ty} ${tx - 5},${ty - 10} ${tx + 5},${ty - 10}`}
        fill="rgba(0,212,255,0.4)"
      />
    </g>
  );
}

export default function DependencyGraph() {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);

  useEffect(() => {
    getGraph()
      .then(d => { setData(d); setError(null); })
      .catch(() => setError('Could not load dependency graph from backend'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="state-loading"><div className="spinner" /><span>Loading graph…</span></div>;
  if (error)   return <div className="state-error"><span>⚠</span><span>{error}</span></div>;

  const nodes = data?.nodes || [];
  const edges = data?.edges || [];

  if (!nodes.length) {
    return (
      <div className="card state-empty">
        <p>No services in the graph yet. Run an analysis to populate it.</p>
      </div>
    );
  }

  return (
    <div className="graph-card">
      <p className="text-dim text-sm" style={{ marginBottom: 20 }}>
        Arrows show dependency direction (A → B means A depends on B). Border colour reflects latest risk level.
      </p>

      <div style={{ overflowX: 'auto' }}>
        <svg className="graph-svg" viewBox="0 0 620 420" preserveAspectRatio="xMidYMid meet">
          <defs>
            {edges.map((_, i) => (
              <style key={i}>{`
                @keyframes graphDash${i} { to { stroke-dashoffset: -22; } }
              `}</style>
            ))}
          </defs>

          {/* Edges */}
          {edges.map((e, i) => {
            const fromPos = POS[e.from];
            const toPos   = POS[e.to];
            if (!fromPos || !toPos) return null;
            return <Edge key={i} from={fromPos} to={toPos} idx={i} />;
          })}

          {/* Nodes */}
          {nodes.map(node => {
            const pos      = POS[node.id];
            const riskLevel = (node.risk_level || 'UNKNOWN').toUpperCase();
            const color     = RISK_COLOR[riskLevel] || RISK_COLOR.UNKNOWN;
            const analyzed  = riskLevel !== 'UNKNOWN';
            if (!pos) return null;

            return (
              <g key={node.id} transform={`translate(${pos.x},${pos.y})`}>
                {/* Glow */}
                <rect width={NODE_W} height={NODE_H} rx="10" fill={color} opacity="0.06" />
                {/* Card */}
                <rect
                  width={NODE_W} height={NODE_H} rx="10"
                  fill="rgba(13,16,32,0.95)"
                  stroke={color} strokeWidth={analyzed ? 1.8 : 1}
                />
                {/* Left accent bar */}
                <rect width="4" height={NODE_H} rx="2" fill={color} opacity="0.8" />
                {/* Label */}
                <text
                  x={NODE_W / 2 + 2} y="21" textAnchor="middle"
                  fill="white" fontSize="12" fontWeight="600"
                  fontFamily="'Space Grotesk',sans-serif"
                >
                  {node.label || node.id}
                </text>
                {/* Risk / port info */}
                <text
                  x={NODE_W / 2 + 2} y="39" textAnchor="middle"
                  fill={color} fontSize="10" fontFamily="'JetBrains Mono',monospace"
                >
                  {analyzed
                    ? `${riskLevel} · ${node.risk_score}/100`
                    : node.port ? `port :${node.port}` : 'Not analysed yet'}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <div className="graph-legend">
        {Object.entries(RISK_COLOR)
          .filter(([k]) => k !== 'UNKNOWN')
          .map(([level, color]) => (
            <span key={level} style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12, color: 'var(--text-dim)' }}>
              <span className="legend-dot" style={{ background: color, boxShadow: `0 0 6px ${color}` }} />
              {level}
            </span>
          ))}
      </div>
    </div>
  );
}
