import { useEffect, useRef, useState } from 'react';
export async function api<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options.headers },
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body?.detail;
    const message =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail
              .map(
                (d: { msg?: string; loc?: string[] }) =>
                  `${d.loc?.slice(1).join(' ') || 'Input'}: ${d.msg || 'Please check this value'}`,
              )
              .join('. ')
          : 'Could not complete this action. Please try again.';
    throw new Error(message);
  }
  return body as T;
}
export function post<T>(url: string, body: unknown, method = 'POST') {
  return api<T>(url, { method, body: JSON.stringify(body) });
}
export function useData<T>(url: string | null, version = 0) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!url) {
      setData(null);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError('');
    setData(null);
    api<T>(url, { signal: controller.signal })
      .then(setData)
      .catch((e: Error) => {
        if (e.name !== 'AbortError') setError(friendlyError(e));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [url, version, retry]);
  return { data, loading, error, reload: () => setRetry((v) => v + 1) };
}
export function friendlyError(e: unknown) {
  return e instanceof TypeError
    ? 'Unable to connect. Check your connection and try again.'
    : e instanceof Error
      ? e.message
      : 'Something went wrong. Please try again.';
}
export function useRequestId() {
  const ref = useRef<{ payload: string; id: string } | null>(null);
  const get = (payload: unknown) => {
    const key = JSON.stringify(payload);
    if (ref.current?.payload !== key)
      ref.current = {
        payload: key,
        id: crypto.randomUUID
          ? crypto.randomUUID()
          : `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      };
    return ref.current.id;
  };
  return Object.assign(get, {
    reset: () => {
      ref.current = null;
    },
  });
}
