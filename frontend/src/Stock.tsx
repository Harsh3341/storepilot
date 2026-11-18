import { useState } from 'react';
import {
  ArrowDownToLine,
  History as HistoryIcon,
  Package,
  Pencil,
  Plus,
  Scale,
  SlidersHorizontal,
} from 'lucide-react';
import { friendlyError, post, useData, useRequestId } from './api';
import {
  Button,
  Empty,
  ErrorNotice,
  Field,
  Loading,
  Modal,
  SearchField,
} from './components';
import { dateText, money, paise, positive, quantityText } from './format';
import type { Movement, Product } from './types';

export function Stock({ version, onChange }: { version: number; onChange: () => void }) {
  const [search, setSearch] = useState('');
  const [low, setLow] = useState(false);
  const data = useData<Product[]>(
    `/api/products?q=${encodeURIComponent(search)}`,
    version,
  );
  const [editing, setEditing] = useState<Product | 'new' | null>(null);
  const [movement, setMovement] = useState<{
    product: Product;
    kind: 'receive' | 'adjust';
  } | null>(null);
  const [history, setHistory] = useState<Product | null>(null);
  const products = data.data?.filter((p) => !low || p.low_stock) || [];
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Keep your shelves ready</h1>
          <p>Your products, prices, and stock in one place.</p>
        </div>
        <Button onClick={() => setEditing('new')}>
          <Plus size={19} />
          Add product
        </Button>
      </div>
      <section className="surface">
        <div className="list-toolbar">
          <SearchField
            value={search}
            onChange={setSearch}
            placeholder="Search product name or code"
          />
          <button
            className={`filter-button ${low ? 'active' : ''}`}
            onClick={() => setLow((v) => !v)}
          >
            <SlidersHorizontal size={18} />
            Low stock only{low && <span className="filter-check">✓</span>}
          </button>
        </div>
        <ErrorNotice message={data.error} retry={data.reload} />
        {data.loading ? (
          <Loading />
        ) : products.length ? (
          <div className="stock-table">
            <div className="stock-table-head">
              <span>Product</span>
              <span>Price</span>
              <span>In stock</span>
              <span>Actions</span>
            </div>
            {products.map((product) => (
              <div className="stock-row" key={product.code}>
                <div className="stock-product">
                  <span className={`product-icon ${product.unit}`}>
                    {product.unit === 'kg' ? <Scale size={23} /> : <Package size={23} />}
                  </span>
                  <div>
                    <strong>{product.name}</strong>
                    <small>
                      {product.code} ·{' '}
                      {product.unit === 'kg' ? 'Loose goods' : 'Packaged'}
                    </small>
                  </div>
                </div>
                <div className="stock-price">
                  <small className="mobile-only">Price</small>
                  <strong>{money(product.price)}</strong>
                  <span> / {product.unit === 'kg' ? 'kg' : 'pc'}</span>
                </div>
                <div className="stock-quantity">
                  <small className="mobile-only">In stock</small>
                  <strong className={product.low_stock ? 'low-stock-text' : ''}>
                    {quantityText(product.stock, product.unit)}
                  </strong>
                  {product.low_stock && <span className="stock-status">Low stock</span>}
                  <small>
                    Reorder at {quantityText(product.reorder_level, product.unit)}
                  </small>
                </div>
                <div className="stock-actions">
                  <Button
                    variant="secondary"
                    onClick={() => setMovement({ product, kind: 'receive' })}
                  >
                    <ArrowDownToLine size={17} />
                    Add stock
                  </Button>
                  <button
                    className="icon-button"
                    aria-label={`Edit ${product.name}`}
                    title="Edit product"
                    onClick={() => setEditing(product)}
                  >
                    <Pencil size={18} />
                  </button>
                  <button
                    className="icon-button"
                    aria-label={`Adjust ${product.name} stock`}
                    title="Adjust stock"
                    onClick={() => setMovement({ product, kind: 'adjust' })}
                  >
                    <SlidersHorizontal size={18} />
                  </button>
                  <button
                    className="icon-button"
                    aria-label={`View ${product.name} stock movements`}
                    title="Stock history"
                    onClick={() => setHistory(product)}
                  >
                    <HistoryIcon size={18} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          !data.error && (
            <Empty
              title={low ? 'No low-stock products' : 'No products found'}
              text={
                search
                  ? 'Try another name or product code.'
                  : low
                    ? 'Your shelves are looking good.'
                    : 'Add products and opening stock to begin.'
              }
            >
              {!search && !low && (
                <Button onClick={() => setEditing('new')}>
                  <Plus size={18} />
                  Add product
                </Button>
              )}
            </Empty>
          )
        )}
      </section>
      {editing && (
        <ProductForm
          product={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            onChange();
          }}
        />
      )}{' '}
      {movement && (
        <StockForm
          {...movement}
          onClose={() => setMovement(null)}
          onSaved={() => {
            setMovement(null);
            onChange();
          }}
        />
      )}{' '}
      {history && (
        <MovementHistory
          product={history}
          onClose={() => setHistory(null)}
          version={version}
        />
      )}
    </>
  );
}
function validQty(value: string, unit: string, signed = false) {
  return (
    (signed ? /^-?\d+(\.\d+)?$/ : /^\d+(\.\d+)?$/).test(value) &&
    (unit !== 'piece' || (signed ? /^-?\d+$/ : /^\d+$/).test(value))
  );
}
function ProductForm({
  product,
  onClose,
  onSaved,
}: {
  product: Product | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [code, setCode] = useState(product?.code || '');
  const [name, setName] = useState(product?.name || '');
  const [unit, setUnit] = useState<'kg' | 'piece'>(product?.unit || 'piece');
  const [price, setPrice] = useState(product?.price || '');
  const [opening, setOpening] = useState('0');
  const [reorder, setReorder] = useState(product?.reorder_level || '0');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const cents = paise(price);
  const valid =
    !!code.trim() &&
    !!name.trim() &&
    cents !== null &&
    cents >= 0n &&
    validQty(reorder, unit) &&
    (product || validQty(opening, unit));
  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (busy || !valid) return;
    setBusy(true);
    setError('');
    try {
      await post(
        product ? `/api/products/${encodeURIComponent(product.code)}` : '/api/products',
        product
          ? { name: name.trim(), price, reorder_level: reorder }
          : {
              code: code.trim(),
              name: name.trim(),
              unit,
              price,
              opening_stock: opening,
              reorder_level: reorder,
            },
        product ? 'PUT' : 'POST',
      );
      onSaved();
    } catch (e) {
      setError(friendlyError(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal busy={busy} title={product ? 'Edit product' : 'Add product'} onClose={onClose}>
      <form onSubmit={save}>
        <Field label="Product name">
          <input
            autoFocus
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Aashirvaad Atta 1 kg"
            maxLength={160}
          />
        </Field>
        <div className="field-pair">
          <Field
            label="Product code"
            hint={
              product
                ? 'The product code stays the same.'
                : 'A short, unique code for this product.'
            }
          >
            <input
              required
              disabled={!!product}
              value={code}
              onChange={(e) => setCode(e.target.value.toUpperCase())}
              placeholder="e.g. ATTA-1KG"
              maxLength={50}
            />
          </Field>
          <Field
            label="Sold by"
            hint={
              product
                ? 'The selling unit stays the same.'
                : 'Each brand and pack size needs its own code.'
            }
          >
            <select
              value={unit}
              disabled={!!product}
              onChange={(e) => setUnit(e.target.value as 'kg' | 'piece')}
            >
              <option value="piece">Whole pieces / packets</option>
              <option value="kg">Weight / kilograms</option>
            </select>
          </Field>
        </div>
        <Field label={`Selling price per ${unit === 'kg' ? 'kilogram' : 'piece'} (₹)`}>
          <input
            required
            inputMode="decimal"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            placeholder="0.00"
          />
        </Field>
        <div className="field-pair">
          {!product && (
            <Field label={`Opening stock (${unit === 'kg' ? 'kg' : 'pieces'})`}>
              <input
                required
                inputMode={unit === 'kg' ? 'decimal' : 'numeric'}
                value={opening}
                onChange={(e) => setOpening(e.target.value)}
              />
            </Field>
          )}
          <Field
            label={`Low-stock alert at (${unit === 'kg' ? 'kg' : 'pieces'})`}
            hint="Alert when stock reaches this quantity."
          >
            <input
              required
              inputMode={unit === 'kg' ? 'decimal' : 'numeric'}
              value={reorder}
              onChange={(e) => setReorder(e.target.value)}
            />
          </Field>
        </div>
        <ErrorNotice message={error} />
        <div className="form-actions">
          <Button disabled={busy} variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" busy={busy} disabled={!valid}>
            {product ? 'Save changes' : 'Add product'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
function StockForm({
  product,
  kind,
  onClose,
  onSaved,
}: {
  product: Product;
  kind: 'receive' | 'adjust';
  onClose: () => void;
  onSaved: () => void;
}) {
  const [value, setValue] = useState('');
  const [unit, setUnit] = useState<'kg' | 'g' | 'piece'>(product.unit);
  const [reason, setReason] = useState('');
  const [reference, setReference] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const requestId = useRequestId();
  const valid =
    validQty(value, unit, kind === 'adjust') &&
    /[1-9]/.test(value) &&
    (kind !== 'receive' || positive(value)) &&
    (kind !== 'adjust' || !!reason.trim());
  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (busy || !valid) return;
    setBusy(true);
    setError('');
    const payload = {
      product_code: product.code,
      quantity: value,
      unit,
      kind,
      reason: reason.trim(),
      reference: reference.trim(),
    };
    try {
      await post('/api/stock', { ...payload, request_id: requestId(payload) });
      requestId.reset();
      onSaved();
    } catch (e) {
      setError(friendlyError(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      busy={busy}
      title={kind === 'receive' ? 'Add stock' : 'Adjust stock'}
      onClose={onClose}
    >
      <form onSubmit={save}>
        <div className="form-product">
          <strong>{product.name}</strong>
          <p>Currently {quantityText(product.stock, product.unit)} in stock</p>
        </div>
        <div className="field-pair">
          <Field
            label={kind === 'receive' ? 'Quantity received' : 'Quantity to add or remove'}
            hint={
              kind === 'adjust'
                ? 'Use − for removal, e.g. −2 for damaged stock.'
                : undefined
            }
          >
            <input
              autoFocus
              required
              inputMode={kind === 'adjust' ? 'text' : 'decimal'}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={kind === 'adjust' ? 'e.g. -2' : 'e.g. 10'}
            />
          </Field>
          <Field label="Unit">
            <select
              value={unit}
              onChange={(e) => setUnit(e.target.value as 'kg' | 'g' | 'piece')}
            >
              {product.unit === 'kg' ? (
                <>
                  <option value="kg">Kilograms (kg)</option>
                  <option value="g">Grams (g)</option>
                </>
              ) : (
                <option value="piece">Pieces / packets</option>
              )}
            </select>
          </Field>
        </div>
        <Field label={kind === 'adjust' ? 'Reason (required)' : 'Note (optional)'}>
          <input
            required={kind === 'adjust'}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder={
              kind === 'adjust'
                ? 'e.g. Damaged packets, stock count correction'
                : 'e.g. New delivery'
            }
          />
        </Field>
        <Field label="Supplier / reference (optional)">
          <input
            value={reference}
            onChange={(e) => setReference(e.target.value)}
            placeholder="Supplier name or delivery bill number"
          />
        </Field>
        <ErrorNotice message={error} />
        <div className="form-actions">
          <Button disabled={busy} variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" busy={busy} disabled={!valid}>
            {kind === 'receive' ? 'Add stock' : 'Save adjustment'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
function MovementHistory({
  product,
  onClose,
  version,
}: {
  product: Product;
  onClose: () => void;
  version: number;
}) {
  const data = useData<Movement[]>(
    `/api/products/${encodeURIComponent(product.code)}/movements`,
    version,
  );
  const labels: Record<string, string> = {
    receive: 'Stock received',
    adjust: 'Stock adjustment',
    sale: 'Sale',
    opening: 'Opening stock',
  };
  return (
    <Modal title="Stock history" onClose={onClose} wide>
      <div className="form-product">
        <strong>{product.name}</strong>
        <p>{product.code}</p>
      </div>
      <ErrorNotice message={data.error} retry={data.reload} />
      {data.loading ? (
        <Loading />
      ) : data.data?.length ? (
        <div className="activity-list">
          {data.data.map((entry) => (
            <div className="activity-row" key={entry.id}>
              <span className="activity-icon">
                <Package size={19} />
              </span>
              <div className="activity-main">
                <strong>{labels[entry.kind] || entry.kind}</strong>
                <p>
                  {entry.reason ||
                    entry.reference ||
                    (entry.sale_id ? `Sale #${entry.sale_id}` : 'Stock updated')}
                </p>
                {entry.reason && entry.reference && <p>{entry.reference}</p>}
                <small>{dateText(entry.created_at)}</small>
              </div>
              <strong className={entry.quantity.startsWith('-') ? '' : 'green-text'}>
                {entry.quantity.startsWith('-') ? '' : '+'}
                {quantityText(entry.quantity, entry.unit)}
              </strong>
            </div>
          ))}
        </div>
      ) : (
        <Empty
          title="No stock movements yet"
          text="Opening stock, deliveries, and sales will appear here."
        />
      )}
      <div className="form-actions">
        <Button variant="secondary" onClick={onClose}>
          Close
        </Button>
      </div>
    </Modal>
  );
}
