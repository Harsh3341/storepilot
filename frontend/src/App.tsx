import { useEffect, useRef, useState } from 'react';
import {
  ShoppingBasket,
  Package,
  UsersRound,
  ClipboardList,
  ReceiptText,
  Store,
  ArrowUpRight,
  RefreshCw,
  LogOut,
} from 'lucide-react';
import { useData } from './api';
import { money } from './format';
import type { Order, Page, Sale, Summary } from './types';
import { Sell } from './Sell';
import { Stock } from './Stock';
import { Customers } from './Customers';
import { Orders } from './Orders';
import { History } from './History';
import { Receipt } from './Receipt';
import { Button, ErrorNotice } from './components';

const pages = [
  { id: 'sell', label: 'Sell', icon: ShoppingBasket },
  { id: 'stock', label: 'Stock', icon: Package },
  { id: 'customers', label: 'Udhaar', icon: UsersRound },
  { id: 'orders', label: 'Orders', icon: ClipboardList },
  { id: 'history', label: 'Sales', icon: ReceiptText },
] as const;
type AppProps = {
  ownerName?: string | null;
  sessionVersion?: number;
  onLogout?: () => void;
};

export default function App({
  ownerName = null,
  sessionVersion = 0,
  onLogout,
}: AppProps = {}) {
  const [page, setPage] = useState<Page>('sell');
  const [checkoutBusy, setCheckoutBusy] = useState(false);
  const [version, setVersion] = useState(0);
  const [order, setOrder] = useState<Order | null>(null);
  const [receipt, setReceipt] = useState<Sale | null>(null);
  const previousSession = useRef(sessionVersion);
  useEffect(() => {
    if (previousSession.current !== sessionVersion) {
      previousSession.current = sessionVersion;
      setVersion((version) => version + 1);
    }
  }, [sessionVersion]);
  const summary = useData<Summary>('/api/summary', version);
  const refresh = () => setVersion((v) => v + 1);
  const openOrder = (value: Order) => {
    setOrder(value);
    setPage('sell');
  };
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="StorePilot home">
          <span className="brand-mark">
            <Store size={25} />
          </span>
          <span>
            StorePilot<small>MY SHOP</small>
          </span>
        </a>
        <nav className="desktop-nav" aria-label="Main navigation">
          {pages.map(({ id, label, icon: Icon }) => (
            <button
              disabled={checkoutBusy}
              key={id}
              onClick={() => setPage(id)}
              className={page === id ? 'selected' : ''}
            >
              <Icon size={21} />
              {id === 'customers'
                ? 'Customers & udhaar'
                : id === 'history'
                  ? 'Sales history'
                  : label}
              {id === 'orders' && !!summary.data?.pending_orders_count && (
                <span className="nav-count">{summary.data.pending_orders_count}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="status-dot" /> Your everyday shop companion
          <small>Prices in Indian rupees</small>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="mobile-brand">
            <Store size={22} />
            <strong>StorePilot</strong>
          </div>
          <div className="topbar-title">
            My shop<span className="separator">/</span>
            <strong>
              {pages.find((p) => p.id === page)?.label === 'Udhaar'
                ? 'Customers & udhaar'
                : pages.find((p) => p.id === page)?.label}
            </strong>
          </div>
          <div className="topbar-right">
            <span className="header-date">
              {new Date().toLocaleDateString('en-IN', {
                weekday: 'short',
                day: 'numeric',
                month: 'short',
              })}
            </span>
            <button
              disabled={checkoutBusy}
              className="icon-button"
              aria-label="Refresh shop data"
              onClick={refresh}
            >
              <RefreshCw size={18} />
            </button>
            {onLogout && (
              <>
                {ownerName && <span className="owner-name">{ownerName}</span>}
                <Button
                  className="logout-button"
                  variant="secondary"
                  disabled={checkoutBusy}
                  onClick={onLogout}
                >
                  <LogOut size={17} />
                  Sign out
                </Button>
              </>
            )}
          </div>
        </header>
        <main>
          <ErrorNotice message={summary.error} retry={summary.reload} />
          {
            <section hidden={page !== 'sell'}>
              <div className="page-heading">
                <div>
                  <h1>Let’s make a sale</h1>
                  <p>Add items, collect payment, and you’re done.</p>
                </div>
                {summary.data && (
                  <div className="today-summary">
                    <span>Today’s sales</span>
                    <strong>{money(summary.data.today.sales_total)}</strong>
                    <small>{summary.data.today.sales_count} bills</small>
                  </div>
                )}
              </div>
              <Sell
                onBusyChange={setCheckoutBusy}
                version={version}
                onChange={refresh}
                linkedOrder={order}
                onOrderCleared={() => setOrder(null)}
                onReceipt={setReceipt}
                onStock={() => setPage('stock')}
              />
            </section>
          }
          {page === 'stock' && <Stock version={version} onChange={refresh} />}{' '}
          {page === 'customers' && (
            <Customers version={version} onChange={refresh} onReceipt={setReceipt} />
          )}{' '}
          {page === 'orders' && (
            <Orders
              version={version}
              onChange={refresh}
              onOpen={openOrder}
              onReceipt={setReceipt}
            />
          )}{' '}
          {page === 'history' && <History version={version} onReceipt={setReceipt} />}
        </main>
        <footer className="desktop-footer">
          <span>StorePilot · Made for the everyday shop</span>
          <button disabled={checkoutBusy} onClick={() => setPage('stock')}>
            Manage your catalogue <ArrowUpRight size={14} />
          </button>
        </footer>
      </div>
      <nav className="bottom-nav" aria-label="Main navigation">
        {pages.map(({ id, label, icon: Icon }) => (
          <button
            disabled={checkoutBusy}
            key={id}
            onClick={() => setPage(id)}
            className={page === id ? 'selected' : ''}
          >
            <Icon size={22} />
            <span>{label}</span>
          </button>
        ))}
      </nav>
      {receipt && <Receipt sale={receipt} onClose={() => setReceipt(null)} />}
    </div>
  );
}
