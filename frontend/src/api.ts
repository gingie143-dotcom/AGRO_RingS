export async function api<T = any>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const csrf = document.cookie.split('; ').find(x => x.startsWith('csrf='))?.slice(5) || '';
  const isFile = body instanceof FormData;
  const response = await fetch('/api' + path, { method, credentials: 'same-origin',
    headers: { ...(isFile ? {} : { 'Content-Type': 'application/json' }), 'X-CSRF-Token': decodeURIComponent(csrf) },
    body: body === undefined ? undefined : isFile ? body : JSON.stringify(body) });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
  return data;
}
