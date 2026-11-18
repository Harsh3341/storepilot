import { useState } from 'react';
import { ArrowUpRight, ReceiptText } from 'lucide-react';
import { api, friendlyError, useData } from './api';
import { Empty, ErrorNotice, Loading, SearchField } from './components';
import { dateText, money, paise } from './format';
import type { Sale } from './types';

export function History({
  version,
  onReceipt,
}: {
  version: number;
  onReceipt: (sale: Sale) => void;
}) {
  const data = useData<Sale[]>('/api/sales', version);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState('');
  const sales =
    data.data?.filter((sale) => {
      const matchesText = `${sale.number} ${sale.customer_name || 'Walk-in customer'}`
        .toLowerCase()
        .includes(search.toLowerCase());
      return matchesText && (filter !== 'due' || (paise(sale.due_amount) || 0n) > 0n);
    }) || [];

  async function openReceipt(id: number) {
    if (busyId !== null) return;
    setBusyId(id);
    setError('');
    try {
      onReceipt(await api<Sale>(`/api/sales/${id}`));
    } catch (error) {
      setError(friendlyError(error));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Your sales, all together</h1>
          <p>Reopen a saved bill, print a receipt, or share it with a customer.</p>
        </div>
      </div>
      <section className="surface">
        <div className="list-toolbar">
          <SearchField
            value={search}
            onChange={setSearch}
            placeholder="Search bill number or customer"
          />
          <div className="filter-tabs inline-tabs">
            <button
              className={filter === 'all' ? 'active' : ''}
              onClick={() => setFilter('all')}
            >
              All sales
            </button>
            <button
              className={filter === 'due' ? 'active' : ''}
              onClick={() => setFilter('due')}
            >
              Sold on udhaar
            </button>
          </div>
        </div>
        <ErrorNotice message={data.error} retry={data.reload} />
        <ErrorNotice message={error} />
        {data.loading ? (
          <Loading />
        ) : sales.length ? (
          <div className="sales-table">
            <div className="sales-table-head">
              <span>Bill / customer</span>
              <span>When</span>
              <span>Bill total</span>
              <span>Collected</span>
              <span>Udhaar at sale</span>
              <span />
            </div>
            {sales.map((sale) => (
              <button
                className="sale-row"
                key={sale.id}
                disabled={busyId !== null}
                onClick={() => openReceipt(sale.id)}
              >
                <div className="sale-identity">
                  <span className="activity-icon">
                    <ReceiptText size={20} />
                  </span>
                  <div>
                    <strong>{sale.number}</strong>
                    <small>{sale.customer_name || 'Walk-in customer'}</small>
                  </div>
                </div>
                <div className="sale-date">{dateText(sale.created_at)}</div>
                <div className="sale-total">
                  <small className="mobile-only">Total</small>
                  <strong>{money(sale.total)}</strong>
                </div>
                <div className="sale-paid">
                  <small className="mobile-only">Collected</small>
                  <span>{money(sale.paid_amount)}</span>
                  <small>{sale.payment_method === 'upi' ? 'UPI' : 'Cash'}</small>
                </div>
                <div className="sale-due">
                  <small className="mobile-only">Udhaar at sale</small>
                  <strong
                    className={
                      (paise(sale.due_amount) || 0n) > 0n ? 'due-text' : 'green-text'
                    }
                  >
                    {money(sale.due_amount)}
                  </strong>
                </div>
                <span className="sale-open">
                  {busyId === sale.id ? '…' : <ArrowUpRight size={20} />}
                </span>
              </button>
            ))}
          </div>
        ) : (
          !data.error && (
            <Empty
              title={
                search
                  ? 'No matching bills'
                  : filter === 'due'
                    ? 'No credit sales found'
                    : 'Your first sale is waiting'
              }
              text={
                search
                  ? 'Try another bill number or customer name.'
                  : filter === 'due'
                    ? 'Sales with an amount due at billing will appear here.'
                    : 'Saved sales will appear here, ready to print or share.'
              }
            />
          )
        )}
      </section>
      {filter === 'due' && (
        <p className="page-note">
          This shows udhaar when each bill was saved. Current balances and repayments are
          in Customers & udhaar.
        </p>
      )}
    </>
  );
}
