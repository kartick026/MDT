import { useEffect, useRef, useState } from 'react';
import { getHealth, getServices } from '../api';

export default function Diagnostics({ onClose }) {
  const dialog = useRef(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => { dialog.current?.showModal(); }, []);
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([getHealth({ signal: controller.signal }), getServices({ signal: controller.signal })]).then(([health, services]) => { setData({ health, services }); setError(''); }).catch(err => { if (!controller.signal.aborted) setError(err.message); });
    return () => controller.abort();
  }, [retry]);
  return <dialog className="mdt-dialog" ref={dialog} aria-labelledby="diagnostics-title" onCancel={onClose} onClose={onClose}>
    <div className="workspace-actions"><h2 id="diagnostics-title">Local diagnostics</h2><button className="btn btn-ghost" onClick={onClose}>Close</button></div>
    <p>Health of your local Docker services. Repository graph nodes describe source structure and have no live health status.</p>
    <button className="btn btn-ghost" onClick={() => setRetry(v => v + 1)}>Refresh health</button>
    {error && <p role="alert">{error}</p>}{!data && !error && <p role="status">Checking services…</p>}
    {data && <><ul className="workspace-findings">{data.services.map(service => <li key={service.name}><strong>{service.display_name}</strong> · {service.status}</li>)}</ul><details><summary>Backend diagnostics</summary><pre>{JSON.stringify(data.health,null,2)}</pre></details></>}
  </dialog>;
}
