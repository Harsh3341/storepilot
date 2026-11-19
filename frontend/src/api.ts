import { useEffect, useRef, useState } from 'react';

export type AuthSession = {
  enabled: boolean;
  authenticated: boolean;
  username: string | null;
  csrf_token: string | null;
};

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

// Cookies are managed by the browser. The CSRF value lives only in this tab.
let csrfToken: string | null = null;
let sessionGeneration = 0;
const expiredListeners = new Set<() => void>();

export function setCsrfToken(token: string | null) {
  csrfToken = token;
  sessionGeneration += 1;
}

export function onSessionExpired(listener: () => void) {
  expiredListeners.add(listener);
  return () => {
    expiredListeners.delete(listener);
  };
}

export async function api<T>(url: string, options: RequestInit = {}): Promise<T> {
  const requestGeneration = sessionGeneration;
  const method = (options.method || 'GET').toUpperCase();
  const headers = new Headers(options.headers);
  headers.set('Content-Type', 'application/json');
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && csrfToken) {
    headers.set('X-CSRF-Token', csrfToken);
  }
  const response = await fetch(url, {
    ...options,
    credentials: 'same-origin',
    cache: 'no-store',
    headers,
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const isAuthRoute = url.startsWith('/api/auth/');
    if (
      response.status === 401 &&
      !isAuthRoute &&
      requestGeneration === sessionGeneration
    ) {
      setCsrfToken(null);
      expiredListeners.forEach((listener) => listener());
    }
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
    throw new ApiError(message, response.status);
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
