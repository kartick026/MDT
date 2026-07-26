const API_BASE = 'http://localhost:8000';

export interface HealthResponse {
  status: string;
  neo4j: boolean;
  chromadb: boolean;
  indexed_chunks: number;
}

export interface ServiceInfo {
  name: string;
  port: number;
  url: string;
  language: string;
  description: string;
}

export interface AnalysisRequest {
  repo_url: string;
  commit_sha: string;
  changed_files: string[];
}

export interface AnalysisResult {
  status: string;
  commit: string;
  risk_score: number;
  severity: string;
  impacted_services: string[];
  confidence: number;
  explanation: string;
  suggested_fixes: string[];
  affected_files: any[];
}

export const fetchHealth = async (): Promise<HealthResponse> => {
  const res = await fetch(`${API_BASE}/health/detailed`);
  if (!res.ok) throw new Error('Failed to fetch health');
  return res.json();
};

export const fetchServices = async (): Promise<string[]> => {
  const res = await fetch(`${API_BASE}/services/`);
  if (!res.ok) throw new Error('Failed to fetch services');
  return res.json();
};

export const fetchServiceDetails = async (name: string): Promise<ServiceInfo> => {
  const res = await fetch(`${API_BASE}/services/${name}`);
  if (!res.ok) throw new Error('Failed to fetch service details');
  return res.json();
};

export const fetchDependencies = async (name: string): Promise<any> => {
  const res = await fetch(`${API_BASE}/services/${name}/dependencies`);
  if (!res.ok) throw new Error('Failed to fetch dependencies');
  return res.json();
};

export const analyzeImpact = async (repo_url: string, commit_sha: string, changed_files: string[]): Promise<AnalysisResult> => {
  const res = await fetch(`${API_BASE}/analysis/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ repo_url, commit_sha, changed_files })
  });
  if (!res.ok) throw new Error('Analysis failed');
  return res.json();
};
