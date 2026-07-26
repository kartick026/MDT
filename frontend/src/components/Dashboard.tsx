import React, { useEffect, useState } from 'react';
import { fetchHealth, fetchServices, fetchServiceDetails, type HealthResponse, type ServiceInfo } from '../api/client';
import { ServiceCard } from './ServiceCard';
import { AnalysisPanel } from './AnalysisPanel';
import { Activity, GitCommit, RefreshCw } from 'lucide-react';

export const Dashboard: React.FC = () => {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [services, setServices] = useState<ServiceInfo[]>([]);
  const [loading, setLoading] = useState(true);

  const loadData = async () => {
    setLoading(true);
    try {
      const h = await fetchHealth();
      setHealth(h);
      
      const serviceNames = await fetchServices();
      const serviceDetails = await Promise.all(
        serviceNames.map(name => fetchServiceDetails(name).catch(() => ({ name, port: 0, url: '', language: '', description: '' })))
      );
      setServices(serviceDetails);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  return (
    <div className="container">
      <header className="flex items-center justify-between" style={{ marginBottom: '2rem' }}>
        <div>
          <h1>MDT Dashboard</h1>
          <p>Microservice Drift Tracker</p>
        </div>
        <button className="btn-primary" onClick={loadData} disabled={loading}>
          <RefreshCw size={16} className={loading ? 'spin' : ''} />
          Refresh
        </button>
      </header>

      <section className="glass-panel" style={{ marginBottom: '2rem' }}>
        <h2 className="flex items-center gap-2" style={{ marginBottom: '1rem' }}>
          <Activity size={20} /> System Health
        </h2>
        <div className="grid grid-cols-3 gap-4">
          <div>
            <p>API Status</p>
            <h3 style={{ color: health?.status === 'healthy' ? 'var(--success)' : 'var(--danger)' }}>
              {health?.status || 'Offline'}
            </h3>
          </div>
          <div>
            <p>Neo4j Graph</p>
            <h3 style={{ color: health?.neo4j ? 'var(--success)' : 'var(--warning)' }}>
              {health?.neo4j ? 'Connected' : 'Disabled (Fallback mode)'}
            </h3>
          </div>
          <div>
            <p>ChromaDB Retrieval</p>
            <h3 style={{ color: health?.chromadb ? 'var(--success)' : 'var(--warning)' }}>
              {health?.chromadb ? 'Connected' : 'Disabled (Fallback mode)'}
            </h3>
          </div>
        </div>
      </section>

      <section>
        <h2 className="flex items-center gap-2" style={{ marginBottom: '1rem' }}>
          <GitCommit size={20} /> Monitored Services
        </h2>
        <div className="grid grid-cols-2 gap-4">
          {services.map((svc) => (
            <ServiceCard 
              key={svc.name} 
              name={svc.name} 
              port={svc.port} 
              status={svc.port ? 'healthy' : 'unknown'} 
            />
          ))}
          {services.length === 0 && !loading && (
            <p>No services found or backend unreachable.</p>
          )}
        </div>
      </section>

      <AnalysisPanel />
    </div>
  );
};
