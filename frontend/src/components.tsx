import { useEffect, useRef, useState, type ReactNode } from 'react';
import { AlertCircle, ArrowLeft, Check, LoaderCircle, Search, X } from 'lucide-react';
import { post, friendlyError } from './api';
import type { Customer } from './types';

export function Button({
  children,
  busy = false,
  variant = 'primary',
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  busy?: boolean;
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
}) {
  return (
    <button
      type="button"
      {...props}
      className={`button ${variant} ${props.className || ''}`}
      disabled={busy || props.disabled}
    >
      {busy && <LoaderCircle className="spin" size={18} />} {children}
    </button>
  );
}
export function ErrorNotice({ message, retry }: { message: string; retry?: () => void }) {
  return message ? (
    <div className="error-notice" role="alert">
      <AlertCircle size={20} />
      <span>{message}</span>
      {retry && <button onClick={retry}>Try again</button>}
    </div>
  ) : null;
}
export function Empty({
  title,
  text,
  children,
}: {
  title: string;
  text: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Check size={24} />
      </div>
      <h3>{title}</h3>
      <p>{text}</p>
      {children}
    </div>
  );
}
export function Loading() {
  return (
    <div className="loading" role="status">
      <LoaderCircle className="spin" size={22} /> Loading your shop…
    </div>
  );
}
export function SearchField({
  value,
  onChange,
  placeholder = 'Search…',
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <div className="search-field">
      <Search size={21} />
      <input
        aria-label={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
      {value && (
        <button
          className="icon-button"
          aria-label="Clear search"
          onClick={() => onChange('')}
        >
          <X size={18} />
        </button>
      )}
    </div>
  );
}
export function Modal({
  title,
  onClose,
  children,
  wide = false,
  busy = false,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
  busy?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const closeRef = useRef(onClose);
  const busyRef = useRef(busy);
  closeRef.current = onClose;
  busyRef.current = busy;
  useEffect(() => {
    ref.current?.showModal();
    const current = ref.current;
    const cancel = (event: Event) => {
      event.preventDefault();
      if (!busyRef.current) closeRef.current();
    };
    current?.addEventListener('cancel', cancel);
    return () => {
      current?.removeEventListener('cancel', cancel);
      current?.close();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className={`modal ${wide ? 'wide' : ''}`}
      onClick={(e) => {
        if (!busy && e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal-head">
        <h2>{title}</h2>
        <button
          disabled={busy}
          className="icon-button"
          aria-label="Close dialog"
          onClick={onClose}
        >
          <X size={23} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}
export function NewCustomer({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (customer: Customer) => void;
}) {
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      const customer = await post<Customer>('/api/customers', {
        name: name.trim(),
        phone: phone.trim(),
      });
      onCreated(customer);
    } catch (e) {
      setError(friendlyError(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal busy={busy} title="Add customer" onClose={onClose}>
      <form onSubmit={save}>
        <Field label="Customer name">
          <input
            autoFocus
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Ramesh Kumar"
            maxLength={120}
          />
        </Field>
        <Field label="Phone number (optional)">
          <input
            type="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="Mobile number"
            maxLength={30}
          />
        </Field>
        <ErrorNotice message={error} />
        <div className="form-actions">
          <Button disabled={busy} variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" busy={busy} disabled={!name.trim()}>
            Add customer
          </Button>
        </div>
      </form>
    </Modal>
  );
}
export function BackButton({
  onClick,
  children,
}: {
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <Button variant="ghost" onClick={onClick}>
      <ArrowLeft size={18} />
      {children}
    </Button>
  );
}
