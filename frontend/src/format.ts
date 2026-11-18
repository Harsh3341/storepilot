// Decimal text stays exact; money arithmetic uses integer paise.
export function paise(value: string) {
  const match = /^(-?)(\d+)(?:\.(\d{0,2}))?$/.exec(value.trim());
  if (!match) return null;
  return (
    (match[1] ? -1n : 1n) *
    (BigInt(match[2]) * 100n + BigInt((match[3] || '').padEnd(2, '0')))
  );
}
export function fromPaise(value: bigint) {
  const abs = value < 0n ? -value : value;
  return `${value < 0n ? '-' : ''}${abs / 100n}.${String(abs % 100n).padStart(2, '0')}`;
}
export function money(value: string | null | undefined) {
  const cents = paise(value || '0');
  if (cents === null) return `₹${value}`;
  const text = fromPaise(cents).replace('-', '');
  const [whole, fraction] = text.split('.');
  const last = whole.slice(-3);
  const head = whole.slice(0, -3);
  const grouped = head ? head.replace(/\B(?=(\d{2})+(?!\d))/g, ',') + ',' + last : last;
  return `${cents < 0n ? '−' : ''}₹${grouped}.${fraction}`;
}
export function quantity(value: string) {
  return value.includes('.') ? value.replace(/0+$/, '').replace(/\.$/, '') : value;
}
export function quantityText(value: string, unit: string | null) {
  return `${quantity(value)} ${unit === 'piece' ? 'pcs' : unit || ''}`;
}
export function dateText(value: string) {
  return new Date(value).toLocaleString('en-IN', {
    day: 'numeric',
    month: 'short',
    hour: 'numeric',
    minute: '2-digit',
  });
}
export function positive(value: string) {
  return /^\d+(\.\d+)?$/.test(value) && /[1-9]/.test(value);
}
export function decimalAdd(a: string, b: string) {
  const precision = Math.max(a.split('.')[1]?.length || 0, b.split('.')[1]?.length || 0);
  const units = (v: string) =>
    BigInt(
      v
        .replace('.', '')
        .padEnd(
          v.replace('.', '').length + precision - (v.split('.')[1]?.length || 0),
          '0',
        ),
    );
  const sum = String(units(a) + units(b)).padStart(precision + 1, '0');
  return precision ? `${sum.slice(0, -precision)}.${sum.slice(-precision)}` : sum;
}
