import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { cancelAnalysisJob, createProject, deleteProject, getAnalysisJob, getAnalysisSnapshot, getDemo, getProject, listProjects, startAnalysisJob } from '../api';
import { useAuth } from '../context/useAuth';
import { PROJECT_VIEWS, readRoute, routeHash, formatScore, jobResult } from '../utils/analysis';
import AnalysisResult from './AnalysisResult';
import EvidenceSummary from './EvidenceSummary';

const Graph = lazy(() => import('./DependencyGraph'));
const Drift = lazy(() => import('./ProjectDrift'));
const Policies = lazy(() => import('./ProjectPolicies'));
const TERMINAL = new Set(['succeeded', 'completed', 'partial', 'failed', 'cancelled']);
const message = error => typeof error.response?.data?.detail === 'string' ? error.response.data.detail : error.response?.data?.detail?.message || error.message || 'Request failed.';

export default function Workspace({ onSignIn }) {
  const { isAuthenticated } = useAuth();
  const [route, setRoute] = useState(() => readRoute(location.hash));
  const [projects, setProjects] = useState([]);
  const [project, setProject] = useState(null);
  const [demo, setDemo] = useState(null);
  const [job, setJob] = useState(null);
  const [snapshot, setSnapshot] = useState(null);
  const [retry, setRetry] = useState(0);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [repoUrl, setRepoUrl] = useState('');
  const [name, setName] = useState('');
  const [branch, setBranch] = useState('HEAD');
  const [baseRef, setBaseRef] = useState('');
  const [headRef, setHeadRef] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [copiedLink, setCopiedLink] = useState(false);
  const [projectSearch, setProjectSearch] = useState('');
  const demoMode = route.projectId === 'demo';
  const directory = !route.projectId;
  const navigate = (projectId, view = 'summary', jobId = '') => { location.hash = routeHash('projects', { projectId, view, jobId }); };
  const handleCopyLink = () => {
    navigator.clipboard.writeText(window.location.href).then(() => {
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 2000);
    }).catch(() => setError('Clipboard access was denied. Copy this page URL from the address bar.'));
  };

  useEffect(() => {
    const update = () => setRoute(readRoute(location.hash));
    window.addEventListener('hashchange', update);
    return () => window.removeEventListener('hashchange', update);
  }, []);

  useEffect(() => {
    if (!isAuthenticated) { setLoading(false); return; }
    const controller = new AbortController();
    setLoading(true);
    listProjects({ signal: controller.signal }).then(setProjects).catch(err => { if (!controller.signal.aborted) setError(message(err)); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [isAuthenticated, retry]);

  useEffect(() => {
    const controller = new AbortController();
    setProject(null); setSnapshot(null); setJob(null); setError(''); setConfirmDelete(false); setSettingsOpen(false);
    setBaseRef(''); setHeadRef('');
    if (demoMode) getDemo({ signal: controller.signal }).then(setDemo).catch(err => { if (!controller.signal.aborted) setError(message(err)); });
    else if (isAuthenticated && route.projectId) getProject(route.projectId, { signal: controller.signal }).then(setProject).catch(err => { if (!controller.signal.aborted) setError(message(err)); });
    return () => controller.abort();
  }, [demoMode, isAuthenticated, route.projectId, retry]);

  useEffect(() => {
    if (!isAuthenticated || !route.jobId || demoMode) return;
    let active = true, timer, controller, failures = 0, terminal = false;
    const poll = async () => {
      if (!active || document.hidden || terminal) return;
      clearTimeout(timer); controller?.abort(); controller = new AbortController();
      try {
        const next = await getAnalysisJob(route.jobId, { signal: controller.signal });
        if (!active) return;
        if (route.projectId && next.project !== route.projectId) throw new Error('This job belongs to another project. Open its original history link.');
        failures = 0; setJob(next); setError(''); terminal = TERMINAL.has(next.status);
        if (terminal && next.result?.kind === 'import') {
          const imported = await getProject(route.projectId, { signal: controller.signal });
          if (active) setProject(imported);
        }
        if (!terminal) timer = setTimeout(poll, 2500);
      } catch (err) {
        if (!active || err.code === 'ERR_CANCELED') return;
        failures += 1; terminal = failures >= 5 || [401,403,404].includes(err.response?.status);
        setError(`${message(err)} ${terminal ? 'Use Refresh to retry.' : 'Retrying…'}`);
        if (!terminal) timer = setTimeout(poll, Math.min(10000, failures * 2500));
      }
    };
    const visibility = () => { if (document.hidden) { clearTimeout(timer); controller?.abort(); } else poll(); };
    setJob(null); poll(); document.addEventListener('visibilitychange', visibility);
    return () => { active = false; clearTimeout(timer); controller?.abort(); document.removeEventListener('visibilitychange', visibility); };
  }, [route.jobId, route.projectId, isAuthenticated, demoMode, retry]);

  useEffect(() => {
    setSnapshot(null);
    if (route.view !== 'graph' || demoMode || !job || !TERMINAL.has(job.status) || !job.result) return;
    const controller = new AbortController();
    getAnalysisSnapshot(route.jobId, { signal: controller.signal }).then(data => setSnapshot(data.snapshot)).catch(err => { if (!controller.signal.aborted) setError(message(err)); });
    return () => controller.abort();
  }, [route.view, route.jobId, demoMode, job]);

  const add = async event => {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const created = await createProject({ name: name.trim() || repoUrl.split('/').filter(Boolean).at(-1), repo_url: repoUrl.trim(), branch: branch.trim() });
      setProjects(await listProjects()); setRepoUrl(''); setName(''); navigate(created.id, 'summary', created.job_id || '');
    } catch (err) { setError(message(err)); } finally { setBusy(false); }
  };
  const analyze = async (source = 'commit') => {
    setBusy(true); setError('');
    try {
      const created = await startAnalysisJob(route.projectId, { source, head_ref: headRef.trim() || project?.branch || 'HEAD', snapshot_version: project?.snapshot_version, ...(source === 'commit' && baseRef.trim() ? { base_ref: baseRef.trim() } : {}) });
      setJob(created); navigate(route.projectId, 'summary', created.job_id || created.id);
    } catch (err) { setError(message(err)); } finally { setBusy(false); }
  };
  const remove = async () => {
    setBusy(true);
    try { await deleteProject(route.projectId); setProjects(await listProjects()); navigate(''); }
    catch (err) { setError(message(err)); } finally { setBusy(false); }
  };
  const result = useMemo(() => demoMode ? demo?.analysis || demo : jobResult(job), [demoMode, demo, job]);
  const view = demoMode && ['analyze','drift'].includes(route.view) ? 'summary' : route.view;
  const graph = demoMode ? demo?.snapshot : route.jobId && job?.result ? snapshot : project?.snapshot;
  const visibleProjects = projects.filter(item => {
    if (!projectSearch) return true;
    const q = projectSearch.toLowerCase();
    return (item.name || '').toLowerCase().includes(q) || (item.repo_url || '').toLowerCase().includes(q);
  });

  return <div className="workspace">
    <header className="workspace-heading">
      <div>
        {!directory && (
          <div className="project-switcher-wrap" style={{ margin: '0 0 8px', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <a href={routeHash('projects')}>← All projects</a>
            <select
              className="project-switcher-select"
              value={demoMode ? 'demo' : route.projectId}
              onChange={e => {
                if (e.target.value === 'demo') navigate('demo');
                else navigate(e.target.value);
              }}
              aria-label="Switch project"
            >
              <option value="demo">✨ Explore Demo</option>
              {projects.map(p => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
        )}
        <h1 className="page-title">{directory ? 'Your architecture, in context' : demoMode ? 'MDT reference architecture' : project?.name || 'Project'}</h1>
        <p className="page-sub">{directory ? 'Choose a project, review a change, then inspect its evidence.' : demoMode ? 'Recorded public example · illustrative fixture, not live observations' : project ? `${project.repo_url} · ${project.branch}` : 'Loading project context…'}</p>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <button
          type="button"
          className="btn-copy-chip"
          onClick={handleCopyLink}
          title="Copy link to current view"
        >
          <span>{copiedLink ? '✓ Link copied' : '🔗 Share link'}</span>
        </button>
        <span className="badge badge-info">Academic alpha</span>
      </div>
    </header>
    {error && <div className="evidence-summary" role="alert">{error} <button className="btn btn-ghost" onClick={() => setRetry(v => v + 1)}>Refresh</button></div>}
    {directory ? <>
      {projects.length > 2 && (
        <div className="search-box project-directory-search">
          <input
            className="form-input"
            placeholder="Filter projects by name or URL…"
            aria-label="Filter projects by name or URL"
            value={projectSearch}
            onChange={e => setProjectSearch(e.target.value)}
          />
          {projectSearch && <button type="button" className="btn-clear-search" aria-label="Clear project filter" onClick={() => setProjectSearch('')}>✕</button>}
        </div>
      )}
      <div className="project-grid">
        <article className="card workspace-account demo-project">
          <span className="badge badge-info">Public example</span>
          <h2>Explore a recorded analysis</h2>
          <p>Follow dependencies across the reference microservices, inspect architectural findings and export the evidence.</p>
          <a className="btn btn-primary" href={routeHash('projects',{projectId:'demo'})}>Explore demo</a>
        </article>
        {visibleProjects.map(item => (
          <article className="card workspace-account" key={item.id}>
            <h2>{item.name}</h2>
            <p>{item.repo_url}</p>
            <p className="text-dim">{item.branch} · {item.import_status === 'failed' ? 'Import failed — review evidence' : item.ready ? 'Ready for analysis' : 'Import pending'}</p>
            <a className="btn btn-ghost" href={routeHash('projects',{projectId:item.id})}>Open project</a>
          </article>
        ))}
      </div>
      {loading && <p role="status">Loading your projects…</p>}
      {!isAuthenticated ? (
        <section className="card workspace-account">
          <h2>Analyze your repository</h2>
          <p>Sign in with an invited account to save projects and review changes. Source is read within bounded limits and is never executed.</p>
          <button className="btn btn-ghost" onClick={onSignIn}>Sign in</button>
        </section>
      ) : (
        <details className="card workspace-account">
          <summary>Add a public GitHub repository</summary>
          <form className="workspace-form" onSubmit={add}>
            <div className="preset-pills-row">
              <span style={{ fontSize: '11.5px', color: 'var(--text-dim)' }}>Presets:</span>
              <button
                type="button"
                className="preset-pill-btn"
                onClick={() => { setName('MDT Reference'); setRepoUrl('https://github.com/kartick026/MDT'); setBranch('main'); }}
              >
                ⚡ Fill MDT repository
              </button>
            </div>
            <label>Project name<input className="form-input" value={name} maxLength={100} onChange={e => setName(e.target.value)} /></label>
            <label>Repository URL<input className="form-input" type="url" required placeholder="https://github.com/owner/repository" value={repoUrl} onChange={e => setRepoUrl(e.target.value)} /></label>
            <label>Branch<input className="form-input" required value={branch} onChange={e => setBranch(e.target.value)} /></label>
            <p>Large or unsupported repositories may produce partial coverage.</p>
            <button className="btn btn-primary" disabled={busy}>{busy ? 'Creating project…' : 'Create project'}</button>
          </form>
        </details>
      )}
    </> : !demoMode && !isAuthenticated ? (
      <section className="card workspace-account">
        <h2>Sign in to open this project</h2>
        <p>Your project and analysis link will be preserved.</p>
        <button className="btn btn-primary" onClick={onSignIn}>Sign in</button>
      </section>
    ) : (
      <>
        <nav className="project-nav" aria-label="Project views">
        {PROJECT_VIEWS.filter(v => !demoMode || !['analyze','drift'].includes(v)).map(v => {
          const icon = v === 'summary' ? '📊' : v === 'graph' ? '🕸' : v === 'findings' ? '🔍' : v === 'drift' ? '🔀' : '⚡';
          const findingsCount = (result?.findings || result?.architecture_smells || result?.smells || []).length;
          const nodesCount = graph?.nodes?.length || graph?.services?.length;
          return (
            <a key={v} aria-current={view === v ? 'page' : undefined} href={routeHash('projects',{...route,view:v})}>
              <span style={{ marginRight: '6px' }}>{icon}</span>
              {v[0].toUpperCase() + v.slice(1)}
              {v === 'findings' && Boolean(findingsCount) && (
                <span className="subtab-count highlight" style={{ marginLeft: '6px' }}>{findingsCount}</span>
              )}
              {v === 'graph' && Boolean(nodesCount) && (
                <span className="subtab-count" style={{ marginLeft: '6px' }}>{nodesCount}</span>
              )}
            </a>
          );
        })}
      </nav>
      {job && <section className="job-progress" aria-live="polite"><span><strong>{job.status}</strong> · {job.stage || 'Analysis'}{job.error && ` · ${typeof job.error === 'string' ? job.error : JSON.stringify(job.error)}`}</span>{!TERMINAL.has(job.status) && <button className="btn btn-ghost" onClick={async () => { try { setJob(await cancelAnalysisJob(route.jobId)); } catch (err) { setError(message(err)); } }}>Cancel job</button>}<button className="btn btn-ghost" onClick={() => setRetry(v => v + 1)}>Refresh</button></section>}
      {!job && route.jobId && <p role="status">Loading saved analysis…</p>}
      {view === 'summary' && <>
        {result ? <AnalysisResult key={route.jobId || 'demo'} result={result} demo={demoMode} /> : <section className="card workspace-account"><h2>Project summary</h2><p>{project?.ready ? `${project.snapshot?.services?.length || 0} modeled nodes. Open Analyze to review a code change, or Graph to explore the captured topology.` : 'Architecture import has not completed. Open History to find its job, or Analyze to retry the import.'}</p>{job?.result?.kind === 'import' && <><p>Architectural debt: <strong>{formatScore(job.result.architecture_health?.score)}/100</strong> · {(job.result.smells || []).length} static findings. Commit risk has not been assessed.</p><EvidenceSummary result={job.result} /></>}</section>}
        {demo?.recorded_fallback && demoMode && <p className="text-dim">Bundled recorded example; live API unavailable.</p>}
        {!demoMode && project && <details className="card workspace-account" onToggle={event => setSettingsOpen(event.currentTarget.open)}><summary>Project settings</summary>{settingsOpen && <><p>Project ID: <code>{project.id}</code></p><p>Use this ID in the CLI hook or extension to keep analyses scoped to this project.</p><Suspense fallback={<p role="status">Loading dependency rules…</p>}><Policies project={project} /></Suspense>{confirmDelete ? <><p>Delete this project and all its saved data permanently?</p><div className="workspace-actions"><button className="btn btn-ghost" disabled={busy} onClick={remove}>Confirm deletion</button><button className="btn btn-ghost" onClick={() => setConfirmDelete(false)}>Keep project</button></div></> : <button className="btn btn-ghost" onClick={() => setConfirmDelete(true)}>Delete project and data</button>}</>}</details>}
      </>}
      {view === 'analyze' && <section className="card workspace-account">
        <h2>Review a code change</h2>
        <form className="workspace-form" onSubmit={e => { e.preventDefault(); analyze(); }}>
          <label>
            Head revision
            <div className="preset-pills-row">
              <button type="button" className="preset-pill-btn" onClick={() => setHeadRef(project?.branch || 'HEAD')}>Default ({project?.branch || 'HEAD'})</button>
              <button type="button" className="preset-pill-btn" onClick={() => setHeadRef('HEAD')}>HEAD</button>
              <button type="button" className="preset-pill-btn" onClick={() => setHeadRef('HEAD~1')}>HEAD~1</button>
            </div>
            <input className="form-input" aria-label="Head revision" value={headRef} onChange={e => setHeadRef(e.target.value)} placeholder={project?.branch || 'HEAD'} />
          </label>
          <label>
            Base revision (optional)
            <div className="preset-pills-row">
              <button type="button" className="preset-pill-btn" onClick={() => setBaseRef('HEAD~1')}>HEAD~1</button>
              <button type="button" className="preset-pill-btn" onClick={() => setBaseRef('HEAD~2')}>HEAD~2</button>
              <button type="button" className="preset-pill-btn" onClick={() => setBaseRef('')}>Clear (Parent commit)</button>
            </div>
            <input className="form-input" aria-label="Base revision (optional)" value={baseRef} onChange={e => setBaseRef(e.target.value)} placeholder="Parent commit when omitted" />
          </label>
          <p>Change impact uses the captured project topology. Import the head revision separately to compare architectural drift.</p>
          <div className="workspace-actions">
            <button className="btn btn-primary" disabled={!project?.ready || busy || (job && !TERMINAL.has(job.status))}>
              {busy ? 'Running analysis…' : 'Analyze changes'}
            </button>
            <button type="button" className="btn btn-ghost" disabled={!project || busy || (job && !TERMINAL.has(job.status))} onClick={() => analyze('import')}>
              Import topology at head revision
            </button>
          </div>
        </form>
      </section>}
      {view === 'graph' && <section className="card workspace-account"><h2>Dependency graph</h2><p>{route.jobId ? 'Topology captured for this saved analysis.' : 'Current captured project topology.'} Nodes describe modeled services and dependencies.</p><Suspense fallback={<p role="status">Loading graph…</p>}>{job && ['failed','cancelled'].includes(job.status) ? <p role="status">No graph was captured for this unsuccessful job. Review the import error above.</p> : graph ? <Graph snapshot={graph} illustrative={demoMode} findingsHref={routeHash('projects',{...route,view:'findings'})} /> : <p role="status">{job && ['failed', 'cancelled'].includes(job.status) ? 'No graph is available for this unsuccessful import.' : job && !job.result ? 'Graph will be available when this job completes.' : 'Loading captured graph…'}</p>}</Suspense></section>}
      {view === 'findings' && (result ? <AnalysisResult key={route.jobId || 'demo'} view="findings" result={result} demo={demoMode} /> : <section className="card workspace-account"><h2>No change analysis selected</h2><p>Run an analysis or open a saved result from History to review its findings.</p><a href={routeHash('history',{projectId:route.projectId})}>Open project history</a></section>)}
      {view === 'drift' && <Suspense fallback={<p role="status">Loading snapshots…</p>}><Drift projectId={route.projectId} /></Suspense>}
    </>) }
  </div>;
}

