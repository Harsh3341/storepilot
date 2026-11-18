import { useEffect, useMemo, useState } from 'react';
import {
  ArrowRight,
  Check,
  ChevronDown,
  Minus,
  Package,
  Plus,
  Scale,
  ShoppingBasket,
  Trash2,
  UserRound,
  ClipboardList,
  Info,
} from 'lucide-react';
import { api, friendlyError, post, useData, useRequestId } from './api';
import {
  Button,
  Empty,
  ErrorNotice,
  Field,
  Loading,
  Modal,
  NewCustomer,
  SearchField,
} from './components';
import {
  decimalAdd,
  fromPaise,
  money,
  paise,
  positive,
  quantity,
  quantityText,
} from './format';
import type { Customer, Item, Order, Preview, Product, Sale } from './types';

function gramsToKg(value: string) {
  const [whole, fraction = ''] = value.split('.');
  const digits = (whole + fraction).padStart(4 + fraction.length, '0');
  return quantity(
    `${digits.slice(0, -3 - fraction.length)}.${digits.slice(-3 - fraction.length)}`,
  );
}
function kgToGrams(value: string) {
  const [whole, fraction = ''] = value.split('.');
  const text = whole + fraction.padEnd(3, '0');
  return quantity(
    fraction.length > 3
      ? `${text.slice(0, text.length - fraction.length + 3)}.${text.slice(text.length - fraction.length + 3)}`
      : String(BigInt(text)),
  );
}
export function Sell({
  onBusyChange,
  version,
  onChange,
  linkedOrder,
  onOrderCleared,
  onReceipt,
  onStock,
}: {
  onBusyChange: (value: boolean) => void;
  version: number;
  onChange: () => void;
  linkedOrder: Order | null;
  onOrderCleared: () => void;
  onReceipt: (sale: Sale) => void;
  onStock: () => void;
}) {
  const products = useData<Product[]>('/api/products', version);
  const customers = useData<Customer[]>('/api/customers', version);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [items, setItems] = useState<Item[]>([]);
  const [editor, setEditor] = useState<{ product: Product; existing?: Item } | null>(
    null,
  );
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewVersion, setPreviewVersion] = useState(-1);
  const [previewRetry, setPreviewRetry] = useState(0);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewError, setPreviewError] = useState('');
  const [customerId, setCustomerId] = useState<number | null>(null);
  const [newCustomer, setNewCustomer] = useState(false);
  const [method, setMethod] = useState<'cash' | 'upi'>('cash');
  const [fullPaid, setFullPaid] = useState(true);
  const [paid, setPaid] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [saveOrder, setSaveOrder] = useState(false);
  const [mobileBill, setMobileBill] = useState(false);
  const requestId = useRequestId();
  useEffect(() => onBusyChange(busy), [busy, onBusyChange]);
  useEffect(() => {
    if (linkedOrder) {
      setItems(
        linkedOrder.items.map(({ product_code, quantity, unit }) => ({
          product_code,
          quantity,
          unit,
        })),
      );
      setCustomerId(linkedOrder.customer_id);
      setFullPaid(true);
      setError('');
    }
  }, [linkedOrder]);
  useEffect(() => {
    if (!items.length) {
      setPreview(null);
      setPreviewError('');
      setPreviewBusy(false);
      return;
    }
    const controller = new AbortController();
    setPreviewBusy(true);
    setPreview(null);
    setPreviewError('');
    setError('');
    api<Preview>('/bills/preview', {
      method: 'POST',
      body: JSON.stringify({ items }),
      signal: controller.signal,
    })
      .then((result) => {
        if (!controller.signal.aborted) {
          setPreview(result);
          setPreviewVersion(version);
        }
      })
      .catch((e: Error) => {
        if (e.name !== 'AbortError') setPreviewError(friendlyError(e));
      })
      .finally(() => {
        if (!controller.signal.aborted) setPreviewBusy(false);
      });
    return () => controller.abort();
  }, [items, version, previewRetry]);
  const shown = useMemo(
    () =>
      products.data?.filter(
        (p) =>
          `${p.name} ${p.code}`.toLowerCase().includes(search.toLowerCase()) &&
          (filter === 'all' || p.unit === filter),
      ) || [],
    [products.data, search, filter],
  );
  const sampleNotice =
    products.data?.length && products.data.every((p) => !/[1-9]/.test(p.stock));
  const amount = fullPaid ? preview?.total || '0' : paid;
  const totalPaise = paise(preview?.total || '0') || 0n;
  const paidPaise = paise(amount);
  const due = paidPaise === null ? null : totalPaise - paidPaise;
  const validPayment =
    paidPaise !== null &&
    paidPaise >= 0n &&
    due !== null &&
    due >= 0n &&
    (due === 0n || customerId !== null);
  function add(
    product: Product,
    value: string,
    unit: 'g' | 'kg' | 'piece',
    replace = false,
  ) {
    const normalized = unit === 'g' ? gramsToKg(value) : value;
    setItems((current) => {
      const index = current.findIndex((i) => i.product_code === product.code);
      if (index < 0)
        return [
          ...current,
          { product_code: product.code, quantity: normalized, unit: product.unit },
        ];
      return current.map((i, n) =>
        n === index
          ? {
              ...i,
              quantity: replace ? normalized : decimalAdd(i.quantity, normalized),
              unit: product.unit,
            }
          : i,
      );
    });
    setEditor(null);
  }
  function choose(product: Product) {
    if (product.unit === 'piece') add(product, '1', 'piece');
    else setEditor({ product });
  }
  function changePieces(item: Item, delta: number) {
    const value = BigInt(quantity(item.quantity)) + BigInt(delta);
    setItems((current) =>
      value <= 0n
        ? current.filter((i) => i !== item)
        : current.map((i) => (i === item ? { ...i, quantity: String(value) } : i)),
    );
  }
  function reset() {
    setItems([]);
    setCustomerId(null);
    setFullPaid(true);
    setPaid('');
    setError('');
    setMobileBill(false);
    onOrderCleared();
  }
  async function finish() {
    if (
      busy ||
      !preview ||
      !validPayment ||
      previewVersion !== version ||
      products.loading
    )
      return;
    setBusy(true);
    setError('');
    const payload = {
      items,
      customer_id: customerId,
      paid_amount: amount,
      payment_method: method,
      order_id: linkedOrder?.id || null,
    };
    try {
      const sale = await post<Sale>('/api/sales', {
        ...payload,
        request_id: requestId(payload),
      });
      requestId.reset();
      reset();
      onChange();
      onReceipt(sale);
    } catch (e) {
      setError(friendlyError(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      {!!sampleNotice && (
        <div className="sample-notice">
          <Info size={21} />
          <div>
            <strong>Make this catalogue yours</strong>
            <span>
              Sample catalogue: update prices and add opening stock before real billing.
            </span>
          </div>
          <Button disabled={busy} variant="secondary" onClick={onStock}>
            Set up stock <ArrowRight size={17} />
          </Button>
        </div>
      )}
      <div className="sell-layout">
        <section className="catalogue">
          <div className="section-heading">
            <h2>
              Products <span className="muted-count">{products.data?.length || 0}</span>
            </h2>
            <span className="muted">Tap to add to bill</span>
          </div>
          <SearchField
            value={search}
            onChange={setSearch}
            placeholder="Search product name or code"
          />
          <div className="filter-tabs" role="group" aria-label="Product type">
            {[
              ['all', 'All products'],
              ['kg', 'Loose goods'],
              ['piece', 'Packaged'],
            ].map(([value, label]) => (
              <button
                key={value}
                onClick={() => setFilter(value)}
                className={filter === value ? 'active' : ''}
              >
                {label}
              </button>
            ))}
          </div>
          <ErrorNotice message={products.error} retry={products.reload} />
          {products.loading ? (
            <Loading />
          ) : shown.length ? (
            <div className="product-grid">
              {shown.map((product) => {
                const inBill = items.find((i) => i.product_code === product.code);
                return (
                  <button
                    disabled={busy}
                    className={`product-card ${inBill ? 'in-bill' : ''}`}
                    key={product.code}
                    onClick={() => choose(product)}
                  >
                    <div className="product-card-top">
                      <span className={`product-icon ${product.unit}`}>
                        {product.unit === 'kg' ? (
                          <Scale size={24} />
                        ) : (
                          <Package size={24} />
                        )}
                      </span>
                      <span className="product-code">{product.code}</span>
                    </div>
                    <h3>{product.name}</h3>
                    <div className="product-price">
                      {money(product.price)}
                      <span>/{product.unit === 'kg' ? 'kg' : 'pc'}</span>
                    </div>
                    <div className="product-card-bottom">
                      <span className={product.low_stock ? 'low-stock-text' : ''}>
                        {/[1-9]/.test(product.stock)
                          ? `${quantityText(product.stock, product.unit)} left`
                          : 'No stock yet'}
                      </span>
                      <span className="add-product">
                        {inBill ? <Check size={18} /> : <Plus size={19} />}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          ) : (
            !products.error && (
              <Empty
                title="No products found"
                text={
                  search
                    ? 'Try another name or product code.'
                    : 'Add your first product in Stock.'
                }
              >
                {!search && <Button onClick={onStock}>Add products</Button>}
              </Empty>
            )
          )}
        </section>
        <aside className={`bill-panel ${mobileBill ? 'mobile-open' : ''}`}>
          <div className="bill-panel-head">
            <div>
              <ShoppingBasket size={22} />
              <h2>Current bill</h2>
              <span className="muted-count">{items.length}</span>
            </div>
            <button
              className="icon-button mobile-only"
              aria-label="Close bill"
              onClick={() => setMobileBill(false)}
            >
              <ChevronDown size={23} />
            </button>
            {!!items.length && (
              <button
                disabled={busy}
                className="text-button desktop-only"
                onClick={() => {
                  if (window.confirm('Clear all items from this draft bill?')) reset();
                }}
              >
                Clear
              </button>
            )}
          </div>
          {linkedOrder && (
            <div className="order-note">
              <ClipboardList size={18} />
              <div>
                <strong>
                  Order #{linkedOrder.id} · {linkedOrder.customer_name || 'Walk-in'}
                </strong>
                <p>{linkedOrder.note || 'Items from this order are ready to bill.'}</p>
              </div>
              <button disabled={busy} className="text-button" onClick={onOrderCleared}>
                Unlink
              </button>
            </div>
          )}
          {!items.length ? (
            <div className="cart-empty">
              <ShoppingBasket size={48} strokeWidth={1.3} />
              <h3>Your bill starts here</h3>
              <p>
                Tap a product to add it.
                <br />
                Loose goods? Choose grams or kilos.
              </p>
              <div className="draft-note">No sale, stock, or payment has been saved.</div>
            </div>
          ) : (
            <>
              <div className="cart-items">
                {items.map((item) => {
                  const product = products.data?.find(
                    (p) => p.code === item.product_code,
                  );
                  const line = preview?.lines.find(
                    (l) => l.product_code === item.product_code,
                  );
                  return (
                    <div className="cart-item" key={item.product_code}>
                      <div className="cart-item-title">
                        <strong>
                          {line?.name || product?.name || item.product_code}
                        </strong>
                        <button
                          className="icon-button"
                          aria-label={`Remove ${product?.name || item.product_code}`}
                          disabled={busy}
                          onClick={() =>
                            setItems((current) => current.filter((i) => i !== item))
                          }
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                      <div className="cart-item-bottom">
                        {product?.unit === 'piece' ? (
                          <div className="stepper">
                            <button
                              aria-label={`Reduce ${product.name}`}
                              disabled={busy}
                              onClick={() => changePieces(item, -1)}
                            >
                              <Minus size={15} />
                            </button>
                            <span>{quantity(item.quantity)}</span>
                            <button
                              aria-label={`Add another ${product.name}`}
                              disabled={busy}
                              onClick={() => changePieces(item, 1)}
                            >
                              <Plus size={15} />
                            </button>
                          </div>
                        ) : (
                          <button
                            className="quantity-edit"
                            disabled={busy || !product}
                            onClick={() =>
                              product && setEditor({ product, existing: item })
                            }
                          >
                            {quantityText(item.quantity, item.unit)}
                            <ChevronDown size={14} />
                          </button>
                        )}
                        <strong>{line ? money(line.amount) : '…'}</strong>
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="checkout">
                <ErrorNotice
                  message={previewError}
                  retry={() => setPreviewRetry((value) => value + 1)}
                />
                <div className="bill-total">
                  <span>Total</span>
                  <strong>{previewBusy ? 'Calculating…' : money(preview?.total)}</strong>
                </div>
                <div className="customer-label">
                  <span>
                    <UserRound size={17} /> Customer
                  </span>
                  <button
                    className="text-button"
                    onClick={() => setNewCustomer(true)}
                    disabled={busy}
                  >
                    + Add new
                  </button>
                </div>
                <select
                  aria-label="Bill customer"
                  value={customerId ?? ''}
                  disabled={busy || customers.loading}
                  onChange={(e) =>
                    setCustomerId(e.target.value ? Number(e.target.value) : null)
                  }
                >
                  <option value="">Walk-in customer</option>
                  {customers.data?.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                      {c.phone ? ` · ${c.phone}` : ''}
                    </option>
                  ))}
                </select>
                <ErrorNotice message={customers.error} retry={customers.reload} />
                <div className="payment-heading">Payment method</div>
                <div className="payment-method">
                  <button
                    disabled={busy}
                    onClick={() => setMethod('cash')}
                    className={method === 'cash' ? 'active' : ''}
                  >
                    Cash {method === 'cash' && <Check size={16} />}
                  </button>
                  <button
                    disabled={busy}
                    onClick={() => setMethod('upi')}
                    className={method === 'upi' ? 'active' : ''}
                  >
                    UPI {method === 'upi' && <Check size={16} />}
                  </button>
                </div>
                <div className="paid-heading">
                  <span>Amount received</span>
                  <button
                    className="text-button"
                    disabled={busy}
                    onClick={() => setFullPaid(true)}
                  >
                    Full amount
                  </button>
                </div>
                <div className="money-input">
                  <span>₹</span>
                  <input
                    aria-label="Amount received"
                    inputMode="decimal"
                    value={fullPaid ? preview?.total || '' : paid}
                    disabled={busy}
                    onChange={(e) => {
                      setFullPaid(false);
                      setPaid(e.target.value);
                    }}
                  />
                </div>
                <div className={`due-row ${due && due > 0n ? 'has-due' : ''}`}>
                  <span>Udhaar / amount due</span>
                  <strong>
                    {due !== null && due >= 0n ? money(fromPaise(due)) : '—'}
                  </strong>
                </div>
                {due !== null && due > 0n && customerId === null && (
                  <p className="validation-hint">
                    Choose a customer to keep this udhaar.
                  </p>
                )}
                {due !== null && due < 0n && (
                  <p className="validation-hint">
                    Amount received cannot be more than the bill total.
                  </p>
                )}
                <ErrorNotice message={error} />
                <Button
                  className="checkout-button"
                  busy={busy}
                  disabled={
                    !preview ||
                    !validPayment ||
                    previewBusy ||
                    previewVersion !== version ||
                    products.loading
                  }
                  onClick={finish}
                >
                  Save sale <ArrowRight size={19} />
                </Button>
                <Button
                  className="save-order-button"
                  variant="secondary"
                  disabled={busy || !preview || !!linkedOrder}
                  onClick={() => setSaveOrder(true)}
                >
                  <ClipboardList size={18} />
                  Save as order
                </Button>
                <p className="draft-note">
                  Draft only. No sale, stock, or payment has been saved.
                </p>
              </div>
            </>
          )}
        </aside>
      </div>
      {!!items.length && !mobileBill && (
        <button className="mobile-bill-bar" onClick={() => setMobileBill(true)}>
          <span>
            <ShoppingBasket size={21} />
            <strong>
              {items.length} {items.length === 1 ? 'item' : 'items'}
            </strong>
          </span>
          <span>
            View bill <strong>{previewBusy ? '…' : money(preview?.total)}</strong>
            <ArrowRight size={19} />
          </span>
        </button>
      )}
      {editor && (
        <QuantityDialog
          product={editor.product}
          existing={editor.existing}
          onClose={() => setEditor(null)}
          onAdd={(value, unit) => add(editor.product, value, unit, !!editor.existing)}
        />
      )}{' '}
      {newCustomer && (
        <NewCustomer
          onClose={() => setNewCustomer(false)}
          onCreated={(c) => {
            setCustomerId(c.id);
            setNewCustomer(false);
            onChange();
          }}
        />
      )}{' '}
      {saveOrder && (
        <SaveOrderDialog
          items={items}
          customerId={customerId}
          onClose={() => setSaveOrder(false)}
          onSaved={() => {
            setSaveOrder(false);
            reset();
            onChange();
          }}
        />
      )}
    </>
  );
}
function QuantityDialog({
  product,
  existing,
  onClose,
  onAdd,
}: {
  product: Product;
  existing?: Item;
  onClose: () => void;
  onAdd: (quantity: string, unit: 'g' | 'kg' | 'piece') => void;
}) {
  const [unit, setUnit] = useState<'g' | 'kg' | 'piece'>(
    product.unit === 'kg' ? 'g' : 'piece',
  );
  const [value, setValue] = useState(
    existing
      ? product.unit === 'kg'
        ? kgToGrams(existing.quantity)
        : existing.quantity
      : product.unit === 'kg'
        ? '500'
        : '1',
  );
  const valid = positive(value) && (product.unit !== 'piece' || /^\d+$/.test(value));
  return (
    <Modal title={existing ? 'Change quantity' : 'Add loose goods'} onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) onAdd(value, unit);
        }}
      >
        <div className="quantity-product">
          <span className="product-icon kg">
            <Scale size={27} />
          </span>
          <div>
            <strong>{product.name}</strong>
            <p>
              {money(product.price)} / {product.unit === 'kg' ? 'kg' : 'pc'} ·{' '}
              {quantityText(product.stock, product.unit)} in stock
            </p>
          </div>
        </div>
        {product.unit === 'kg' && (
          <div className="filter-tabs quantity-tabs">
            {(['g', 'kg'] as const).map((u) => (
              <button
                type="button"
                key={u}
                className={unit === u ? 'active' : ''}
                onClick={() => {
                  if (u === unit) return;
                  if (positive(value))
                    setValue(u === 'kg' ? gramsToKg(value) : kgToGrams(value));
                  setUnit(u);
                }}
              >
                {u === 'g' ? 'Grams (g)' : 'Kilograms (kg)'}
              </button>
            ))}
          </div>
        )}
        <Field
          label={`Quantity in ${unit === 'g' ? 'grams' : unit === 'kg' ? 'kilograms' : 'pieces'}`}
        >
          <input
            autoFocus
            inputMode={product.unit === 'piece' ? 'numeric' : 'decimal'}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            required
          />
        </Field>
        {product.unit === 'kg' && (
          <div className="quick-quantities">
            {['250', '500', '1000'].map((g) => (
              <button
                type="button"
                key={g}
                onClick={() => {
                  setUnit('g');
                  setValue(g);
                }}
              >
                {g === '1000' ? '1 kg' : `${g} g`}
              </button>
            ))}
          </div>
        )}
        <div className="form-actions">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={!valid}>
            {existing ? 'Update quantity' : 'Add to bill'} <Plus size={17} />
          </Button>
        </div>
      </form>
    </Modal>
  );
}
function SaveOrderDialog({
  items,
  customerId,
  onClose,
  onSaved,
}: {
  items: Item[];
  customerId: number | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [note, setNote] = useState('');
  const [name, setName] = useState('');
  const [source, setSource] = useState<'walk-in' | 'whatsapp'>('walk-in');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      await post('/api/orders', {
        items,
        customer_id: customerId,
        customer_name: name,
        note,
        source,
      });
      onSaved();
    } catch (e) {
      setError(friendlyError(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal busy={busy} title="Save bill as an order" onClose={onClose}>
      <form onSubmit={save}>
        <p className="form-intro">
          Keep these items for later. Stock and payment will be saved when you bill the
          order.
        </p>
        {!customerId && (
          <Field label="Customer name (optional)">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Who is this order for?"
            />
          </Field>
        )}
        <Field label="Order source">
          <select
            value={source}
            onChange={(e) => setSource(e.target.value as 'walk-in' | 'whatsapp')}
          >
            <option value="walk-in">Walk-in</option>
            <option value="whatsapp">WhatsApp</option>
          </select>
        </Field>
        <Field label="Order note (optional)">
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={3}
            placeholder="Delivery time, special instructions…"
          />
        </Field>
        <ErrorNotice message={error} />
        <div className="form-actions">
          <Button disabled={busy} variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" busy={busy}>
            Save order
          </Button>
        </div>
      </form>
    </Modal>
  );
}
