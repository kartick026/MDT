import React from 'react';
import { Server, Activity } from 'lucide-react';

interface ServiceProps {
  name: string;
  status?: string;
  port?: number;
}

export const ServiceCard: React.FC<ServiceProps> = ({ name, status = 'unknown', port }) => {
  const getStatusClass = (s: string) => {
    switch(s.toLowerCase()) {
      case 'healthy': return 'status-healthy';
      case 'error': return 'status-error';
      case 'warning': return 'status-warning';
      default: return 'status-offline';
    }
  };

  return (
    <div className="glass-panel">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Server size={20} className="text-blue-400" />
          <h3 style={{ margin: 0 }}>{name}</h3>
        </div>
        <div className={`status-dot ${getStatusClass(status)}`} title={`Status: ${status}`} />
      </div>
      <div className="mt-4">
        <p style={{ fontSize: '0.85rem' }}>
          <Activity size={14} style={{ display: 'inline', marginRight: '4px', verticalAlign: 'middle' }} />
          Port: {port || 'Unknown'}
        </p>
      </div>
    </div>
  );
};
