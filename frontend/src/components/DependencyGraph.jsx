import { useEffect, useState, useMemo } from 'react';
import { getGraph } from '../api';

const RISK_COLOR = {
  LOW:      '#00ff88',
  MEDIUM:   '#fbbf24',
  HIGH:     '#f97316',
  CRITICAL: '#ff2d55',
  UNKNOWN:  '#3a3f5c',
};

const NODE_W = 160, NODE_H = 52;

/* Predefined positions for known services */
const PRESET_POS = {
  'user-service':         { x: 230, y: 40  },
  'order-service':        { x: 230, y: 175 },
  'payment-service':      { x: 80,  y: 310 },
  'notification-service': { x: 380, y: 310 },
};

/**
 * Build a position map for all nodes.
 */
function buildPositions(nodes) {
  const positions = {};
  const unknown = [];
  let hasPresets = false;

  for (const node of nodes) {
    if (PRESET_POS[node.id]) {
      positions[node.id] = PRESET_POS[node.id];
      hasPresets = true;
    } else {
      unknown.push(node.id);
    }
  }

  // Lay unknown nodes out in a clean multi-column grid
  const cols = unknown.length > 4 ? 3 : 2;
  const startY = hasPresets ? 420 : 60;
  const colSpacing = cols === 3 ? 200 : 260;
  const rowSpacing = 130;
  const startX = cols === 3 ? 25 : 80;

  unknown.forEach((id, i) => {
    const r = Math.floor(i / cols);
    const c = i % cols;
    positions[id] = {
      x: startX + c * colSpacing,
      y: startY + r * rowSpacing,
    };
  });

  return positions;
}

/* Animated dashed arrow between two nodes */
function Edge({ from, to, idx, hasBug, isDimmed, isHighlighted }) {
  const fx = from.x + NODE_W / 2, fy = from.y + NODE_H;
  const tx = to.x   + NODE_W / 2, ty = to.y;
  const mx = (fx + tx) / 2,       my = (fy + ty) / 2 - 20;
  const d = `M ${fx} ${fy} Q ${mx} ${my} ${tx} ${ty}`;

  let strokeColor = hasBug ? '#ff2d55' : 'rgba(0,212,255,0.22)';
  let strokeWidth = hasBug ? '2.5' : '1.5';
  let fillColor   = hasBug ? '#ff2d55' : 'rgba(0,212,255,0.4)';

  if (isHighlighted) {
    strokeColor = hasBug ? '#ff2d55' : '#00d4ff';
    strokeWidth = '2.5';
    fillColor = hasBug ? '#ff2d55' : '#00d4ff';
  }

  return (
    <g style={{ opacity: isDimmed ? 0.2 : 1, transition: 'opacity 0.2s ease' }}>
      <path
        d={d} fill="none" stroke={strokeColor} strokeWidth={strokeWidth}
        strokeDasharray={hasBug ? "4 4" : "6 5"}
        style={{ animation: `graphDash${idx} ${hasBug ? '1.5s' : '3s'} linear infinite` }}
      />
      <polygon
        points={`${tx},${ty} ${tx - 5},${ty - 10} ${tx + 5},${ty - 10}`}
        fill={fillColor}
      />
      {hasBug && (
        <text x={mx} y={my} fill="#ff2d55" fontSize="10" fontWeight="bold" textAnchor="middle">
          ⚠ Broken Link
        </text>
      )}
    </g>
  );
}

export default function DependencyGraph() {
  const [data, setData]             = useState(null);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);
  const [zoom, setZoom]             = useState(1);
  const [selectedNode, setSelected] = useState(null);
  const [searchQuery, setSearch]    = useState('');

  useEffect(() => {
    getGraph()
      .then(d => { setData(d); setError(null); })
      .catch(() => setError('Could not load dependency graph from backend'))
      .finally(() => setLoading(false));
  }, []);

  const nodes = useMemo(() => data?.nodes || [], [data]);
  const edges = useMemo(() => data?.edges || [], [data]);

  const POS = useMemo(() => buildPositions(nodes), [nodes]);

  // Compute connected neighbors for selected node
  const connectedIds = useMemo(() => {
    if (!selectedNode) return null;
    const ids = new Set([selectedNode]);
    edges.forEach(e => {
      if (e.from === selectedNode) ids.add(e.to);
      if (e.to === selectedNode) ids.add(e.from);
    });
    return ids;
  }, [selectedNode, edges]);

  const maxY = Object.values(POS).reduce((m, p) => Math.max(m, p.y + NODE_H + 40), 450);
  const maxX = Object.values(POS).reduce((m, p) => Math.max(m, p.x + NODE_W + 40), 620);
  const viewBox = `0 0 ${maxX} ${maxY}`;

  if (loading) return <div className="state-loading"><div className="spinner" /><span>Loading graph…</span></div>;
  if (error)   return <div className="state-error"><span>⚠</span><span>{error}</span></div>;

  if (!nodes.length) {
    return (
      <div className="card state-empty">
        <p>No services in the graph yet. Run an analysis to populate it.</p>
      </div>
    );
  }

  return (
    <div className="graph-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px', marginBottom: '16px' }}>
        <div>
          <p className="text-dim text-sm" style={{ margin: 0 }}>
            Arrows show dependency direction (A → B means A calls B). Click a node to inspect its blast radius.
          </p>
        </div>

        {/* Toolbar: Search, Zoom, Reset */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <input
            type="text"
            placeholder="Filter service..."
            value={searchQuery}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              padding: '6px 10px',
              fontSize: '12px',
              borderRadius: '6px',
              border: '1px solid rgba(255,255,255,0.12)',
              background: '#0a0d1a',
              color: '#fff',
              outline: 'none',
              width: '140px'
            }}
          />

          <div style={{ display: 'flex', background: 'rgba(255,255,255,0.06)', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.1)' }}>
            <button
              onClick={() => setZoom(z => Math.max(0.6, z - 0.15))}
              title="Zoom out"
              style={{ background: 'none', border: 'none', color: '#fff', padding: '5px 9px', cursor: 'pointer', fontSize: '13px' }}
            >
              −
            </button>
            <span style={{ fontSize: '11px', color: '#a0a5b8', padding: '5px 4px', minWidth: '40px', textAlign: 'center', userSelect: 'none' }}>
              {Math.round(zoom * 100)}%
            </span>
            <button
              onClick={() => setZoom(z => Math.min(1.8, z + 0.15))}
              title="Zoom in"
              style={{ background: 'none', border: 'none', color: '#fff', padding: '5px 9px', cursor: 'pointer', fontSize: '13px' }}
            >
              +
            </button>
            <button
              onClick={() => { setZoom(1); setSelected(null); setSearch(''); }}
              title="Reset view"
              style={{ background: 'none', borderLeft: '1px solid rgba(255,255,255,0.1)', color: '#00d4ff', padding: '5px 9px', cursor: 'pointer', fontSize: '12px' }}
            >
              ↺
            </button>
          </div>
        </div>
      </div>

      {selectedNode && (
        <div style={{
          background: 'rgba(0, 212, 255, 0.08)',
          border: '1px solid rgba(0, 212, 255, 0.25)',
          borderRadius: '8px',
          padding: '8px 14px',
          marginBottom: '14px',
          fontSize: '12px',
          color: '#e2e8f0',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <span>
            Highlighting blast radius for <strong>{selectedNode}</strong> ({connectedIds ? connectedIds.size - 1 : 0} direct dependencies)
          </span>
          <button
            onClick={() => setSelected(null)}
            style={{ background: 'none', border: 'none', color: '#00d4ff', cursor: 'pointer', fontSize: '12px' }}
          >
            Clear Highlight ✕
          </button>
        </div>
      )}

      <div style={{ overflow: 'auto', maxHeight: '580px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.06)', background: '#070913' }}>
        <div style={{ transform: `scale(${zoom})`, transformOrigin: 'top left', transition: 'transform 0.15s ease' }}>
          <svg className="graph-svg" viewBox={viewBox} preserveAspectRatio="xMidYMid meet" style={{ width: maxX, height: maxY }}>
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

              const isRelevant = !connectedIds || (connectedIds.has(e.from) && connectedIds.has(e.to));
              const isHigh = selectedNode && (e.from === selectedNode || e.to === selectedNode);

              return (
                <Edge
                  key={i}
                  from={fromPos}
                  to={toPos}
                  idx={i}
                  hasBug={Boolean(e.has_bug)}
                  isDimmed={Boolean(connectedIds && !isRelevant)}
                  isHighlighted={Boolean(isHigh)}
                />
              );
            })}

            {/* Nodes */}
            {nodes.map(node => {
              const pos       = POS[node.id];
              const riskLevel = (node.risk_level || 'UNKNOWN').toUpperCase();
              const color     = RISK_COLOR[riskLevel] || RISK_COLOR.UNKNOWN;
              const analyzed  = riskLevel !== 'UNKNOWN';
              if (!pos) return null;

              const isMatchesSearch = !searchQuery || node.id.toLowerCase().includes(searchQuery.toLowerCase());
              const isDimmed = (connectedIds && !connectedIds.has(node.id)) || (!isMatchesSearch);
              const isSelected = selectedNode === node.id;

              return (
                <g
                  key={node.id}
                  transform={`translate(${pos.x},${pos.y})`}
                  onClick={() => setSelected(prev => prev === node.id ? null : node.id)}
                  style={{
                    cursor: 'pointer',
                    opacity: isDimmed ? 0.25 : 1,
                    transition: 'all 0.2s ease',
                  }}
                >
                  {/* Glow */}
                  <rect
                    width={NODE_W}
                    height={NODE_H}
                    rx="10"
                    fill={color}
                    opacity={isSelected ? 0.25 : 0.06}
                  />
                  {/* Card */}
                  <rect
                    width={NODE_W}
                    height={NODE_H}
                    rx="10"
                    fill="rgba(13,16,32,0.95)"
                    stroke={isSelected ? '#00d4ff' : color}
                    strokeWidth={isSelected ? 2.5 : (analyzed ? 1.8 : 1)}
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
                      : `UNANALYZED · :${node.port || 8000}`}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
      </div>

      <div className="graph-legend" style={{ marginTop: '16px' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12, color: 'var(--text-dim)' }}>
          <span className="legend-dot" style={{ background: '#3a3f5c', border: '1px solid rgba(255,255,255,0.2)' }} />
          UNANALYZED
        </span>
        {Object.entries(RISK_COLOR)
          .filter(([k]) => k !== 'UNKNOWN')
          .map(([level, color]) => (
            <span key={level} style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12, color: 'var(--text-dim)' }}>
              <span className="legend-dot" style={{ background: color, boxShadow: `0 0 6px ${color}` }} />
              {level}
            </span>
          ))}
        <span style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12, color: 'var(--red)', fontWeight: '600' }}>
          <span style={{ width: 14, height: 2, background: 'var(--red)', display: 'inline-block' }} />
          Broken Link (404/Port Mismatch)
        </span>
      </div>
    </div>
  );
}
