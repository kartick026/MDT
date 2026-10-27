import { useEffect, useState, useMemo, useRef, useCallback, memo } from 'react';
import { getGraph } from '../api';
import { AlertTriangle, Info, Tags } from 'lucide-react';
import CustomSelect from './CustomSelect';


const RISK_COLOR = {
  LOW:      '#236848',
  MEDIUM:   '#815a10',
  HIGH:     '#9b4b19',
  CRITICAL: '#ac3449',
  UNKNOWN:  '#586875',
};

import { NODE_W, NODE_H, edgeLabel, fitGraph } from '../utils/graphLayout';
import { startLayout } from '../utils/graphLayoutClient';
import { groupRelations, relationDescription } from '../utils/graphRelations';
import { snapshotGraph } from '../utils/graphData';

const EdgeCurve = memo(function EdgeCurve({
  edge, edgeIndex, edgeGeo, hasBug, isDimmed, isHighlighted, isHovered, onHover, onLeave, onInspect
}) {
  const { path, start, end, tangentAngle } = edgeGeo;

  let strokeColor = hasBug ? '#ac3449' : 'rgba(23, 107, 104, 0.55)';
  let strokeWidth = hasBug ? '2.4' : '1.8';
  let arrowColor  = hasBug ? '#ac3449' : '#176b68';

  if (isHighlighted || isHovered) {
    strokeColor = hasBug ? '#ac3449' : '#176b68';
    strokeWidth = '2.8';
    arrowColor  = hasBug ? '#ac3449' : '#176b68';
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
      data-edge-index={edgeIndex}
      tabIndex={0}
      role="button"
      aria-label={`Inspect ${edge.from} to ${edge.to}, ${relationDescription(edge)}`}
      onClick={() => onInspect(edge)}
      onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onInspect(edge); } }}
      onPointerEnter={() => onHover(edge)}
      onPointerLeave={onLeave}
      onFocus={() => onHover(edge)}
      onBlur={onLeave}
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
        strokeWidth="12"
        pointerEvents="stroke"
        vectorEffect="non-scaling-stroke"
        className="graph-edge-hit"
      />

      {/* Clearance makes crossings distinct from actual junctions. */}
      <path d={path} fill="none" stroke="#e2e9ee" strokeWidth="7" strokeLinejoin="round" strokeLinecap="round" pointerEvents="none" />
      {/* Visual Relation Path with directional animated dashes strictly toward Head */}
      <path
        d={path}
        fill="none"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        strokeDasharray={hasBug ? "5 4" : "7 5"}
        pointerEvents="none"
        style={{
          animation: isHighlighted || isHovered ? 'graphFlow 2.4s linear infinite' : 'none',
          filter: (isHighlighted || isHovered) ? `drop-shadow(0 0 6px ${strokeColor})` : 'none',
        }}
      />

      {/* TAIL: Unmistakable Concentric Caller Socket Port */}
      <g className="edge-tail" pointerEvents="none" transform={`translate(${start.x}, ${start.y})`}>
        <circle r="5.5" fill="#e2e9ee" stroke={strokeColor} strokeWidth="1.8" />
        <circle r="2.2" fill={arrowColor} />
      </g>

      {/* HEAD: Direction-aligned Aerodynamic Chevron Arrowhead */}
      <polygon
        points={`${p1.x},${p1.y} ${p2.x},${p2.y} ${p3.x},${p3.y} ${p4.x},${p4.y}`}
        fill={arrowColor}
        stroke={arrowColor}
        strokeWidth="0.8"
        pointerEvents="none"
        style={{
          filter: (hasBug || isHighlighted || isHovered) ? `drop-shadow(0 0 5px ${arrowColor})` : 'none',
        }}
      />
    </g>
  );
});

/* Endpoint and Broken Link badges — Rendered in Top Layer to ALWAYS sit on top of nodes */
const EdgeBadge = memo(function EdgeBadge({
  edgeGeo, hasBug, endpoint, isDimmed, isHighlighted,
  isHovered, showEndpoints
}) {
  const { badgePoint } = edgeGeo;

  // Determine badge visibility:
  // - Broken link ALWAYS visible
  // - Normal edges visible on edge hover OR when showEndpoints is toggled OR when explicitly highlighted
  const showBadge = hasBug || isHovered || showEndpoints || (isHighlighted && Boolean(endpoint));

  if (!showBadge) return null;

  return (
    <g
      className="graph-badge-group"
      pointerEvents="none"
      style={{
        opacity: isDimmed ? 0.15 : 1,
        transition: 'opacity 0.25s ease',
      }}
    >
      {hasBug ? (
        // Broken Link Badge (centered on the red edge)
        <g transform={`translate(${badgePoint.x}, ${badgePoint.y})`}>
          <rect
            x="-50" y="-11" width="100" height="21" rx="10"
            fill="#ac3449"
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
              fill="#edf1f4"
              stroke={isHovered ? "#176b68" : "rgba(23,107,104,0.5)"}
              strokeWidth={isHovered ? "1.5" : "1"}
              style={{
                filter: 'drop-shadow(0 2px 3px rgba(80,97,110,0.15))',
                transition: 'all 0.15s ease'
              }}
            />
            <text
              x="0" y="3.5" textAnchor="middle"
              fill="var(--cyan)" fontSize="9.5" fontWeight="600"
              fontFamily="'JetBrains Mono',monospace"
            >
              {endpoint}
            </text>
          </g>
        )
      )}
    </g>
  );
});

export default function DependencyGraph({ snapshot = null, findingsHref = null, illustrative = false }) {
  const [data, setData]               = useState(null);
  const [loading, setLoading]         = useState(true);
  const [error, setError]             = useState(null);
  const [zoom, setZoom]               = useState(null);
  const [layout, setLayout]           = useState(null);
  const [layoutError, setLayoutError] = useState(null);
  const [direction, setDirection]     = useState('DOWN');
  const [expanded, setExpanded]       = useState(false);
  const [viewport, setViewport]       = useState({width:0,height:0});
  const viewportRef = useRef(null);
  const dialogRef = useRef(null);
  const [selectedNode, setSelected]   = useState(null);
  const [hoveredEdge, setHoveredEdge] = useState(null);
  const [inspectedEdge, setInspectedEdge] = useState(null);
  const [relationView, setRelationView] = useState('connections');
  const [searchQuery, setSearch]      = useState('');
  const [showEndpoints, setShowEnd]   = useState(false); // Clean view by default with toggle
  const hoverEdge = useCallback(edge => setHoveredEdge(edge), []);
  const clearEdgeHover = useCallback(() => setHoveredEdge(null), []);
  const inspectEdge = useCallback(edge => setInspectedEdge(edge), []);

  useEffect(() => {
    if (snapshot) {
      setData(snapshotGraph(snapshot));
      setLoading(false);
      setError(null);
      setSelected(null);
      return;
    }
    getGraph()
      .then(d => { setData(d); setError(null); })
      .catch(() => setError('Could not load dependency graph from backend'))
      .finally(() => setLoading(false));
  }, [snapshot]);

  const nodes = useMemo(() => data?.nodes || [], [data]);
  const rawEdges = useMemo(() => data?.edges || [], [data]);
  const connections = useMemo(() => groupRelations(rawEdges), [rawEdges]);
  const edges = relationView === 'connections' ? connections : rawEdges;
  const hasParallelRelations = connections.length < rawEdges.length;

  useEffect(() => {
    if (!nodes.length) return;
    let task;
    let timer;
    let active = true;
    setLayout(null);
    setLayoutError(null);
    setZoom(null);
    setHoveredEdge(null);
    setInspectedEdge(null);
    try {
      task = startLayout(nodes,edges,direction);
      const fail = (error) => { if (!active) return; console.error('MDT graph worker failed',error?.message || 'Layout deadline exceeded'); setLayoutError('Could not arrange this graph. Refresh the view to retry.'); task.terminate(); clearTimeout(timer); };
      task.result.then(result => {
        if (!active) return;
        clearTimeout(timer);
        setLayout(result);
        task.terminate();
      }).catch(fail);
      timer = setTimeout(fail,30000);
    } catch { setLayoutError('Graph layout could not start. Refresh the view to retry.'); }
    return () => { active=false; clearTimeout(timer); task?.terminate(); };
  }, [nodes, edges, direction]);

  useEffect(() => {
    if(!layout || !viewportRef.current) return;
    const observer = new ResizeObserver(([entry]) => {
      const {width, height} = entry.contentRect;
      setViewport(previous => previous.width === width && previous.height === height ? previous : {width, height});
    });
    observer.observe(viewportRef.current);
    return () => observer.disconnect();
  }, [layout, expanded]);

  useEffect(() => {
    if(expanded) dialogRef.current?.showModal();
  }, [expanded, layout]);

  const POS = layout?.positions || {};
  const fittedScale = layout ? fitGraph(layout.width,layout.height,viewport.width,viewport.height) : 1;
  const scale = zoom ?? fittedScale;
  const resetView = () => {
    setZoom(null); setSelected(null); setSearch(''); setHoveredEdge(null);
    viewportRef.current?.scrollTo({left:0,top:0});
  };

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

  const maxY = layout?.height || 600;
  const maxX = layout?.width || 1000;
  const viewBox = `0 0 ${maxX} ${maxY}`;

  if (loading) return <div className="state-loading"><div className="spinner" /><span>Loading topology graph…</span></div>;
  if (error || layoutError) return <div className="state-error" role="alert"><AlertTriangle size={18} aria-hidden="true" /><span>{error || layoutError}</span></div>;

  if (!nodes.length) {
    return (
      <div className="card state-empty">
        <p>No services in the graph yet. Run an analysis to populate it.</p>
      </div>
    );
  }

  if (!layout) return <div className="state-loading" role="status"><div className="spinner" /><span>Arranging nodes and routing dependencies…</span></div>;

  const activeSelected = nodes.find(n => n.id === selectedNode);

  const content = (
    <div className="graph-card">
      {/* Top Header & Toolbar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px', marginBottom: '14px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
            <h2 className="panel-title" style={{ fontSize: '18px', fontWeight: 600, margin: 0 }}>
              Service Dependency Topology
            </h2>
            <span style={{ fontSize: '11px', color: 'var(--cyan)', background: 'rgba(0,212,255,0.12)', border: '1px solid rgba(0,212,255,0.3)', padding: '2px 8px', borderRadius: '10px', fontWeight: 600 }}>
              {nodes.length} Nodes · {connections.length} Connections · {rawEdges.length} Relations
            </span>
          </div>
          <p style={{ margin: '4px 0 0', fontSize: '12px', color: 'var(--text-dim)' }}>
            Circular socket = Caller (Tail) → Directional chevron = Callee (Head).
          </p>
          {illustrative && <p className="text-dim" style={{fontSize:12,margin:'6px 0 0'}}>Recorded demo · illustrative topology, not observed runtime traffic.</p>}
          {hasParallelRelations && <p className="text-dim" style={{fontSize:12,margin:'6px 0 0'}}>A connection groups all recorded relations in one direction. Select it to inspect each endpoint and its evidence, or switch to individual relations.</p>}
        </div>

        {/* Toolbar controls */}
        <div className="graph-toolbar" style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <button className="btn btn-ghost" onClick={()=>setExpanded(value=>!value)}>{expanded ? 'Close expanded graph' : 'Expand graph'}</button>
          {/* Search */}
          <input
            type="text"
            placeholder="Filter service…"
            aria-label="Filter graph services"
            value={searchQuery}
            onChange={e => setSearch(e.target.value)}
            style={{
              padding: '5px 10px',
              fontSize: '12px',
              background: 'rgba(255,255,255,0.05)',
              border: '1px solid rgba(255,255,255,0.12)',
              borderRadius: '6px',
              color: 'var(--text)',
              outline: 'none',
              width: '130px'
            }}
          />

          {/* Toggle Endpoints */}
          <CustomSelect className="form-select" aria-label="Graph detail" value={relationView} onChange={event => setRelationView(event.target.value)} style={{width:'auto',fontSize:12}}>
            <option value="connections">Service connections</option><option value="relations">Individual relations</option>
          </CustomSelect>
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
            <Tags size={13} aria-hidden="true" /> {showEndpoints ? 'Endpoints: ON' : 'Endpoints: OFF'}
          </button>

          <CustomSelect className="form-select" aria-label="Graph direction" value={direction} onChange={e=>setDirection(e.target.value)} style={{width:'auto',fontSize:12}}>
            <option value="DOWN">Top to bottom</option><option value="RIGHT">Left to right</option>
          </CustomSelect>
          {/* Zoom controls */}
          <div style={{ display: 'flex', alignItems: 'center', background: 'rgba(255,255,255,0.05)', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.12)' }}>
            <button
              onClick={() => setZoom(z => Math.max(0.1, (z ?? fittedScale) - 0.15))}
              title="Zoom out"
              style={{ background: 'none', border: 'none', color: 'var(--text)', padding: '5px 9px', cursor: 'pointer', fontSize: '13px' }}
            >
              −
            </button>
            <span style={{ fontSize: '11px', color: 'var(--text-dim)', padding: '5px 2px', minWidth: '38px', textAlign: 'center', userSelect: 'none' }}>
              {Math.round(scale * 100)}%
            </span>
            <button
              onClick={() => setZoom(z => Math.min(2, (z ?? fittedScale) + 0.15))}
              title="Zoom in"
              style={{ background: 'none', border: 'none', color: 'var(--text)', padding: '5px 9px', cursor: 'pointer', fontSize: '13px' }}
            >
              +
            </button>
            <button
              onClick={resetView}
              title="Fit graph to view" aria-label="Fit graph to view"
              style={{ background: 'none', borderLeft: '1px solid rgba(255,255,255,0.1)', color: '#176b68', padding: '5px 9px', cursor: 'pointer', fontSize: '11px' }}
            >
              Fit
            </button>
            <button className="btn btn-ghost" title="Show at actual size" onClick={() => setZoom(1)}>1:1</button>
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
          color: 'var(--text)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '8px'
        }}>
          <div>
            <strong>{activeSelected?.label || selectedNode}</strong>
            {activeSelected?.is_broken ? (
              <span style={{ color: '#ac3449', fontWeight: 700, marginLeft: '8px' }}>
                ⚠ BROKEN LINK · unresolved dependency target
              </span>
            ) : (
              <span style={{ color: 'var(--cyan)', marginLeft: '8px' }}>
                · Directly connected: {connectedIds ? connectedIds.size - 1 : 0} nodes
              </span>
            )}
          </div>
          {activeSelected?.resolution_reason && <p style={{flexBasis:'100%',margin:0}}>{activeSelected.resolution_reason}</p>}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {findingsHref && <a
              href={findingsHref}
              className="btn-primary-ghost"
              style={{ padding: '4px 10px', fontSize: '11px', textDecoration: 'none', borderRadius: '4px' }}
              title="Open findings for this captured analysis"
            >
              🔍 View Findings
            </a>}
            <button
              onClick={() => setSelected(null)}
              className="btn btn-ghost"
              style={{ padding: '2px 8px', fontSize: '11px', color: '#176b68' }}
            >
              Clear Highlight ✕
            </button>
          </div>
        </div>
      )}

      {/* Relation details can wrap instead of overflowing narrow viewports. */}
      <div className="graph-context" role="region" aria-label="Connection details" tabIndex={0} style={{
        background: hoveredEdge
          ? (hoveredEdge.has_bug ? 'rgba(255,45,85,0.15)' : 'rgba(0, 212, 255, 0.1)')
          : 'rgba(255, 255, 255, 0.02)',
        border: `1px solid ${hoveredEdge
          ? (hoveredEdge.has_bug ? '#ac3449' : 'rgba(0, 212, 255, 0.3)')
          : 'rgba(255, 255, 255, 0.06)'}`,
        borderRadius: '6px',
        padding: '8px 14px',
        marginBottom: '10px',
        fontSize: '11.5px',
        fontFamily: "'JetBrains Mono', monospace",
        color: 'var(--text)',
        display: 'flex',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '8px',
        boxSizing: 'border-box',
        transition: 'background 0.2s ease, border-color 0.2s ease',
      }}>
        {hoveredEdge ? (
          <>
            <span style={{ color: 'var(--text-dim)' }}>RELATION:</span>
            <strong>{hoveredEdge.from}</strong>
            <span style={{ color: hoveredEdge.has_bug ? '#ac3449' : 'var(--cyan)' }}>
              ──({relationDescription(hoveredEdge)})──►
            </span>
            <strong>{hoveredEdge.to}</strong>
            {hoveredEdge.has_bug && (
              <span style={{ color: '#ac3449', fontWeight: 700, marginLeft: 'auto' }}>
                ⚠ UNRESOLVED DEPENDENCY
              </span>
            )}
          </>
        ) : (
          <span style={{ color: 'var(--text-faint)', fontSize: '11px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Info size={15} aria-hidden="true" /> Hover a connection to identify it. Select it to inspect its recorded relations, or select a service to highlight its neighbors.
          </span>
        )}
      </div>

      <p className="text-dim" style={{fontSize:12,margin:'0 0 10px'}}>Fit shows the full topology. Use 1:1 to read labels, scroll to explore, or select a node to highlight its connections.</p>
      {/* Main Graph SVG Viewport */}
      <div className="graph-viewport" ref={viewportRef} style={{
        overflow: 'auto',
        borderRadius: '10px',
        border: '1px solid rgba(255,255,255,0.08)',
        background: 'var(--bg-card2)',
        position: 'relative'
      }}>
        <div className="graph-stage" style={{width:maxX*scale,height:maxY*scale,visibility:viewport.width&&viewport.height?'visible':'hidden'}}>
          <svg
            className="graph-svg"
            viewBox={viewBox}
            preserveAspectRatio="xMidYMid meet"
            style={{ width: maxX*scale, height: maxY*scale, display: 'block' }}
          >
            <defs>
              {/* Node drop shadows */}
              <filter id="nodeGlow" x="-20%" y="-20%" width="140%" height="140%">
                <feDropShadow dx="0" dy="4" stdDeviation="6" floodOpacity="0.35" />
              </filter>
              <filter id="brokenGlow" x="-30%" y="-30%" width="160%" height="160%">
                <feDropShadow dx="0" dy="0" stdDeviation="8" floodColor="#ac3449" floodOpacity="0.55" />
              </filter>
            </defs>

            {/* Subtle Grid Pattern Background */}
            <pattern id="graphGrid" width="40" height="40" patternUnits="userSpaceOnUse">
              <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(80,97,110,0.09)" strokeWidth="1" />
            </pattern>
            <rect width={maxX} height={maxY} fill="url(#graphGrid)" />

            {/* Layer 1: Relations / Edges (paths, sockets, chevrons) */}
            <g className="graph-layer-edges">
              {edges.map((e, i) => {
                const fromPos = POS[e.from];
                const toPos   = POS[e.to];
                if (!fromPos || !toPos || !layout.routes[i]) return null;

                const isRelevant = !selectedNode || e.from === selectedNode || e.to === selectedNode;
                const isHigh = inspectedEdge === e || selectedNode && (e.from === selectedNode || e.to === selectedNode);
                const isEdgeHovered = hoveredEdge === e;

                return (
                  <EdgeCurve
                    key={`curve-${e.from}->${e.to}-${i}`}
                    edge={e}
                    edgeIndex={i}
                    edgeGeo={layout.routes[i]}
                    hasBug={Boolean(e.has_bug)}
                    isDimmed={Boolean(connectedIds && !isRelevant)}
                    isHighlighted={Boolean(isHigh)}
                    isHovered={Boolean(isEdgeHovered)}
                    onHover={hoverEdge}
                    onLeave={clearEdgeHover}
                    onInspect={inspectEdge}
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
                const color     = isBroken ? '#ac3449' : (RISK_COLOR[riskLevel] || RISK_COLOR.UNKNOWN);
                const analyzed  = riskLevel !== 'UNKNOWN';
                const statusColor = isBroken ? '#ac3449' : node.status === 'healthy' ? RISK_COLOR.LOW : RISK_COLOR.UNKNOWN;
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
                    role="button"
                    tabIndex={0}
                    aria-label={`Inspect ${node.label || node.id}`}
                    aria-pressed={selectedNode === node.id}
                    onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelected(prev => prev === node.id ? null : node.id); } }}
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
                      fill={isBroken ? "#f1dce0" : "#edf1f4"}
                      stroke={isSelected ? '#176b68' : color}
                      strokeWidth={isSelected ? 2.5 : (isBroken ? 2 : 1.5)}
                      strokeDasharray={isBroken ? "5 4" : "none"}
                    />

                    {/* Left Accent Color Bar */}
                    <rect
                      x="2" y="6"
                      width="1" height={nodeH - 12}
                      rx="2"
                      fill={color}
                    />

                    {/* Node Title */}
                    <text
                      x={nodeW / 2 + 1} y="24" textAnchor="middle"
                      fill="var(--text)" fontSize={titleFontSize} fontWeight="600"
                      fontFamily="'JetBrains Mono',monospace"
                      style={{ letterSpacing: titleLen > 24 ? '-0.3px' : 'normal' }}
                    >
                      {title}
                    </text>

                    {/* Node Status / Metric */}
                    {isBroken ? (
                      <text
                        x={nodeW / 2 + 1} y="43" textAnchor="middle"
                        fill="#ac3449" fontSize="10" fontWeight="700"
                        fontFamily="'JetBrains Mono',monospace"
                      >
                        BROKEN LINK · UNRESOLVED
                      </text>
                    ) : (
                      <text
                        x={nodeW / 2 + 1} y="43" textAnchor="middle"
                        fill={color} fontSize="10.5" fontWeight="500"
                        fontFamily="'JetBrains Mono',monospace"
                      >
                        {snapshot ? `MODELED · ${node.node_type || 'service'}` : analyzed
                          ? `${riskLevel} · ${node.risk_score}/100`
                          : `${(node.status || 'unobserved').toUpperCase()}${node.port == null ? '' : ` · :${node.port}`}`}
                      </text>
                    )}

                    {/* Unknown modeled nodes must not imply observed live health. */}
                    <circle
                      cx={nodeW - 12} cy="14" r="3.5"
                      fill={statusColor}
                      style={{
                        filter: 'none',
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
                if (!fromPos || !toPos || !layout.routes[i]) return null;

                const isRelevant = !selectedNode || e.from === selectedNode || e.to === selectedNode;
                const isHigh = inspectedEdge === e || selectedNode && (e.from === selectedNode || e.to === selectedNode);
                const isEdgeHovered = hoveredEdge === e;

                return (
                  <EdgeBadge
                    key={`badge-${e.from}->${e.to}-${i}`}
                    edgeGeo={layout.routes[i]}
                    hasBug={Boolean(e.has_bug)}
                    endpoint={edgeLabel(e)}
                    isDimmed={Boolean(connectedIds && !isRelevant)}
                    isHighlighted={Boolean(isHigh)}
                    isHovered={Boolean(isEdgeHovered)}
                    showEndpoints={showEndpoints || Boolean(e.relations)}
                  />
                );
              })}
            </g>
          </svg>
        </div>
      </div>

      {inspectedEdge && <section className="graph-relation-inspector" aria-label="Recorded connection evidence">
        <div className="workspace-actions"><strong>{inspectedEdge.from} → {inspectedEdge.to}</strong><button className="btn btn-ghost" onClick={() => setInspectedEdge(null)}>Close connection details</button></div>
        <p>{illustrative ? 'Illustrative demo records; these are not verified runtime calls.' : 'Captured static evidence; declarations do not establish runtime traffic.'}</p>
        <ol>{(inspectedEdge.relations || [inspectedEdge]).map((edge, index) => <li key={index}>
          <code>{relationDescription(edge)}</code>
          <small>{edge.evidence_kind ? edge.evidence_kind.replaceAll('_', ' ') : illustrative ? 'Illustrative modeled relation' : 'Evidence kind not recorded'}{edge.source_file && ` · ${edge.source_file}${edge.source_line ? `:${edge.source_line}` : ''}`}{edge.environment_variable && ` · ${edge.environment_variable}`}</small>
          {edge.resolution_reason && <p>{edge.resolution_reason}</p>}
        </li>)}</ol>
      </section>}

      {/* Enhanced Legend and Direction Guide */}
      <div className="graph-legend" style={{ marginTop: '14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flexWrap: 'wrap' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12, color: 'var(--text-dim)' }}>
            <span className="legend-dot" style={{ background: '#586875', border: '1px solid rgba(255,255,255,0.2)' }} />
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
            ⚠ Broken link / unresolved target
          </span>
        </div>

        {/* Visual Arrowhead / Tail Guide */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '4px 12px', background: 'rgba(255,255,255,0.04)', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.08)', fontSize: '11px', color: 'var(--text-dim)' }}>
          <span>Relation Guide:</span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: 'var(--text)' }}>
            <span style={{ width: 9, height: 9, borderRadius: '50%', border: '1.8px solid #176b68', background: '#e2e9ee', display: 'inline-block' }} />
            Tail (Caller)
          </span>
          <span style={{ color: 'var(--cyan)' }}>────────►</span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: 'var(--text)' }}>
            <span style={{ width: 0, height: 0, borderTop: '4px solid transparent', borderBottom: '4px solid transparent', borderLeft: '8px solid #176b68', display: 'inline-block' }} />
            Head (Callee)
          </span>
        </div>
      </div>
    </div>
  );
  return expanded ? <dialog ref={dialogRef} className="graph-dialog" aria-label="Expanded dependency graph" onClose={()=>setExpanded(false)}>{content}</dialog> : content;
}
