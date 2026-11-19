import { useEffect, useRef, useState } from 'react';
import {
  ArrowRight,
  Check,
  ClipboardList,
  MessageCircle,
  Plus,
  ReceiptText,
  Sparkles,
  X,
} from 'lucide-react';
import { api, friendlyError, post, useData, useRequestId } from './api';
import { OrderDraft, draftIssue } from './OrderDraft';
import { Button, Empty, ErrorNotice, Field, Loading, Modal } from './components';
import { dateText, money, quantityText } from './format';
import type {
  Customer,
  DraftRow,
  Extraction,
  ExtractionStatus,
  Item,
  Order,
  Product,
  Sale,
} from './types';

type OrdersProps = {
  version: number;
  onChange: () => void;
  onOpen: (order: Order) => void;
  onReceipt: (sale: Sale) => void;
};

export function Orders({ version, onChange, onOpen, onReceipt }: OrdersProps) {
  const [status, setStatus] = useState('active');
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState('');
  const data = useData<Order[]>(
    status === 'active' ? '/api/orders' : `/api/orders?status=${status}`,
    version,
  );
  const orders =
    data.data?.filter(
      (order) =>
        status !== 'active' || order.status === 'pending' || order.status === 'ready',
    ) || [];

  async function changeStatus(order: Order, nextStatus: 'ready' | 'cancelled') {
    if (busyId !== null) return;
    if (nextStatus === 'cancelled' && !window.confirm(`Cancel order #${order.id}?`))
      return;
    setBusyId(order.id);
    setError('');
    try {
      await post(`/api/orders/${order.id}/status`, { status: nextStatus }, 'PATCH');
      onChange();
    } catch (error) {
      setError(friendlyError(error));
    } finally {
      setBusyId(null);
    }
  }

  async function openReceipt(order: Order) {
    if (busyId !== null || !order.sale_id) return;
    setBusyId(order.id);
    setError('');
    try {
      onReceipt(await api<Sale>(`/api/sales/${order.sale_id}`));
    } catch (error) {
      setError(friendlyError(error));
    } finally {
      setBusyId(null);
    }
  }

  function orderCreated() {
    setCreating(false);
    onChange();
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Every order, remembered</h1>
          <p>Keep walk-in and WhatsApp requests ready for billing.</p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <Plus size={19} />
          New order
        </Button>
      </div>
      <div className="filter-tabs orders-tabs" aria-label="Order status">
        {[
          ['active', 'To prepare'],
          ['completed', 'Completed'],
          ['cancelled', 'Cancelled'],
        ].map(([value, label]) => (
          <button
            key={value}
            className={status === value ? 'active' : ''}
            onClick={() => setStatus(value)}
          >
            {label}
          </button>
        ))}
      </div>
      <ErrorNotice message={data.error} retry={data.reload} />
      <ErrorNotice message={error} />
      {data.loading ? (
        <Loading />
      ) : orders.length ? (
        <div className="orders-list">
          {orders.map((order) => (
            <article className="order-card" key={order.id}>
              <div className="order-head">
                <span className="order-icon">
                  {order.source === 'whatsapp' ? (
                    <MessageCircle size={22} />
                  ) : (
                    <ClipboardList size={22} />
                  )}
                </span>
                <div>
                  <h2>{order.customer_name || 'Walk-in customer'}</h2>
                  <p>
                    Order #{order.id} ·{' '}
                    {order.source === 'whatsapp' ? 'WhatsApp' : 'Walk-in'} ·{' '}
                    {dateText(order.created_at)}
                  </p>
                </div>
                <span className={`order-status ${order.status}`}>
                  {order.status === 'pending'
                    ? 'To prepare'
                    : order.status === 'ready'
                      ? 'Ready to bill'
                      : order.status === 'completed'
                        ? 'Completed'
                        : 'Cancelled'}
                </span>
              </div>
              {order.note && <div className="order-card-note">{order.note}</div>}
              {order.items.length > 0 && (
                <div className="order-items">
                  {order.items.map((item, index) => (
                    <span key={`${item.product_code}-${index}`}>
                      {item.name || item.product_code}
                      <strong>{quantityText(item.quantity, item.unit)}</strong>
                    </span>
                  ))}
                </div>
              )}
              <div className="order-bottom">
                <div className="order-estimate">
                  <span>Estimated total</span>
                  <strong>
                    {order.estimated_total !== null
                      ? money(order.estimated_total)
                      : 'Add items when billing'}
                  </strong>
                </div>
                <div className="order-actions">
                  {(order.status === 'pending' || order.status === 'ready') && (
                    <>
                      <button
                        className="icon-button cancel-order"
                        aria-label={`Cancel order ${order.id}`}
                        title="Cancel order"
                        disabled={busyId !== null}
                        onClick={() => changeStatus(order, 'cancelled')}
                      >
                        <X size={19} />
                      </button>
                      {order.status === 'pending' && (
                        <Button
                          variant="secondary"
                          busy={busyId === order.id}
                          disabled={busyId !== null}
                          onClick={() => changeStatus(order, 'ready')}
                        >
                          <Check size={17} />
                          Mark ready
                        </Button>
                      )}
                      <Button disabled={busyId !== null} onClick={() => onOpen(order)}>
                        Open in bill
                        <ArrowRight size={18} />
                      </Button>
                    </>
                  )}
                  {order.status === 'completed' && order.sale_id && (
                    <Button
                      variant="secondary"
                      busy={busyId === order.id}
                      disabled={busyId !== null}
                      onClick={() => openReceipt(order)}
                    >
                      <ReceiptText size={17} />
                      View receipt
                    </Button>
                  )}
                </div>
              </div>
            </article>
          ))}
        </div>
      ) : (
        !data.error && (
          <section className="surface">
            <Empty
              title={
                status === 'active'
                  ? 'No orders waiting'
                  : status === 'completed'
                    ? 'No completed orders yet'
                    : 'No cancelled orders'
              }
              text={
                status === 'active'
                  ? 'Add a walk-in request or paste a WhatsApp message. It’ll be here when you need it.'
                  : status === 'completed'
                    ? 'Orders appear here after their sale is saved.'
                    : 'Cancelled orders will appear here.'
              }
            >
              {status === 'active' && (
                <Button onClick={() => setCreating(true)}>
                  <Plus size={18} />
                  New order
                </Button>
              )}
            </Empty>
          </section>
        )
      )}
      {creating && (
        <OrderForm
          version={version}
          onClose={() => setCreating(false)}
          onSaved={orderCreated}
        />
      )}
    </>
  );
}

function OrderForm({
  version,
  onClose,
  onSaved,
}: {
  version: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const customers = useData<Customer[]>('/api/customers', version);
  const products = useData<Product[]>('/api/products', version);
  const extraction = useData<ExtractionStatus>('/api/orders/extraction-status', version);
  const [customerId, setCustomerId] = useState<number | null>(null);
  const [name, setName] = useState('');
  const [source, setSource] = useState<'walk-in' | 'whatsapp'>('whatsapp');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [extractError, setExtractError] = useState('');
  const [extracting, setExtracting] = useState(false);
  const [rows, setRows] = useState<DraftRow[] | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const nextRowId = useRef(0);
  const operation = useRef(false);
  const controller = useRef<AbortController | null>(null);
  const requestId = useRequestId();
  const working = busy || extracting;
  const invalid = (rows || []).some((row) => draftIssue(row, products.data || []));

  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    const cooldown = extraction.data?.cooldown_seconds;
    if (!cooldown) return;
    const timer = window.setTimeout(extraction.reload, cooldown * 1000 + 100);
    return () => window.clearTimeout(timer);
  }, [extraction.data]);

  function changeRows(next: DraftRow[]) {
    setRows(next);
    setReviewed(false);
    setError('');
  }

  function addRow() {
    changeRows([
      ...(rows || []),
      {
        id: nextRowId.current++,
        original: '',
        product_code: null,
        quantity: null,
        unit: null,
        reason: null,
      },
    ]);
  }

  async function extractItems() {
    if (operation.current || !note.trim()) return;
    operation.current = true;
    setExtracting(true);
    setExtractError('');
    controller.current = new AbortController();
    try {
      const result = await api<Extraction>('/api/orders/extract', {
        method: 'POST',
        body: JSON.stringify({ text: note }),
        signal: controller.current.signal,
      });
      changeRows(result.rows.map((row) => ({ ...row, id: nextRowId.current++ })));
    } catch (error) {
      if (!(error instanceof Error && error.name === 'AbortError'))
        setExtractError(friendlyError(error));
    } finally {
      operation.current = false;
      setExtracting(false);
      extraction.reload();
    }
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (operation.current || !note.trim() || invalid || (rows?.length && !reviewed))
      return;
    operation.current = true;
    setBusy(true);
    setError('');
    try {
      const payload = {
        customer_id: customerId,
        customer_name: name.trim(),
        source,
        note: note.trim(),
        items: (rows || []).map((row): Item => ({
          product_code: row.product_code!,
          quantity: row.quantity!,
          unit: row.unit,
        })),
      };
      await post('/api/orders', { ...payload, request_id: requestId(payload) });
      onSaved();
    } catch (error) {
      setError(friendlyError(error));
    } finally {
      setBusy(false);
      operation.current = false;
    }
  }

  return (
    <Modal busy={working} title="New customer order" onClose={onClose}>
      <form onSubmit={save}>
        <fieldset className="order-form-fields" disabled={working}>
          <p className="form-intro">
            Paste a WhatsApp request or write down a walk-in order. Extract suggested
            items, check them, then save. You can also save just the note.
          </p>
          <Field label="Order source">
            <select
              value={source}
              onChange={(event) =>
                setSource(event.target.value as 'walk-in' | 'whatsapp')
              }
            >
              <option value="whatsapp">WhatsApp</option>
              <option value="walk-in">Walk-in</option>
            </select>
          </Field>
          <Field label="Customer">
            <select
              value={customerId ?? ''}
              onChange={(event) =>
                setCustomerId(event.target.value ? Number(event.target.value) : null)
              }
              disabled={customers.loading}
            >
              <option value="">New / walk-in customer</option>
              {customers.data?.map((customer) => (
                <option key={customer.id} value={customer.id}>
                  {customer.name}
                  {customer.phone ? ` · ${customer.phone}` : ''}
                </option>
              ))}
            </select>
          </Field>
          <ErrorNotice message={customers.error} retry={customers.reload} />
          {customerId === null && (
            <Field label="Customer name (optional)">
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Who is the order for?"
                maxLength={160}
              />
            </Field>
          )}
          <Field label="Order request">
            <textarea
              aria-label="Order request"
              autoFocus
              required
              rows={5}
              maxLength={5000}
              value={note}
              onChange={(event) => {
                setNote(event.target.value);
                setRows(null);
                setReviewed(false);
                setExtractError('');
                setError('');
              }}
              placeholder={
                source === 'whatsapp'
                  ? 'Paste the customer’s message here…'
                  : 'Products, quantities, collection time…'
              }
            />
          </Field>
          <div className="extract-actions">
            <Button
              variant="secondary"
              busy={extracting}
              onClick={extractItems}
              disabled={!note.trim() || note.length > 2000 || !extraction.data?.available}
            >
              <Sparkles size={17} /> Extract items
            </Button>
            {extraction.data?.enabled && (
              <small>
                {extraction.data.remaining} of {extraction.data.daily_limit} suggestions
                left today
              </small>
            )}
          </div>
          <p className="extraction-hint">
            {note.length > 2000
              ? 'Shorten the request to 2000 characters to extract items; the full note can still be saved.'
              : extraction.data?.reason ||
                'The request and product names are sent to Groq. Leave out personal or payment details.'}
          </p>
          <ErrorNotice message={extraction.error} retry={extraction.reload} />
          <ErrorNotice message={extractError} />
          <ErrorNotice message={products.error} retry={products.reload} />
          {rows !== null ? (
            <>
              <OrderDraft
                rows={rows}
                products={products.data || []}
                onChange={changeRows}
                onAdd={addRow}
              />
              {rows.length > 0 && (
                <label className="draft-review">
                  <input
                    type="checkbox"
                    checked={reviewed}
                    disabled={invalid}
                    onChange={(event) => setReviewed(event.target.checked)}
                  />
                  <span>
                    I checked every item and quantity against the original request.
                  </span>
                </label>
              )}
              <Button
                variant="ghost"
                onClick={() => {
                  setRows(null);
                  setReviewed(false);
                }}
              >
                Use note only
              </Button>
            </>
          ) : (
            <Button
              variant="ghost"
              onClick={addRow}
              disabled={products.loading || !products.data?.length}
            >
              Add items manually
            </Button>
          )}
          <ErrorNotice message={error} />
        </fieldset>
        <div className="form-actions">
          <Button disabled={working} variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="submit"
            busy={busy}
            disabled={
              working || !note.trim() || invalid || Boolean(rows?.length && !reviewed)
            }
          >
            Save order
          </Button>
        </div>
      </form>
    </Modal>
  );
}
