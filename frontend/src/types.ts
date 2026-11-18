export type Unit = 'kg' | 'piece';
export type InputUnit = Unit | 'g' | null;
export type Product = {
  code: string;
  name: string;
  unit: Unit;
  price: string;
  stock: string;
  reorder_level: string;
  low_stock: boolean;
};
export type Item = { product_code: string; quantity: string; unit: InputUnit };
export type Line = {
  product_code: string;
  name: string;
  quantity: string;
  unit: Unit;
  price: string;
  amount: string;
};
export type Preview = {
  kind: 'draft';
  currency: string;
  saved: false;
  lines: Line[];
  total: string;
};
export type Customer = { id: number; name: string; phone: string; balance: string };
export type Sale = {
  id: number;
  number: string;
  created_at: string;
  customer_id: number | null;
  customer_name: string | null;
  total: string;
  paid_amount: string;
  due_amount: string;
  payment_method: 'cash' | 'upi';
  lines: Line[];
  kind: 'sale';
  saved: true;
};
export type Order = {
  id: number;
  customer_id: number | null;
  customer_name: string;
  source: 'walk-in' | 'whatsapp';
  note: string;
  status: 'pending' | 'ready' | 'completed' | 'cancelled';
  created_at: string;
  items: (Item & { name: string })[];
  estimated_total: string | null;
  sale_id: number | null;
};
export type Movement = {
  id: number;
  kind: string;
  quantity: string;
  unit: Unit;
  reference: string;
  reason: string;
  created_at: string;
  sale_id: number | null;
};
export type Ledger = {
  customer: Customer;
  entries: {
    id: number;
    kind: string;
    description: string;
    amount: string;
    created_at: string;
    sale_id: number | null;
  }[];
};
export type Summary = {
  today: {
    sales_count: number;
    sales_total: string;
    paid_total: string;
    credit_total: string;
  };
  outstanding_total: string;
  low_stock_count: number;
  pending_orders_count: number;
};
export type Page = 'sell' | 'stock' | 'customers' | 'orders' | 'history';
