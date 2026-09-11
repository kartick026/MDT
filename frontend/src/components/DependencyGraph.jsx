import { useEffect, useState, useMemo } from 'react';
import { getGraph } from '../api';

const RISK_COLOR = {
  LOW:      '#00ff88',
  MEDIUM:   '#fbbf24',
  HIGH:     '#f97316',
  CRITICAL: '#ff2d55',
  UNKNOWN:  '#3a3f5c',
};

const NODE_W = 175, NODE_H = 60;

/* Architectural preset positions optimized for balanced, collision-free geometry */
const PRESET_POS = {
  'user-service':         { x: 60,  y: 160 },
  'order-service':        { x: 450, y: 160 },
  'inventory-service':    { x: 840, y: 70  }, // Broken link / dead host (top-right)
  'notification-service': { x: 840, y: 310 }, // Downstream notification dispatch (bottom-right)
  'payment-service':      { x: 450, y: 410 }, // Payment isolated downstream (bottom-center)
  'frontend':             { x: 60,  y: 40  },
  'backend':              { x: 450, y: 40  },
  'local-demo-postgres':  { x: 60,  y: 410 },
};

/**
 * Calculate dynamic node width based on label text length to guarantee text fits with ample padding.
 */
function getNodeWidth(label) {
  const len = (label || '').length;
  if (len <= 14) return 175;
  if (len <= 18) return 195;
  if (len <= 24) return 225;
  if (len <= 30) return 255;
  return Math.min(295, 255 + (len - 30) * 7);
}

/**
 * Intelligent layout for demo fleet and arbitrary dynamic repositories.
 */
function buildPositions(nodes, edges) {
  const positions = {};
  const unplaced = [];

  const nodeMap = {};
  for (const n of nodes) {
    nodeMap[n.id] = n;
  }

  for (const node of nodes) {
    const label = node.label || node.id.replace(/-service$/i, '');
    const w = getNodeWidth(label);
    const h = NODE_H;
    if (PRESET_POS[node.id]) {
      positions[node.id] = { ...PRESET_POS[node.id], w, h };
    } else {
      unplaced.push(node);
    }
  }

  if (unplaced.length === 0) return positions;

  // Layered topological sorting for imported repositories
  const inDegree = {}, outDegree = {};
  nodes.forEach(n => { inDegree[n.id] = 0; outDegree[n.id] = 0; });
  edges.forEach(e => {
    if (inDegree[e.to] !== undefined) inDegree[e.to]++;
    if (outDegree[e.from] !== undefined) outDegree[e.from]++;
  });

  const roots = [], intermediates = [], sinks = [];
  unplaced.forEach(n => {
    if (inDegree[n.id] === 0) roots.push(n.id);
    else if (outDegree[n.id] === 0) sinks.push(n.id);
    else intermediates.push(n.id);
  });

  const layers = [roots, intermediates, sinks].filter(l => l.length > 0);
  const startY = Object.keys(positions).length > 0 ? 460 : 70;
  const layerHeight = 160;

  layers.forEach((layer, layerIdx) => {
    const y = startY + layerIdx * layerHeight;
    // Calculate required column spacing based on actual node widths in this layer
    const layerWidths = layer.map(id => {
      const label = nodeMap[id]?.label || id.replace(/-service$/i, '');
      return getNodeWidth(label);
    });
    const maxLayerNodeW = Math.max(...layerWidths, 175);
    const colSpacing = Math.max(280, maxLayerNodeW + 70);
    const totalW = layer.length * colSpacing;
    const startX = Math.max(70, (960 - totalW) / 2);

    layer.forEach((id, colIdx) => {
      const label = nodeMap[id]?.label || id.replace(/-service$/i, '');
      const w = getNodeWidth(label);
      positions[id] = {
        x: startX + colIdx * colSpacing,
        y: y,
        w: w,
        h: NODE_H,
      };
    });
  });

  return positions;
}

/**
 * High-precision edge geometry calculator.
 * Guarantees:
 * - Unmistakable caller (tail socket) and callee (chevron arrowhead) separation.
 * - Non-overlapping bi-directional lanes with dedicated curvature offsets.
 * - Specialized collision-free arcs for loops and underpass cross-connections.
 */
function computeSmartEdge(fromNode, toNode, isBiDirectional, isReverse) {
  const fw = fromNode.w || NODE_W, fh = fromNode.h || NODE_H;
  const tw = toNode.w || NODE_W, th = toNode.h || NODE_H;

  // 1. SELF-LOOP CASES
  if (fromNode.id === toNode.id || (fromNode.x === toNode.x && fromNode.y === toNode.y)) {
    if (fromNode.id === 'order-service') {
      // Curve UP into the spacious area above order-service
      const fcx = fromNode.x + fw / 2;
      const sx = fcx - 36, sy = fromNode.y;
      const ex = fcx + 36, ey = fromNode.y;
      const c1x = fcx - 46, c1y = fromNode.y - 48;
      const c2x = fcx + 46, c2y = fromNode.y - 48;
      const d = `M ${sx} ${sy} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${ex} ${ey}`;
      return {
        path: d,
        start: { x: sx, y: sy },
        end: { x: ex, y: ey },
        mid: { x: fcx, y: fromNode.y - 36 },
        badgePoint: { x: fcx, y: fromNode.y - 52 },
        tangentAngle: Math.PI / 2, // Straight down into top border
      };
    } else {
      // Loop out to the right margin with generous curvature and clear badge positioning above curve
      const fcy = fromNode.y + fh / 2;
      const sx = fromNode.x + fw, sy = fcy - 16;
      const ex = fromNode.x + fw, ey = fcy + 16;
      const c1x = fromNode.x + fw + 55, c1y = fcy - 45;
      const c2x = fromNode.x + fw + 55, c2y = fcy + 45;
      const d = `M ${sx} ${sy} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${ex} ${ey}`;
      return {
        path: d,
        start: { x: sx, y: sy },
        end: { x: ex, y: ey },
        mid: { x: fromNode.x + fw + 42, y: fcy },
        badgePoint: { x: fromNode.x + fw + 75, y: fcy - 34 },
        tangentAngle: Math.PI, // Straight left into right border
      };
    }
  }

  // 2. SPECIAL UNDERPASS: notification-service -> user-service
  // Sweeps gracefully beneath order-service to avoid crossing through it
  if (fromNode.id === 'notification-service' && toNode.id === 'user-service') {
    const sx = fromNode.x, sy = fromNode.y + fh - 10;
    const ex = toNode.x + fw - 20, ey = toNode.y + fh;
    const mx = 450, my = 350; // Underpass control point
    const d = `M ${sx} ${sy} Q ${mx} ${my} ${ex} ${ey}`;
    const tangentAngle = Math.atan2(ey - my, ex - mx);
    const bx = (sx + 2 * mx + ex) / 4;
    const by = (sy + 2 * my + ey) / 4 + 14;
    return {
      path: d,
      start: { x: sx, y: sy },
      end: { x: ex, y: ey },
      mid: { x: bx, y: by - 14 },
      badgePoint: { x: bx, y: by },
      tangentAngle,
    };
  }

  const fcx = fromNode.x + fw / 2, fcy = fromNode.y + fh / 2;
  const tcx = toNode.x + tw / 2,   tcy = toNode.y + th / 2;
  const dx = tcx - fcx;
  const dy = tcy - fcy;

  let sx, sy, ex, ey, mx, my, badgeX, badgeY;

  // 3. HORIZONTAL CONNECTIONS (e.g. user-service <-> order-service)
  // Dual-lane separation: Rightward traffic on upper lane, Leftward traffic on lower lane
  if (Math.abs(dx) >= Math.abs(dy) * 1.3) {
    if (dx > 0) {
      // Flowing RIGHT (user -> order): UPPER LANE arches UP
      sx = fromNode.x + fw;
      ex = toNode.x;
      const portOffset  = isBiDirectional ? -18 : 0;
      const curveOffset = isBiDirectional ? -55 : 0;
      sy = fcy + portOffset;
      ey = tcy + portOffset;
      mx = (sx + ex) / 2;
      my = (sy + ey) / 2 + curveOffset;
      badgeX = (sx + ex) / 2;
      badgeY = (sy + 2 * my + ey) / 4 - 8;
    } else {
      // Flowing LEFT (order -> user): LOWER LANE arches DOWN
      sx = fromNode.x;
      ex = toNode.x + tw;
      const portOffset  = isBiDirectional ? 18 : 0;
      const curveOffset = isBiDirectional ? 55 : 0;
      sy = fcy + portOffset;
      ey = tcy + portOffset;
      mx = (sx + ex) / 2;
      my = (sy + ey) / 2 + curveOffset;
      badgeX = (sx + ex) / 2;
      badgeY = (sy + 2 * my + ey) / 4 + 8;
    }
  }
  // 4. VERTICAL CONNECTIONS
  else if (Math.abs(dy) >= Math.abs(dx) * 1.3) {
    if (dy > 0) {
      // Flowing DOWN
      sx = fcx + (isBiDirectional ? (isReverse ? 22 : -22) : 0);
      sy = fromNode.y + fh;
      ex = tcx + (isBiDirectional ? (isReverse ? 22 : -22) : 0);
      ey = toNode.y;
      const biOffset = isBiDirectional ? (isReverse ? 45 : -45) : 0;
      mx = (sx + ex) / 2 + biOffset;
      my = (sy + ey) / 2;
      badgeX = mx + (isBiDirectional ? (isReverse ? 14 : -14) : 0);
      badgeY = my;
    } else {
      // Flowing UP
      sx = fcx + (isBiDirectional ? (isReverse ? -22 : 22) : 0);
      sy = fromNode.y;
      ex = tcx + (isBiDirectional ? (isReverse ? -22 : 22) : 0);
      ey = toNode.y + th;
      const biOffset = isBiDirectional ? (isReverse ? -45 : 45) : 0;
      mx = (sx + ex) / 2 + biOffset;
      my = (sy + ey) / 2;
      badgeX = mx + (isBiDirectional ? (isReverse ? -14 : 14) : 0);
      badgeY = my;
    }
  }
  // 5. DIAGONAL CONNECTIONS (e.g. order-service -> inventory-service, order <-> notification)
  else {
    const dist = Math.hypot(dx, dy) || 1;
    const ux = dx / dist, uy = dy / dist;
    // Perpendicular unit normal vector
    const px = -uy, py = ux;

    if (dx > 0 && dy < 0) {
      // Up-Right (order-service -> inventory-service [Broken link])
      sx = fromNode.x + fw;
      sy = fcy - 12;
      ex = toNode.x;
      ey = tcy + 10;
      mx = (sx + ex) / 2;
      my = (sy + ey) / 2 - 24;
      badgeX = mx;
      badgeY = my - 8;
    } else if (isBiDirectional) {
      // Dual-lane diagonal separation:
      // Lane 1 (order -> notification): curves outward to the upper-right
      // Lane 2 (notification -> order): curves outward to the lower-left
      const laneShift = dx > 0 ? -42 : -42;
      sx = dx > 0 ? (fromNode.x + fw) : (fromNode.x);
      sy = fcy + (dx > 0 ? -14 : 14);
      ex = dx > 0 ? (toNode.x) : (toNode.x + tw);
      ey = tcy + (dx > 0 ? -14 : 14);
      mx = (sx + ex) / 2 + px * laneShift;
      my = (sy + ey) / 2 + py * laneShift;
      badgeX = (sx + 2 * mx + ex) / 4 + px * 12;
      badgeY = (sy + 2 * my + ey) / 4 + py * 12;
    } else {
      // General diagonal fallback with normal curve
      sx = fcx + ux * (fw / 2);
      sy = fcy + uy * (fh / 2);
      ex = tcx - ux * (tw / 2);
      ey = tcy - uy * (th / 2);
      mx = (sx + ex) / 2;
      my = (sy + ey) / 2;
      badgeX = mx;
      badgeY = my;
    }
  }

  const d = `M ${sx} ${sy} Q ${mx} ${my} ${ex} ${ey}`;
  const tangentAngle = Math.atan2(ey - my, ex - mx);

  // Placed at the curve apex / midpoint for guaranteed clearance from node borders
  const bx = badgeX !== undefined ? badgeX : (sx + 2 * mx + ex) / 4;
  const by = badgeY !== undefined ? badgeY : (sy + 2 * my + ey) / 4;

  return {
    path: d,
    start: { x: sx, y: sy },
    end: { x: ex, y: ey },
    mid: { x: (sx + 2 * mx + ex) / 4, y: (sy + 2 * my + ey) / 4 },
    badgePoint: { x: bx, y: by },
    tangentAngle,
  };
}

/* Visual relation curve with unmistakable tail socket and directional chevron */
function EdgeCurve({
  fromPos, toPos, fromId, toId, idx, hasBug,
  isDimmed, isHighlighted, isBiDirectional, isReverse,
  isHovered, onHover, onLeave
}) {
  const edgeGeo = useMemo(() => {
    return computeSmartEdge(
      { ...fromPos, id: fromId },
      { ...toPos, id: toId },
      isBiDirectional,
      isReverse
    );
  }, [fromPos, toPos, fromId, toId, isBiDirectional, isReverse]);

  const { path, start, end, tangentAngle } = edgeGeo;

  let strokeColor = hasBug ? '#ff2d55' : 'rgba(0, 212, 255, 0.45)';
  let strokeWidth = hasBug ? '2.4' : '1.8';
  let arrowColor  = hasBug ? '#ff2d55' : '#00d4ff';

  if (isHighlighted || isHovered) {
    strokeColor = hasBug ? '#ff2d55' : '#00f0ff';
    strokeWidth = '2.8';
    arrowColor  = hasBug ? '#ff2d55' : '#00f0ff';
  }

  // Directional aerodynamic chevron arrowhead (sharp tip + recessed notch)
  const arrowLen = 12;
  const arrowWidth = 6.5;
  const notchDepth = 3.5;
  const cosT = Math.cos(tangentAngle);
  const sinT = Math.sin(tangentAngle);
  const tipX = end.x;
  const tipY = end.y;

  const p1 = { x: tipX, y: tipY };
  const p2 = {
    x: tipX - arrowLen * cosT + arrowWidth * sinT,
    y: tipY - arrowLen * sinT - arrowWidth * cosT,
  };
  const p3 = {
    x: tipX - (arrowLen - notchDepth) * cosT,
    y: tipY - (arrowLen - notchDepth) * sinT,
  };
  const p4 = {
    x: tipX - arrowLen * cosT - arrowWidth * sinT,
    y: tipY - arrowLen * sinT + arrowWidth * cosT,
  };

  return (
    <g
      className="graph-edge-group"
      onMouseEnter={onHover}
      onMouseLeave={onLeave}
      style={{
        opacity: isDimmed ? 0.15 : 1,
        transition: 'opacity 0.25s ease',
        cursor: 'pointer',
      }}
    >
      {/* Invisible wider stroke for easy hover detection */}
      <path
        d={path}
        fill="none"
        stroke="transparent"
        strokeWidth="16"
      />

      {/* Visual Relation Path with directional animated dashes strictly toward Head */}
      <path
        d={path}
        fill="none"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        strokeDasharray={hasBug ? "5 4" : "7 5"}
        style={{
          animation: `flowDash${idx} ${hasBug ? '1.2s' : '2.4s'} linear infinite`,
          filter: (isHighlighted || isHovered) ? `drop-shadow(0 0 6px ${strokeColor})` : 'none',
        }}
      />

      {/* TAIL: Unmistakable Concentric Caller Socket Port */}
      <g className="edge-tail" transform={`translate(${start.x}, ${start.y})`}>
        <circle r="5.5" fill="#080b18" stroke={strokeColor} strokeWidth="1.8" />
        <circle r="2.2" fill={arrowColor} />
      </g>

      {/* HEAD: Direction-aligned Aerodynamic Chevron Arrowhead */}
      <polygon
        points={`${p1.x},${p1.y} ${p2.x},${p2.y} ${p3.x},${p3.y} ${p4.x},${p4.y}`}
        fill={arrowColor}
        stroke={arrowColor}
        strokeWidth="0.8"
        style={{
          filter: (hasBug || isHighlighted || isHovered) ? `drop-shadow(0 0 5px ${arrowColor})` : 'none',
        }}
      />
    </g>
  );
}

/* Endpoint and Broken Link badges — Rendered in Top Layer to ALWAYS sit on top of nodes */
function EdgeBadge({
  fromPos, toPos, fromId, toId, hasBug, endpoint,
  isDimmed, isHighlighted, isBiDirectional, isReverse,
  isHovered, onHover, onLeave, showEndpoints
}) {
  const edgeGeo = useMemo(() => {
    return computeSmartEdge(
      { ...fromPos, id: fromId },
      { ...toPos, id: toId },
      isBiDirectional,
      isReverse
    );
  }, [fromPos, toPos, fromId, toId, isBiDirectional, isReverse]);

  const { mid, badgePoint } = edgeGeo;

  // Determine badge visibility:
  // - Broken link ALWAYS visible
  // - Normal edges visible on edge hover OR when showEndpoints is toggled OR when explicitly highlighted
  const showBadge = hasBug || isHovered || showEndpoints || (isHighlighted && Boolean(endpoint));

  if (!showBadge) return null;

  return (
    <g
      className="graph-badge-group"
      onMouseEnter={onHover}
      onMouseLeave={onLeave}
      style={{
        opacity: isDimmed ? 0.15 : 1,
        transition: 'opacity 0.25s ease',
        cursor: 'pointer',
      }}
    >
      {hasBug ? (
        // Broken Link Badge (centered on the red edge)
        <g transform={`translate(${mid.x}, ${mid.y})`}>
          <rect
            x="-50" y="-11" width="100" height="21" rx="10"
            fill="#ff2d55"
            stroke="#ffffff"
            strokeWidth="1"
            style={{ filter: 'drop-shadow(0 0 10px rgba(255,45,85,0.7))' }}
          />
          <text
            x="0" y="3.5" textAnchor="middle"
            fill="#ffffff" fontSize="9.5" fontWeight="700"
            fontFamily="'JetBrains Mono',monospace"
          >
            ⚠ BROKEN LINK
          </text>
        </g>
      ) : (
        // Regular Endpoint Badge (staggered at t = 0.65 to completely eliminate collision)
        endpoint && (
          <g transform={`translate(${badgePoint.x}, ${badgePoint.y})`}>
            <rect
              x={-endpoint.length * 3.4 - 10} y="-10"
              width={endpoint.length * 6.8 + 20} height="20" rx="6"
              fill="#0a0e1e"
              stroke={isHovered ? "#00f0ff" : "rgba(0,212,255,0.5)"}
              strokeWidth={isHovered ? "1.5" : "1"}
              style={{
                filter: 'drop-shadow(0 2px 8px rgba(0,0,0,0.85))',
                transition: 'all 0.15s ease'
              }}
            />
            <text
              x="0" y="3.5" textAnchor="middle"
              fill={isHovered ? "#ffffff" : "#00d4ff"} fontSize="9.5" fontWeight="600"
              fontFamily="'JetBrains Mono',monospace"
            >
              {endpoint}
            </text>
          </g>
        )
      )}
    </g>
  );
}

export default function DependencyGraph() {
  const [data, setData]               = useState(null);
  const [loading, setLoading]         = useState(true);
  const [error, setError]             = useState(null);
  const [zoom, setZoom]               = useState(1);
  const [selectedNode, setSelected]   = useState(null);
  const [hoveredEdge, setHoveredEdge] = useState(null);
  const [searchQuery, setSearch]      = useState('');
  const [showEndpoints, setShowEnd]   = useState(false); // Clean view by default with toggle

  useEffect(() => {
    getGraph()
      .then(d => { setData(d); setError(null); })
      .catch(() => setError('Could not load dependency graph from backend'))
      .finally(() => setLoading(false));
  }, []);

  const nodes = useMemo(() => data?.nodes || [], [data]);
  const edges = useMemo(() => data?.edges || [], [data]);

  // Index reverse edges for bi-directional lane separation
  const edgePairMap = useMemo(() => {
    const map = new Set();
    edges.forEach(e => map.add(`${e.to}->${e.from}`));
    return map;
  }, [edges]);

  const POS = useMemo(() => buildPositions(nodes, edges), [nodes, edges]);

  // Compute connected neighbors for blast radius
  const connectedIds = useMemo(() => {
    if (!selectedNode) return null;
    const ids = new Set([selectedNode]);
    edges.forEach(e => {
      if (e.from === selectedNode) ids.add(e.to);
      if (e.to === selectedNode) ids.add(e.from);
    });
    return ids;
  }, [selectedNode, edges]);

  const maxY = Object.values(POS).reduce((m, p) => Math.max(m, p.y + (p.h || NODE_H) + 60), 520);
  const maxX = Object.values(POS).reduce((m, p) => Math.max(m, p.x + (p.w || NODE_W) + 200), 1260);
  const viewBox = `0 0 ${maxX} ${maxY}`;

  if (loading) return <div className="state-loading"><div className="spinner" /><span>Loading topology graph…</span></div>;
  if (error)   return <div className="state-error"><span>⚠</span><span>{error}</span></div>;

  if (!nodes.length) {
    return (
      <div className="card state-empty">
        <p>No services in the graph yet. Run an analysis to populate it.</p>
      </div>
    );
  }

  const activeSelected = nodes.find(n => n.id === selectedNode);

  return (
    <div className="graph-card">
      {/* Top Header & Toolbar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px', marginBottom: '14px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <h2 className="panel-title" style={{ fontSize: '18px', fontWeight: 600, margin: 0 }}>
              Service Dependency Topology
            </h2>
            <span style={{ fontSize: '11px', color: 'var(--cyan)', background: 'rgba(0,212,255,0.12)', border: '1px solid rgba(0,212,255,0.3)', padding: '2px 8px', borderRadius: '10px', fontWeight: 600 }}>
              {nodes.length} Nodes · {edges.length} Dependencies
            </span>
          </div>
          <p style={{ margin: '4px 0 0', fontSize: '12px', color: 'var(--text-dim)' }}>
            Circular socket = Caller (Tail) → Directional chevron = Callee (Head).
          </p>
        </div>

        {/* Toolbar controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          {/* Search */}
          <input
            type="text"
            placeholder="Filter service…"
            value={searchQuery}
            onChange={e => setSearch(e.target.value)}
            style={{
              padding: '5px 10px',
              fontSize: '12px',
              background: 'rgba(255,255,255,0.05)',
              border: '1px solid rgba(255,255,255,0.12)',
              borderRadius: '6px',
              color: '#fff',
              outline: 'none',
              width: '130px'
            }}
          />

          {/* Toggle Endpoints */}
          <button
            onClick={() => setShowEnd(prev => !prev)}
            title="Toggle endpoint route labels on all relation curves"
            style={{
              background: showEndpoints ? 'rgba(0,212,255,0.18)' : 'rgba(255,255,255,0.05)',
              border: `1px solid ${showEndpoints ? 'var(--cyan)' : 'rgba(255,255,255,0.12)'}`,
              color: showEndpoints ? 'var(--cyan)' : 'var(--text-dim)',
              padding: '5px 10px',
              borderRadius: '6px',
              fontSize: '11.5px',
              fontWeight: 500,
              cursor: 'pointer',
              transition: 'all 0.2s',
            }}
          >
            {showEndpoints ? '🏷 Endpoints: ON' : '🏷 Endpoints: OFF'}
          </button>

          {/* Zoom controls */}
          <div style={{ display: 'flex', alignItems: 'center', background: 'rgba(255,255,255,0.05)', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.12)' }}>
            <button
              onClick={() => setZoom(z => Math.max(0.6, z - 0.15))}
              title="Zoom out"
              style={{ background: 'none', border: 'none', color: '#fff', padding: '5px 9px', cursor: 'pointer', fontSize: '13px' }}
            >
              −
            </button>
            <span style={{ fontSize: '11px', color: '#a0a5b8', padding: '5px 2px', minWidth: '38px', textAlign: 'center', userSelect: 'none' }}>
              {Math.round(zoom * 100)}%
            </span>
            <button
              onClick={() => setZoom(z => Math.min(2.0, z + 0.15))}
              title="Zoom in"
              style={{ background: 'none', border: 'none', color: '#fff', padding: '5px 9px', cursor: 'pointer', fontSize: '13px' }}
            >
              +
            </button>
            <button
              onClick={() => { setZoom(1); setSelected(null); setSearch(''); }}
              title="Reset view"
              style={{ background: 'none', borderLeft: '1px solid rgba(255,255,255,0.1)', color: '#00d4ff', padding: '5px 9px', cursor: 'pointer', fontSize: '11px' }}
            >
              ↺
            </button>
          </div>
        </div>
      </div>

      {/* Selected Node Inspector Banner */}
      {selectedNode && (
        <div style={{
          background: activeSelected?.is_broken ? 'rgba(255, 45, 85, 0.12)' : 'rgba(0, 212, 255, 0.08)',
          border: `1px solid ${activeSelected?.is_broken ? 'rgba(255, 45, 85, 0.35)' : 'rgba(0, 212, 255, 0.25)'}`,
          borderRadius: '8px',
          padding: '8px 14px',
          marginBottom: '12px',
          fontSize: '12px',
          color: '#e2e8f0',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '8px'
        }}>
          <div>
            <strong>{activeSelected?.label || selectedNode}</strong>
            {activeSelected?.is_broken ? (
              <span style={{ color: '#ff2d55', fontWeight: 700, marginLeft: '8px' }}>
                ⚠ UNRESOLVED BROKEN LINK NODE (Dead Host / Connection Refused)
              </span>
            ) : (
              <span style={{ color: 'var(--cyan)', marginLeft: '8px' }}>
                · Direct blast radius: {connectedIds ? connectedIds.size - 1 : 0} services
              </span>
            )}
          </div>
          <button
            onClick={() => setSelected(null)}
            className="btn btn-ghost"
            style={{ padding: '2px 8px', fontSize: '11px', color: '#00d4ff' }}
          >
            Clear Highlight ✕
          </button>
        </div>
      )}

      {/* Interactive Hovered Edge Details Bar — Fixed Height prevents layout shift & hover flickering */}
      <div style={{
        minHeight: '34px',
        height: '34px',
        background: hoveredEdge
          ? (hoveredEdge.has_bug ? 'rgba(255,45,85,0.15)' : 'rgba(0, 212, 255, 0.1)')
          : 'rgba(255, 255, 255, 0.02)',
        border: `1px solid ${hoveredEdge
          ? (hoveredEdge.has_bug ? '#ff2d55' : 'rgba(0, 212, 255, 0.3)')
          : 'rgba(255, 255, 255, 0.06)'}`,
        borderRadius: '6px',
        padding: '0 14px',
        marginBottom: '10px',
        fontSize: '11.5px',
        fontFamily: "'JetBrains Mono', monospace",
        color: '#ffffff',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        boxSizing: 'border-box',
        transition: 'background 0.2s ease, border-color 0.2s ease',
      }}>
        {hoveredEdge ? (
          <>
            <span style={{ color: 'var(--text-dim)' }}>RELATION:</span>
            <strong>{hoveredEdge.from}</strong>
            <span style={{ color: hoveredEdge.has_bug ? '#ff2d55' : 'var(--cyan)' }}>
              ──({hoveredEdge.type || 'http'}: {hoveredEdge.endpoint || '/'})──►
            </span>
            <strong>{hoveredEdge.to}</strong>
            {hoveredEdge.has_bug && (
              <span style={{ color: '#ff2d55', fontWeight: 700, marginLeft: 'auto' }}>
                ⚠ DEAD HOST / UNRESOLVED
              </span>
            )}
          </>
        ) : (
          <span style={{ color: 'var(--text-faint)', fontSize: '11px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span>💡</span> Hover over any relation edge or service node to inspect protocol endpoints and blast radius
          </span>
        )}
      </div>

      {/* Main Graph SVG Viewport */}
      <div style={{
        overflow: 'auto',
        maxHeight: '560px',
        borderRadius: '10px',
        border: '1px solid rgba(255,255,255,0.08)',
        background: 'radial-gradient(ellipse at 50% 30%, #0c1022 0%, #050711 100%)',
        position: 'relative'
      }}>
        <div style={{ transform: `scale(${zoom})`, transformOrigin: 'top left', transition: 'transform 0.15s ease' }}>
          <svg
            className="graph-svg"
            viewBox={viewBox}
            preserveAspectRatio="xMidYMid meet"
            style={{ width: maxX, height: maxY, display: 'block' }}
          >
            <defs>
              {/* Flow dash keyframes */}
              {edges.map((_, i) => (
                <style key={i}>{`
                  @keyframes flowDash${i} {
                    from { stroke-dashoffset: 24; }
                    to { stroke-dashoffset: 0; }
                  }
                `}</style>
              ))}

              {/* Node drop shadows */}
              <filter id="nodeGlow" x="-20%" y="-20%" width="140%" height="140%">
                <feDropShadow dx="0" dy="4" stdDeviation="6" floodOpacity="0.35" />
              </filter>
              <filter id="brokenGlow" x="-30%" y="-30%" width="160%" height="160%">
                <feDropShadow dx="0" dy="0" stdDeviation="8" floodColor="#ff2d55" floodOpacity="0.55" />
              </filter>
            </defs>

            {/* Subtle Grid Pattern Background */}
            <pattern id="graphGrid" width="40" height="40" patternUnits="userSpaceOnUse">
              <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(255,255,255,0.022)" strokeWidth="1" />
            </pattern>
            <rect width={maxX} height={maxY} fill="url(#graphGrid)" />

            {/* Layer 1: Relations / Edges (paths, sockets, chevrons) */}
            <g className="graph-layer-edges">
              {edges.map((e, i) => {
                const fromPos = POS[e.from];
                const toPos   = POS[e.to];
                if (!fromPos || !toPos) return null;

                const isRelevant = !connectedIds || (connectedIds.has(e.from) && connectedIds.has(e.to));
                const isHigh = selectedNode && (e.from === selectedNode || e.to === selectedNode);
                const isBi = edgePairMap.has(`${e.to}->${e.from}`);
                const isRev = e.from > e.to;
                const isEdgeHovered = hoveredEdge && hoveredEdge.from === e.from && hoveredEdge.to === e.to;

                return (
                  <EdgeCurve
                    key={`curve-${e.from}->${e.to}-${i}`}
                    fromPos={fromPos}
                    toPos={toPos}
                    fromId={e.from}
                    toId={e.to}
                    idx={i}
                    hasBug={Boolean(e.has_bug)}
                    isDimmed={Boolean(connectedIds && !isRelevant)}
                    isHighlighted={Boolean(isHigh)}
                    isBiDirectional={isBi}
                    isReverse={isRev}
                    isHovered={Boolean(isEdgeHovered)}
                    onHover={() => setHoveredEdge(e)}
                    onLeave={() => setHoveredEdge(null)}
                  />
                );
              })}
            </g>

            {/* Layer 2: Service Nodes */}
            <g className="graph-layer-nodes">
              {nodes.map(node => {
                const pos       = POS[node.id];
                const riskLevel = (node.risk_level || 'UNKNOWN').toUpperCase();
                const isBroken  = Boolean(node.is_broken || node.status === 'offline');
                const color     = isBroken ? '#ff2d55' : (RISK_COLOR[riskLevel] || RISK_COLOR.UNKNOWN);
                const analyzed  = riskLevel !== 'UNKNOWN';
                if (!pos) return null;

                const isMatchesSearch = !searchQuery || node.id.toLowerCase().includes(searchQuery.toLowerCase());
                const isDimmed = (connectedIds && !connectedIds.has(node.id)) || (!isMatchesSearch);
                const isSelected = selectedNode === node.id;

                const nodeW = pos.w || NODE_W;
                const nodeH = pos.h || NODE_H;
                const rawTitle = node.label || node.id.replace(/-service$/i, '');
                const title = rawTitle.length > 36 ? rawTitle.slice(0, 34).trim() + '…' : rawTitle;
                const titleLen = title.length;
                let titleFontSize = 13;
                if (titleLen > 28) titleFontSize = 11.5;
                else if (titleLen > 20) titleFontSize = 12;

                return (
                  <g
                    key={node.id}
                    transform={`translate(${pos.x},${pos.y})`}
                    onClick={() => setSelected(prev => prev === node.id ? null : node.id)}
                    style={{
                      cursor: 'pointer',
                      opacity: isDimmed ? 0.2 : 1,
                      transition: 'all 0.25s ease',
                    }}
                  >
                    {/* Outer Ambient Glow */}
                    <rect
                      width={nodeW}
                      height={nodeH}
                      rx="12"
                      fill={color}
                      opacity={isSelected ? 0.3 : (isBroken ? 0.22 : 0.06)}
                      filter={isBroken ? "url(#brokenGlow)" : "url(#nodeGlow)"}
                    />

                    {/* Main Card Background */}
                    <rect
                      width={nodeW}
                      height={nodeH}
                      rx="12"
                      fill={isBroken ? "rgba(26, 8, 14, 0.96)" : "rgba(11, 15, 30, 0.95)"}
                      stroke={isSelected ? '#00d4ff' : color}
                      strokeWidth={isSelected ? 2.5 : (isBroken ? 2 : 1.5)}
                      strokeDasharray={isBroken ? "5 4" : "none"}
                    />

                    {/* Left Accent Color Bar */}
                    <rect
                      x="2" y="6"
                      width="4.5" height={nodeH - 12}
                      rx="2"
                      fill={color}
                    />

                    {/* Node Title */}
                    <text
                      x={nodeW / 2 + 1} y="24" textAnchor="middle"
                      fill="#ffffff" fontSize={titleFontSize} fontWeight="600"
                      fontFamily="'JetBrains Mono',monospace"
                      style={{ letterSpacing: titleLen > 24 ? '-0.3px' : 'normal' }}
                    >
                      {title}
                    </text>

                    {/* Node Status / Metric */}
                    {isBroken ? (
                      <text
                        x={nodeW / 2 + 1} y="43" textAnchor="middle"
                        fill="#ff2d55" fontSize="10" fontWeight="700"
                        fontFamily="'JetBrains Mono',monospace"
                      >
                        ⚠ BROKEN LINK · :9999
                      </text>
                    ) : (
                      <text
                        x={nodeW / 2 + 1} y="43" textAnchor="middle"
                        fill={color} fontSize="10.5" fontWeight="500"
                        fontFamily="'JetBrains Mono',monospace"
                      >
                        {analyzed
                          ? `${riskLevel} · ${node.risk_score}/100`
                          : `ONLINE · :${node.port || 8000}`}
                      </text>
                    )}

                    {/* Live Status indicator dot (top right) */}
                    <circle
                      cx={nodeW - 12} cy="14" r="3.5"
                      fill={isBroken ? '#ff2d55' : '#00ff88'}
                      style={{
                        filter: isBroken ? 'drop-shadow(0 0 4px #ff2d55)' : 'drop-shadow(0 0 3px #00ff88)',
                      }}
                    />
                  </g>
                );
              })}
            </g>

            {/* Layer 3: Endpoint Badges & Broken Link Indicators (ALWAYS on top of nodes and edges) */}
            <g className="graph-layer-badges">
              {edges.map((e, i) => {
                const fromPos = POS[e.from];
                const toPos   = POS[e.to];
                if (!fromPos || !toPos) return null;

                const isRelevant = !connectedIds || (connectedIds.has(e.from) && connectedIds.has(e.to));
                const isHigh = selectedNode && (e.from === selectedNode || e.to === selectedNode);
                const isBi = edgePairMap.has(`${e.to}->${e.from}`);
                const isRev = e.from > e.to;
                const isEdgeHovered = hoveredEdge && hoveredEdge.from === e.from && hoveredEdge.to === e.to;

                return (
                  <EdgeBadge
                    key={`badge-${e.from}->${e.to}-${i}`}
                    fromPos={fromPos}
                    toPos={toPos}
                    fromId={e.from}
                    toId={e.to}
                    hasBug={Boolean(e.has_bug)}
                    endpoint={e.endpoint}
                    isDimmed={Boolean(connectedIds && !isRelevant)}
                    isHighlighted={Boolean(isHigh)}
                    isBiDirectional={isBi}
                    isReverse={isRev}
                    isHovered={Boolean(isEdgeHovered)}
                    onHover={() => setHoveredEdge(e)}
                    onLeave={() => setHoveredEdge(null)}
                    showEndpoints={showEndpoints}
                  />
                );
              })}
            </g>
          </svg>
        </div>
      </div>

      {/* Enhanced Legend and Direction Guide */}
      <div className="graph-legend" style={{ marginTop: '14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flexWrap: 'wrap' }}>
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
          <span style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12, color: 'var(--red)', fontWeight: '700' }}>
            <span style={{ width: 14, height: 2, background: 'var(--red)', display: 'inline-block' }} />
            ⚠ Broken Link Node / Dead Host
          </span>
        </div>

        {/* Visual Arrowhead / Tail Guide */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '4px 12px', background: 'rgba(255,255,255,0.04)', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.08)', fontSize: '11px', color: 'var(--text-dim)' }}>
          <span>Relation Guide:</span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: 'var(--text)' }}>
            <span style={{ width: 9, height: 9, borderRadius: '50%', border: '1.8px solid #00d4ff', background: '#080b18', display: 'inline-block' }} />
            Tail (Caller)
          </span>
          <span style={{ color: 'var(--cyan)' }}>────────►</span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: 'var(--text)' }}>
            <span style={{ width: 0, height: 0, borderTop: '4px solid transparent', borderBottom: '4px solid transparent', borderLeft: '8px solid #00d4ff', display: 'inline-block' }} />
            Head (Callee)
          </span>
        </div>
      </div>
    </div>
  );
}
