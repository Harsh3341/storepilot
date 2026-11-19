import { useState, type FormEvent, type ReactNode } from 'react';
import { ArrowRight, Eye, EyeOff, LockKeyhole, Store } from 'lucide-react';
import { friendlyError, post, type AuthSession } from './api';
import { Button, ErrorNotice, Field } from './components';

export function AuthFrame({ children }: { children: ReactNode }) {
  return (
    <div className="auth-layout">
      <div className="auth-brand">
        <span className="brand-mark">
          <Store size={28} />
        </span>
        <span>StorePilot</span>
      </div>
      <section className="auth-card">{children}</section>
      <p className="auth-footer">Your shop. Your products. Your account.</p>
    </div>
  );
}

type LoginProps = {
  onSignedIn: (session: AuthSession) => void;
  defaultUsername?: string;
  expired?: boolean;
  hasDraft?: boolean;
  notice?: string;
};

export function Login({
  onSignedIn,
  defaultUsername = '',
  expired = false,
  hasDraft = false,
  notice = '',
}: LoginProps) {
  const [username, setUsername] = useState(defaultUsername);
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !username.trim() || !password) return;
    setBusy(true);
    setError('');
    try {
      const session = await post<AuthSession>('/api/auth/login', {
        username: username.trim(),
        password,
      });
      if (!session.authenticated || !session.csrf_token) {
        throw new Error('Could not sign in. Please try again.');
      }
      setPassword('');
      onSignedIn(session);
    } catch (error) {
      setError(friendlyError(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthFrame>
      <div className="auth-heading">
        <span className="auth-lock">
          <LockKeyhole size={23} />
        </span>
        <h1>{expired ? 'Sign in to continue' : 'Welcome to your shop'}</h1>
        <p>
          {expired
            ? 'Your session ended. Sign in again to continue.'
            : 'Sign in with your owner account to open StorePilot.'}
        </p>
      </div>
      {expired && hasDraft && (
        <div className="auth-session-notice" role="status">
          Your current draft is still here. After signing in, review it and retry any
          unfinished action.
        </div>
      )}
      {!expired && notice && (
        <p className="auth-session-notice" role="status">
          {notice}
        </p>
      )}
      <form onSubmit={signIn}>
        <Field label="Username">
          <input
            autoFocus
            required
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            value={username}
            disabled={busy}
            onChange={(event) => setUsername(event.target.value)}
            placeholder="Enter your username"
          />
        </Field>
        <Field label="Password">
          <div className="auth-password">
            <input
              type={showPassword ? 'text' : 'password'}
              required
              autoComplete="current-password"
              value={password}
              disabled={busy}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Enter your password"
            />
            <button
              type="button"
              className="icon-button"
              aria-label={showPassword ? 'Hide password' : 'Show password'}
              aria-pressed={showPassword}
              disabled={busy}
              onClick={() => setShowPassword((value) => !value)}
            >
              {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
            </button>
          </div>
        </Field>
        <ErrorNotice message={error} />
        <Button
          type="submit"
          className="auth-submit"
          busy={busy}
          disabled={!username.trim() || !password}
        >
          {busy ? 'Signing in…' : 'Sign in'}
          {!busy && <ArrowRight size={19} />}
        </Button>
      </form>
      <p className="auth-owner-note">Only the shop owner can access this account.</p>
    </AuthFrame>
  );
}
