import { useState } from 'react';
import {
  ArrowRight,
  IndianRupee,
  Plus,
  ReceiptText,
  UserRound,
  Wallet,
} from 'lucide-react';
import { api, friendlyError, post, useData, useRequestId } from './api';
import {
  BackButton,
  Button,
  Empty,
  ErrorNotice,
  Field,
  Loading,
  Modal,
  NewCustomer,
  SearchField,
} from './components';
import { dateText, money, paise } from './format';
import type { Customer, Ledger, Sale, Summary } from './types';

type CustomerProps = {
  version: number;
  onChange: () => void;
  onReceipt: (sale: Sale) => void;
};

export function Customers({ version, onChange, onReceipt }: CustomerProps) {
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [dueOnly, setDueOnly] = useState(false);
  const data = useData<Customer[]>(
    `/api/customers?q=${encodeURIComponent(search)}`,
    version,
  );
  const summary = useData<Summary>('/api/summary', version);
  const customers =
    data.data?.filter((customer) => !dueOnly || (paise(customer.balance) || 0n) > 0n) ||
    [];

  function customerCreated(customer: Customer) {
    setSelected(customer.id);
    setCreating(false);
    onChange();
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Customers & udhaar</h1>
          <p>Know who owes what. Keep every repayment together.</p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <Plus size={19} />
          Add customer
        </Button>
      </div>
      <div className="balance-banner">
        <span className="balance-icon">
          <Wallet size={26} />
        </span>
        <div>
          <span>Total udhaar to collect</span>
          <strong>
            {summary.loading
              ? '…'
              : summary.data
                ? money(summary.data.outstanding_total)
                : '—'}
          </strong>
        </div>
        <p>Updated when you save a sale or receive a payment.</p>
      </div>
      <ErrorNotice message={summary.error} retry={summary.reload} />
      <div className={`customer-layout ${selected !== null ? 'has-selection' : ''}`}>
        <section className="surface customer-list">
          <div className="list-toolbar">
            <SearchField
              value={search}
              onChange={setSearch}
              placeholder="Search name or phone"
            />
          </div>
          <div className="filter-tabs customer-tabs">
            <button
              onClick={() => setDueOnly(false)}
              className={!dueOnly ? 'active' : ''}
            >
              All customers
            </button>
            <button onClick={() => setDueOnly(true)} className={dueOnly ? 'active' : ''}>
              Udhaar to collect
            </button>
          </div>
          <ErrorNotice message={data.error} retry={data.reload} />
          {data.loading ? (
            <Loading />
          ) : customers.length ? (
            <div>
              {customers.map((customer) => (
                <button
                  className={`customer-row ${selected === customer.id ? 'selected' : ''}`}
                  key={customer.id}
                  onClick={() => setSelected(customer.id)}
                >
                  <span className="avatar">
                    {customer.name.slice(0, 1).toUpperCase()}
                  </span>
                  <span className="customer-row-name">
                    <strong>{customer.name}</strong>
                    <small>{customer.phone || 'No phone number'}</small>
                  </span>
                  <span className="customer-row-balance">
                    <strong
                      className={
                        (paise(customer.balance) || 0n) > 0n ? 'due-text' : 'green-text'
                      }
                    >
                      {money(customer.balance)}
                    </strong>
                    <small>
                      {(paise(customer.balance) || 0n) > 0n ? 'to collect' : 'settled'}
                    </small>
                  </span>
                  <ArrowRight size={18} />
                </button>
              ))}
            </div>
          ) : (
            !data.error && (
              <Empty
                title={dueOnly ? 'No udhaar to collect' : 'No customers yet'}
                text={
                  search
                    ? 'Try another name or phone number.'
                    : dueOnly
                      ? 'All your customer balances are settled.'
                      : 'Add a customer to keep their bills and udhaar together.'
                }
              >
                {!search && !dueOnly && (
                  <Button onClick={() => setCreating(true)}>Add customer</Button>
                )}
              </Empty>
            )
          )}
        </section>
        <section className="surface customer-detail">
          {selected !== null ? (
            <CustomerLedger
              customerId={selected}
              version={version}
              onChange={onChange}
              onBack={() => setSelected(null)}
              onReceipt={onReceipt}
            />
          ) : (
            <div className="detail-empty">
              <UserRound size={44} strokeWidth={1.3} />
              <h3>A clear picture of every customer</h3>
              <p>
                Select a customer to see their bills, udhaar,
                <br />
                and payment history.
              </p>
            </div>
          )}
        </section>
      </div>
      {creating && (
        <NewCustomer onClose={() => setCreating(false)} onCreated={customerCreated} />
      )}
    </>
  );
}

function CustomerLedger({
  customerId,
  version,
  onChange,
  onBack,
  onReceipt,
}: CustomerProps & { customerId: number; onBack: () => void }) {
  const data = useData<Ledger>(`/api/customers/${customerId}/ledger`, version);
  const [payment, setPayment] = useState(false);
  const [saleBusy, setSaleBusy] = useState<number | null>(null);
  const [error, setError] = useState('');

  async function openReceipt(id: number) {
    if (saleBusy !== null) return;
    setSaleBusy(id);
    setError('');
    try {
      onReceipt(await api<Sale>(`/api/sales/${id}`));
    } catch (error) {
      setError(friendlyError(error));
    } finally {
      setSaleBusy(null);
    }
  }

  function paymentSaved() {
    setPayment(false);
    onChange();
  }

  return (
    <>
      <div className="detail-back mobile-only">
        <BackButton onClick={onBack}>All customers</BackButton>
      </div>
      <ErrorNotice message={data.error} retry={data.reload} />
      {data.loading ? (
        <Loading />
      ) : (
        data.data && (
          <>
            <div className="customer-detail-head">
              <span className="avatar large">
                {data.data.customer.name.slice(0, 1).toUpperCase()}
              </span>
              <div>
                <h2>{data.data.customer.name}</h2>
                <p>{data.data.customer.phone || 'No phone number added'}</p>
              </div>
            </div>
            <div className="customer-balance">
              <div>
                <span>Udhaar to collect</span>
                <strong>{money(data.data.customer.balance)}</strong>
              </div>
              <Button
                disabled={(paise(data.data.customer.balance) || 0n) <= 0n}
                onClick={() => setPayment(true)}
              >
                <IndianRupee size={17} />
                Receive payment
              </Button>
            </div>
            <div className="ledger-heading">
              <h3>Account history</h3>
              <span>{data.data.entries.length} entries</span>
            </div>
            <ErrorNotice message={error} />
            {data.data.entries.length ? (
              <div className="activity-list">
                {data.data.entries.map((entry) => {
                  const isPayment = (paise(entry.amount) || 0n) < 0n;
                  return (
                    <div className="activity-row" key={`${entry.kind}-${entry.id}`}>
                      <span className={`activity-icon ${isPayment ? 'payment' : ''}`}>
                        {isPayment ? <Wallet size={18} /> : <ReceiptText size={18} />}
                      </span>
                      <div className="activity-main">
                        <strong>
                          {entry.description ||
                            (isPayment ? 'Payment received' : 'Udhaar sale')}
                        </strong>
                        <small>{dateText(entry.created_at)}</small>
                        {entry.sale_id && (
                          <button
                            className="text-button"
                            disabled={saleBusy !== null}
                            onClick={() => openReceipt(entry.sale_id!)}
                          >
                            {saleBusy === entry.sale_id ? 'Opening…' : 'View bill'}
                          </button>
                        )}
                      </div>
                      <strong className={isPayment ? 'green-text' : 'due-text'}>
                        {!isPayment ? '+' : ''}
                        {money(entry.amount)}
                      </strong>
                    </div>
                  );
                })}
              </div>
            ) : (
              <Empty
                title="A fresh account"
                text="Saved credit bills and repayments will appear here."
              />
            )}
            {payment && (
              <PaymentForm
                customer={data.data.customer}
                onClose={() => setPayment(false)}
                onSaved={paymentSaved}
              />
            )}
          </>
        )
      )}
    </>
  );
}

function PaymentForm({
  customer,
  onClose,
  onSaved,
}: {
  customer: Customer;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [amount, setAmount] = useState(customer.balance);
  const [method, setMethod] = useState<'cash' | 'upi'>('cash');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const requestId = useRequestId();
  const cents = paise(amount);
  const balance = paise(customer.balance) || 0n;
  const valid = cents !== null && cents > 0n && cents <= balance;

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (busy || !valid) return;
    setBusy(true);
    setError('');
    const payload = { amount, method, note };
    try {
      await post(`/api/customers/${customer.id}/payments`, {
        ...payload,
        request_id: requestId(payload),
      });
      requestId.reset();
      onSaved();
    } catch (error) {
      setError(friendlyError(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal busy={busy} title="Receive udhaar payment" onClose={onClose}>
      <form onSubmit={save}>
        <div className="form-product">
          <strong>{customer.name}</strong>
          <p>Current udhaar: {money(customer.balance)}</p>
        </div>
        <Field label="Amount received (₹)">
          <input
            autoFocus
            inputMode="decimal"
            required
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
          />
        </Field>
        {cents !== null && cents > balance && (
          <p className="validation-hint">
            Payment cannot be more than the current udhaar.
          </p>
        )}
        <Field label="Payment method">
          <select
            value={method}
            onChange={(event) => setMethod(event.target.value as 'cash' | 'upi')}
          >
            <option value="cash">Cash</option>
            <option value="upi">UPI</option>
          </select>
        </Field>
        <Field label="Note (optional)">
          <input
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="e.g. Part payment"
          />
        </Field>
        <ErrorNotice message={error} />
        <div className="form-actions">
          <Button disabled={busy} variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" busy={busy} disabled={!valid}>
            Save payment
          </Button>
        </div>
      </form>
    </Modal>
  );
}
