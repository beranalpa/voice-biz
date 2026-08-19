import { ArrowDownRight, ArrowUpRight, Receipt, Wallet } from "lucide-react";
import { rupiah } from "../lib/api";

export const StatCards = ({ data }) => {
  if (!data) return null;
  const delta =
    data.revenue_yesterday > 0
      ? Math.round(((data.revenue_today - data.revenue_yesterday) / data.revenue_yesterday) * 100)
      : null;
  const up = (delta ?? 0) >= 0;

  return (
    <div className="grid grid-cols-2 gap-3">
      <div
        data-testid="stat-revenue"
        className="col-span-2 rounded-2xl bg-forest p-5 text-sand shadow-floating vb-rise"
      >
        <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-sand/60">
          Pendapatan hari ini
        </p>
        <p className="mt-2 font-display text-4xl font-extrabold tracking-tight" data-testid="revenue-value">
          {rupiah(data.revenue_today)}
        </p>
        <div className="mt-3 flex items-center gap-2 text-xs text-sand/75">
          {delta !== null && (
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2 py-1 font-semibold ${
                up ? "bg-white/15 text-white" : "bg-terracotta/25 text-white"
              }`}
            >
              {up ? <ArrowUpRight className="h-3.5 w-3.5" /> : <ArrowDownRight className="h-3.5 w-3.5" />}
              {Math.abs(delta)}% vs kemarin
            </span>
          )}
          <span>{data.transactions_today} transaksi</span>
        </div>
      </div>

      <div data-testid="stat-expense" className="rounded-2xl border border-hairline bg-white p-4 shadow-card vb-rise">
        <div className="flex items-center gap-2 text-mutedink">
          <Receipt className="h-4 w-4" strokeWidth={2.4} />
          <span className="text-[10px] font-bold uppercase tracking-[0.14em]">Pengeluaran</span>
        </div>
        <p className="mt-2 font-display text-xl font-extrabold tracking-tight text-ink">
          {rupiah(data.expense_today)}
        </p>
      </div>

      <div data-testid="stat-profit" className="rounded-2xl border border-hairline bg-white p-4 shadow-card vb-rise">
        <div className="flex items-center gap-2 text-mutedink">
          <Wallet className="h-4 w-4" strokeWidth={2.4} />
          <span className="text-[10px] font-bold uppercase tracking-[0.14em]">Laba</span>
        </div>
        <p
          className={`mt-2 font-display text-xl font-extrabold tracking-tight ${
            data.profit_today < 0 ? "text-terracotta" : "text-forest"
          }`}
        >
          {rupiah(data.profit_today)}
        </p>
      </div>
    </div>
  );
};
