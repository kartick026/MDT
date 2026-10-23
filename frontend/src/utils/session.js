export function clearAnalysisSession(storage = sessionStorage) {
  const keys = [];
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index);
    if (key?.startsWith('mdt_')) keys.push(key);
  }
  keys.forEach(key => storage.removeItem(key));
}

export function attachSession(headers, token) {
  // Logout explicitly targets the prior session, even if a new login finishes
  // before Axios dispatches the queued request.
  if (token && !headers.Authorization) headers.Authorization = `Bearer ${token}`;
  return headers;
}

export function rejectsCurrentSession(error, token) {
  return Boolean(token && error.response?.status === 401
    && error.config?.headers?.Authorization === `Bearer ${token}`);
}
