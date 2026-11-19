import { Plus, X } from 'lucide-react';
import { Button, Field } from './components';
import { positive } from './format';
import type { DraftRow, Product } from './types';

export function draftIssue(row: DraftRow, products: Product[]) {
  const product = products.find((p) => p.code === row.product_code);
  if (!product) return 'Choose the exact product and pack size.';
  const value = row.quantity || '';
  if (!positive(value)) return 'Enter a positive quantity.';
  const [whole, fraction = ''] = value.split('.');
  if (BigInt(whole) > 1000000n || (BigInt(whole) === 1000000n && /[1-9]/.test(fraction)))
    return 'Quantity must be at most 1000000.';
  if (product.unit === 'piece') {
    if (row.unit !== 'piece') return 'Packaged products use pieces.';
    if (/[1-9]/.test(fraction)) return 'Enter a whole number of pieces.';
  } else {
    if (row.unit !== 'g' && row.unit !== 'kg') return 'Choose grams or kilograms.';
    if (
      (row.unit === 'g' && /[1-9]/.test(fraction)) ||
      (row.unit === 'kg' && /[1-9]/.test(fraction.slice(3)))
    )
      return 'Loose quantities must be accurate to a whole gram.';
  }
  return row.reason || '';
}

export function OrderDraft({
  rows,
  products,
  onChange,
  onAdd,
}: {
  rows: DraftRow[];
  products: Product[];
  onChange: (rows: DraftRow[]) => void;
  onAdd: () => void;
}) {
  function edit(id: number, patch: Partial<DraftRow>) {
    onChange(
      rows.map((row) => (row.id === id ? { ...row, ...patch, reason: null } : row)),
    );
  }

  return (
    <section className="order-draft" aria-label="Review order items">
      <h3>Review the items</h3>
      <p>Compare every row with the request above. Correct or remove uncertain items.</p>
      {rows.length === 0 && <p>No items selected. Add items or save just the note.</p>}
      {rows.map((row, index) => {
        const issue = draftIssue(row, products);
        return (
          <div className="draft-row" key={row.id}>
            <div className="draft-row-head">
              <span>{row.original || `Item ${index + 1}`}</span>
              <button
                type="button"
                className="icon-button"
                aria-label={`Remove item ${index + 1}`}
                onClick={() => onChange(rows.filter((r) => r.id !== row.id))}
              >
                <X size={18} />
              </button>
            </div>
            <Field label={`Product ${index + 1}`}>
              <select
                aria-label={`Product ${index + 1}`}
                value={row.product_code || ''}
                onChange={(event) => {
                  const code = event.target.value;
                  const product = products.find((p) => p.code === code);
                  const compatible =
                    product?.unit === 'piece'
                      ? row.unit === 'piece'
                      : row.unit === 'kg' || row.unit === 'g';
                  edit(row.id, {
                    product_code: code || null,
                    unit: compatible ? row.unit : null,
                  });
                }}
              >
                <option value="">Choose product / pack size</option>
                {products.map((product) => (
                  <option key={product.code} value={product.code}>
                    {product.name} · {product.code}
                  </option>
                ))}
              </select>
            </Field>
            <div className="draft-quantity">
              <Field label={`Quantity ${index + 1}`}>
                <input
                  value={row.quantity || ''}
                  inputMode="decimal"
                  maxLength={32}
                  onChange={(event) => edit(row.id, { quantity: event.target.value })}
                />
              </Field>
              <Field label={`Unit ${index + 1}`}>
                <select
                  aria-label={`Unit ${index + 1}`}
                  value={row.unit || ''}
                  onChange={(event) =>
                    edit(row.id, {
                      unit: (event.target.value || null) as DraftRow['unit'],
                    })
                  }
                >
                  <option value="">Choose unit</option>
                  <option value="kg">kg</option>
                  <option value="g">g</option>
                  <option value="piece">pieces</option>
                </select>
              </Field>
            </div>
            {issue && (
              <p className="draft-issue" role="status">
                {issue}
              </p>
            )}
            {row.reason && !draftIssue({ ...row, reason: null }, products) && (
              <Button variant="secondary" onClick={() => edit(row.id, {})}>
                Confirm this item
              </Button>
            )}
          </div>
        );
      })}
      <Button variant="secondary" onClick={onAdd} disabled={rows.length >= 50}>
        <Plus size={17} /> Add item
      </Button>
    </section>
  );
}
