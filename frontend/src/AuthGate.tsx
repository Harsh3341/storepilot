import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { LoaderCircle, ShieldCheck } from 'lucide-react';
import App from './App';
import {
  api,
  ApiError,
  friendlyError,
  onSessionExpired,
  post,
  setCsrfToken,
  type AuthSession,
} from './api';
import { Button, ErrorNotice } from './components';
import { AuthFrame, Login } from './Login';

type GateMode = 'checking' | 'authorized' | 'login' | 'signing-out' | 'unavailable';

export default function AuthGate() {
  const [mode, setMode] = useState<GateMode>('checking');
  const [session, setSession] = useState<AuthSession | null>(null);
  const [shopOpened, setShopOpened] = useState(false);
  const [expired, setExpired] = useState(false);
  const [sessionVersion, setSessionVersion] = useState(0);
  const [checkVersion, setCheckVersion] = useState(0);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const shopRef = useRef<HTMLDivElement>(null);
  const suspendedDialogs = useRef<HTMLDialogElement[]>([]);

  function authorize(status: AuthSession) {
    setCsrfToken(status.csrf_token);
    setSession(status);
    setError('');
    setNotice('');
    setExpired(false);
    setSessionVersion((version) => version + 1);
    setShopOpened(true);
    setMode('authorized');
  }

  useEffect(() => {
    const controller = new AbortController();
    setMode('checking');
    setError('');
    api<AuthSession>('/api/auth/session', { signal: controller.signal })
      .then((status) => {
        if (controller.signal.aborted) return;
        if (!status.enabled || (status.authenticated && status.csrf_token)) {
          authorize(status);
        } else {
          setCsrfToken(null);
          setSession(status);
          setMode('login');
        }
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setCsrfToken(null);
        setError(friendlyError(error));
        setMode('unavailable');
      });
    return () => controller.abort();
  }, [checkVersion]);

  useEffect(
    () =>
      onSessionExpired(() => {
        setExpired(true);
        setNotice('');
        setSession((current) => ({
          enabled: true,
          authenticated: false,
          username: current?.username || null,
          csrf_token: null,
        }));
        setMode('login');
      }),
    [],
  );

  // Native dialogs use the browser's top layer. Close them while the shop is
  // hidden, then restore surviving dialogs after login without remounting App.
  useLayoutEffect(() => {
    if (mode !== 'authorized') {
      const dialogs =
        shopRef.current?.querySelectorAll<HTMLDialogElement>('dialog[open]');
      if (dialogs?.length) {
        suspendedDialogs.current = Array.from(dialogs);
        suspendedDialogs.current.forEach((dialog) => dialog.close());
      }
      return;
    }
    suspendedDialogs.current.forEach((dialog) => {
      if (dialog.isConnected && !dialog.open) dialog.showModal();
    });
    suspendedDialogs.current = [];
  }, [mode]);

  async function signOut() {
    if (mode !== 'authorized') return;
    // Start with the current CSRF value; clear local business state immediately
    // so an intentional sign-out never restores another person's draft.
    const logoutRequest = post<{ ok: boolean }>('/api/auth/logout', {});
    setMode('signing-out');
    setShopOpened(false);
    suspendedDialogs.current = [];
    setCsrfToken(null);
    setSession({ enabled: true, authenticated: false, username: null, csrf_token: null });
    setExpired(false);
    setNotice('You’re signed out.');
    try {
      await logoutRequest;
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 401)) {
        setNotice('Could not confirm sign-out. Sign in again before using your shop.');
      }
    } finally {
      setMode('login');
    }
  }

  const isAuthorized = mode === 'authorized';

  return (
    <>
      {shopOpened && (
        <div ref={shopRef} hidden={!isAuthorized} inert={!isAuthorized}>
          <App
            ownerName={session?.username || null}
            sessionVersion={sessionVersion}
            onLogout={session?.enabled ? signOut : undefined}
          />
        </div>
      )}
      {mode === 'login' && (
        <Login
          key={expired ? 'expired-session' : 'owner-login'}
          onSignedIn={authorize}
          defaultUsername={session?.username || ''}
          expired={expired}
          hasDraft={shopOpened}
          notice={notice}
        />
      )}
      {(mode === 'checking' || mode === 'signing-out') && (
        <AuthFrame>
          <div className="auth-status" role="status">
            <LoaderCircle className="spin" size={29} />
            <h1>{mode === 'signing-out' ? 'Signing out…' : 'Opening your shop…'}</h1>
            <p>
              {mode === 'signing-out'
                ? 'Closing your owner session.'
                : 'Checking your owner session.'}
            </p>
          </div>
        </AuthFrame>
      )}
      {mode === 'unavailable' && (
        <AuthFrame>
          <div className="auth-status">
            <ShieldCheck size={31} />
            <h1>Couldn’t open your shop</h1>
            <p>Check your connection, then try again.</p>
          </div>
          <ErrorNotice message={error} />
          <Button
            className="auth-submit"
            onClick={() => setCheckVersion((version) => version + 1)}
          >
            Try again
          </Button>
        </AuthFrame>
      )}
    </>
  );
}
