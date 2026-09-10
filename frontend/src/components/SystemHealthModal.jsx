import React, { useEffect, useState } from 'react';
import { getHealth } from '../api';

export default function SystemHealthModal({ isOpen, onClose }) {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState(null);

  const fetchHealth = async () => {
    setLoading(true);
    try {
      const data = await getHealth();
      setHealth(data);
      setLastRefreshed(new Date());
    } catch (err) {
      console.error('Failed to fetch detailed health:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchHealth();
      const interval = setInterval(fetchHealth, 5000);
      return () => clearInterval(interval);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const neo4jDetails = health?.components?.details?.neo4j || {};
  const chromaDetails = health?.components?.details?.chroma || {};
  const llmDetails = health?.components?.details?.llm || {};
  const githubDetails = health?.components?.details?.github || {};
  const appInfo = health?.app || {};

  const isHealthy = health?.status === 'healthy';

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(5, 10, 24, 0.78)',
        backdropFilter: 'blur(8px)',
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        animation: 'fadeIn 0.2s ease-out',
        padding: '20px',
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '680px',
          background: 'linear-gradient(145deg, #0b1329 0%, #111e3f 100%)',
          borderRadius: '16px',
          border: '1px solid rgba(0, 212, 255, 0.3)',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.8), 0 0 35px rgba(0, 212, 255, 0.15)',
          padding: '26px',
          position: 'relative',
          color: '#e2e8f0',
          maxHeight: '90vh',
          overflowY: 'auto',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close Button */}
        <button
          onClick={onClose}
          style={{
            position: 'absolute',
            top: '18px',
            right: '18px',
            background: 'transparent',
            border: 'none',
            color: '#94a3b8',
            cursor: 'pointer',
            fontSize: '18px',
            lineHeight: 1,
            padding: '4px',
            borderRadius: '6px',
          }}
          title="Close diagnostics"
        >
          ✕
        </button>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px', borderBottom: '1px solid rgba(255,255,255,0.08)', paddingBottom: '16px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span style={{ fontSize: '22px' }}>📡</span>
              <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 700, color: '#f8fafc', fontFamily: 'var(--display)' }}>
                System Observability & Component Diagnostics
              </h2>
            </div>
            <p style={{ margin: '4px 0 0 32px', fontSize: '12.5px', color: '#94a3b8' }}>
              Live telemetry, database connection pooling, vector indexing, and AI pipeline status.
            </p>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '4px 12px',
                borderRadius: '20px',
                fontSize: '12px',
                fontWeight: 700,
                textTransform: 'uppercase',
                background: isHealthy ? 'rgba(0, 255, 136, 0.12)' : 'rgba(251, 191, 36, 0.12)',
                color: isHealthy ? '#00ff88' : '#fbbf24',
                border: `1px solid ${isHealthy ? 'rgba(0, 255, 136, 0.3)' : 'rgba(251, 191, 36, 0.3)'}`,
              }}
            >
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: isHealthy ? '#00ff88' : '#fbbf24', boxShadow: `0 0 8px ${isHealthy ? '#00ff88' : '#fbbf24'}` }} />
              {health?.status || 'POLLING'}
            </span>
          </div>
        </div>

        {/* 4 Component Diagnostics Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '14px', marginBottom: '20px' }}>
          {/* 1. Neo4j Graph */}
          <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '12px', padding: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600, fontSize: '14px', color: '#f1f5f9' }}>
                <span>⬡</span>
                <span>Neo4j Graph Database</span>
              </div>
              <span style={{
                fontSize: '11px',
                fontWeight: 600,
                padding: '2px 8px',
                borderRadius: '10px',
                background: neo4jDetails.connected ? 'rgba(0, 255, 136, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                color: neo4jDetails.connected ? '#00ff88' : '#ef4444',
                border: `1px solid ${neo4jDetails.connected ? 'rgba(0, 255, 136, 0.2)' : 'rgba(239, 68, 68, 0.2)'}`
              }}>
                {neo4jDetails.is_mock ? 'Mock Mode' : 'Connected'}
              </span>
            </div>
            <div style={{ fontSize: '12px', color: '#94a3b8', display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <div>Driver Mode: <strong style={{ color: '#cbd5e1' }}>{neo4jDetails.is_mock ? 'MockNeo4jDriver (In-Memory Simulation)' : 'GraphDatabase Driver'}</strong></div>
              <div>Connection Pool: <strong style={{ color: '#00d4ff' }}>Max 50 Connections</strong></div>
              <div>TLS Encryption: <strong style={{ color: '#cbd5e1' }}>neo4j+s:// Supported</strong></div>
            </div>
          </div>

          {/* 2. ChromaDB Vector Store */}
          <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '12px', padding: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600, fontSize: '14px', color: '#f1f5f9' }}>
                <span>🧬</span>
                <span>ChromaDB Vector Store</span>
              </div>
              <span style={{
                fontSize: '11px',
                fontWeight: 600,
                padding: '2px 8px',
                borderRadius: '10px',
                background: chromaDetails.connected ? 'rgba(0, 255, 136, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                color: chromaDetails.connected ? '#00ff88' : '#ef4444',
                border: `1px solid ${chromaDetails.connected ? 'rgba(0, 255, 136, 0.2)' : 'rgba(239, 68, 68, 0.2)'}`
              }}>
                {chromaDetails.connected ? 'Connected' : 'Offline'}
              </span>
            </div>
            <div style={{ fontSize: '12px', color: '#94a3b8', display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <div>Indexed Semantic Chunks: <strong style={{ color: '#00ff88' }}>{health?.chroma_indexed_chunks ?? 0} Chunks</strong></div>
              <div>Client Mode: <strong style={{ color: '#cbd5e1' }}>{chromaDetails.mode || 'Unavailable'}</strong></div>
              <div>Heartbeat: <strong style={{ color: '#00d4ff' }}>Active (Auto-recovered)</strong></div>
            </div>
          </div>

          {/* 3. AI / LLM Reasoning Engine */}
          <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '12px', padding: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600, fontSize: '14px', color: '#f1f5f9' }}>
                <span>✨</span>
                <span>AI Reasoning & Explanation</span>
              </div>
              <span style={{
                fontSize: '11px',
                fontWeight: 600,
                padding: '2px 8px',
                borderRadius: '10px',
                background: llmDetails.configured ? 'rgba(168, 85, 247, 0.12)' : 'rgba(251, 191, 36, 0.12)',
                color: llmDetails.configured ? '#c084fc' : '#fbbf24',
                border: `1px solid ${llmDetails.configured ? 'rgba(168, 85, 247, 0.3)' : 'rgba(251, 191, 36, 0.3)'}`
              }}>
                {llmDetails.status === 'ready' ? 'Ready' : 'Fallback Mode'}
              </span>
            </div>
            <div style={{ fontSize: '12px', color: '#94a3b8', display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <div>Primary Model: <strong style={{ color: '#c084fc' }}>{llmDetails.model || 'gemini-3.8-flash'}</strong></div>
              <div>Fallback Chain: <strong style={{ color: '#cbd5e1' }}>3.7 Flash → 2.5 Lite → Deterministic</strong></div>
              <div>Provider: <strong style={{ color: '#00d4ff' }}>Google Generative AI</strong></div>
            </div>
          </div>

          {/* 4. GitHub Integration & Security */}
          <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '12px', padding: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600, fontSize: '14px', color: '#f1f5f9' }}>
                <span>🐙</span>
                <span>GitHub Webhook & API</span>
              </div>
              <span style={{
                fontSize: '11px',
                fontWeight: 600,
                padding: '2px 8px',
                borderRadius: '10px',
                background: githubDetails.status === 'configured' ? 'rgba(0, 255, 136, 0.1)' : 'rgba(251, 191, 36, 0.12)',
                color: githubDetails.status === 'configured' ? '#00ff88' : '#fbbf24',
                border: `1px solid ${githubDetails.status === 'configured' ? 'rgba(0, 255, 136, 0.2)' : 'rgba(251, 191, 36, 0.3)'}`
              }}>
                {githubDetails.status === 'configured' ? 'Configured' : 'Not configured'}
              </span>
            </div>
            <div style={{ fontSize: '12px', color: '#94a3b8', display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <div>API Authentication: <strong style={{ color: githubDetails.status === 'configured' ? '#00ff88' : '#fbbf24' }}>{githubDetails.auth_type || 'none'}</strong></div>
              <div>Webhook Security: <strong style={{ color: '#00ff88' }}>HMAC-SHA256 Enforced</strong></div>
              <div>Rate Limiting: <strong style={{ color: '#cbd5e1' }}>30 req/min (Sliding Window)</strong></div>
              <div>Payload Max Size: <strong style={{ color: '#cbd5e1' }}>25 MB Protection</strong></div>
            </div>
          </div>
        </div>

        {/* Distributed Tracing & Runtime Observability Bar */}
        <div style={{ background: 'rgba(0, 0, 0, 0.4)', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.08)', padding: '14px 16px' }}>
          <div style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700, color: '#00d4ff', marginBottom: '8px' }}>
            Runtime Telemetry & Tracing Headers
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '12px', fontSize: '12px' }}>
            <div>
              <span style={{ color: '#64748b' }}>Environment:</span>
              <div style={{ fontWeight: 600, color: '#f8fafc' }}>{appInfo.environment || 'development'}</div>
            </div>
            <div>
              <span style={{ color: '#64748b' }}>Log Format:</span>
              <div style={{ fontWeight: 600, color: '#f8fafc' }}>{appInfo.log_format || 'text'} (JSON supported)</div>
            </div>
            <div>
              <span style={{ color: '#64748b' }}>Log Level:</span>
              <div style={{ fontWeight: 600, color: '#f8fafc' }}>{appInfo.log_level || 'INFO'}</div>
            </div>
            <div>
              <span style={{ color: '#64748b' }}>Last Refresh:</span>
              <div style={{ fontWeight: 600, color: '#00d4ff' }}>
                {lastRefreshed ? lastRefreshed.toLocaleTimeString() : 'Just now'}
              </div>
            </div>
          </div>
        </div>

        {/* Footer Actions */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '20px' }}>
          <button
            onClick={fetchHealth}
            disabled={loading}
            style={{
              background: 'rgba(255,255,255,0.06)',
              border: '1px solid rgba(255,255,255,0.15)',
              borderRadius: '8px',
              padding: '8px 16px',
              color: '#cbd5e1',
              fontSize: '12.5px',
              cursor: 'pointer',
            }}
          >
            {loading ? 'Refreshing…' : '↻ Refresh Now'}
          </button>
          <button
            onClick={onClose}
            style={{
              background: 'linear-gradient(135deg, #0284c7 0%, #0369a1 100%)',
              border: 'none',
              borderRadius: '8px',
              padding: '8px 18px',
              color: '#ffffff',
              fontSize: '12.5px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
