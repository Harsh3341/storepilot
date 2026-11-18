import { useState } from 'react';
import { Check, Printer, Share2, Store } from 'lucide-react';
import { Button, ErrorNotice, Modal } from './components';
import { dateText, money, paise, quantityText } from './format';
import type { Sale } from './types';

export function Receipt({ sale, onClose }: { sale: Sale; onClose: () => void }) {
  const [shared, setShared] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function shareReceipt() {
    if (busy) return;
    setBusy(true);
    setError('');
    const text = [
      `StorePilot · Bill ${sale.number}`,
      dateText(sale.created_at),
      `Customer: ${sale.customer_name || 'Walk-in'}`,
      '',
      ...sale.lines.map(
        (line) =>
          `${line.name} — ${quantityText(line.quantity, line.unit)} — ${money(line.amount)}`,
      ),
      '',
      `Total: ${money(sale.total)}`,
      `Paid (${sale.payment_method === 'upi' ? 'UPI' : 'cash'}): ${money(sale.paid_amount)}`,
      `Udhaar: ${money(sale.due_amount)}`,
      'Thank you for shopping with us!',
    ].join('\n');
    try {
      if (navigator.share) await navigator.share({ title: `Bill ${sale.number}`, text });
      else if (navigator.clipboard) {
        await navigator.clipboard.writeText(text);
        setShared(true);
      } else {
        const input = document.createElement('textarea');
        input.value = text;
        input.style.position = 'fixed';
        input.style.opacity = '0';
        document.body.append(input);
        input.select();
        const copied = document.execCommand('copy');
        input.remove();
        if (!copied)
          throw new Error('Could not copy this receipt. Try printing it instead.');
        setShared(true);
      }
    } catch (error) {
      if (!(error instanceof DOMException && error.name === 'AbortError'))
        setError(
          error instanceof Error ? error.message : 'Could not share this receipt.',
        );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Saved receipt" onClose={onClose}>
      <div className="receipt-confirmation">
        <span>
          <Check size={18} />
        </span>
        Sale saved. Stock and payment updated.
      </div>
      <div className="receipt-sheet" id="print-receipt">
        <div className="receipt-brand">
          <Store size={30} />
          <h2>StorePilot</h2>
          <p>Thank you for shopping with us</p>
        </div>
        <div className="receipt-meta">
          <strong>{sale.number}</strong>
          <span>{dateText(sale.created_at)}</span>
          <span>{sale.customer_name || 'Walk-in customer'}</span>
        </div>
        <div className="receipt-lines">
          <div className="receipt-line-head">
            <span>Item</span>
            <span>Amount</span>
          </div>
          {sale.lines.map((line, index) => (
            <div className="receipt-line" key={`${line.product_code}-${index}`}>
              <div>
                <strong>{line.name}</strong>
                <small>
                  {quantityText(line.quantity, line.unit)} × {money(line.price)} /{' '}
                  {line.unit === 'kg' ? 'kg' : 'pc'}
                </small>
              </div>
              <strong>{money(line.amount)}</strong>
            </div>
          ))}
        </div>
        <div className="receipt-total">
          <span>Total</span>
          <strong>{money(sale.total)}</strong>
        </div>
        <div className="receipt-payment">
          <span>Paid by {sale.payment_method === 'upi' ? 'UPI' : 'cash'}</span>
          <strong>{money(sale.paid_amount)}</strong>
        </div>
        <div
          className={`receipt-payment ${(paise(sale.due_amount) || 0n) > 0n ? 'due-text' : ''}`}
        >
          <span>Udhaar / due</span>
          <strong>{money(sale.due_amount)}</strong>
        </div>
        <p className="receipt-bottom">Saved bill · {sale.number}</p>
      </div>
      <ErrorNotice message={error} />
      {shared && (
        <p className="copy-success" role="status">
          <Check size={17} />
          Receipt copied. Paste it into a message.
        </p>
      )}
      <div className="receipt-actions">
        <Button variant="secondary" onClick={() => window.print()}>
          <Printer size={18} />
          Print
        </Button>
        <Button busy={busy} onClick={shareReceipt}>
          <Share2 size={18} />
          {shared ? 'Copy again' : 'Share receipt'}
        </Button>
      </div>
      <Button className="receipt-done" variant="ghost" onClick={onClose}>
        Done
      </Button>
    </Modal>
  );
}
