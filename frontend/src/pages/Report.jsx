import { useEffect, useState } from "react";
import { CalendarRange, Copy, Loader2, Share2, TrendingUp } from "lucide-react";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { getWeekly, rupiah } from "../lib/api";

export default function Report({ refreshKey }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState("weekly");

  const load = () => {
    setLoading(true);
    getWeekly(period)
      .then(setData)
      .catch(() => toast.error("Gagal memuat laporan"))
      .finally(() => setLoading(false));
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [refreshKey, period]);

  const copy = async () => {
    await navigator.clipboard.writeText(data.share_text);
    toast.success("Ringkasan disalin, siap ditempel di WhatsApp");
  };

  return (
    <div className="space-y-5" data-testid="report-page">
      <div>
        <h2 className="font-display text-2xl font-extrabold tracking-tight text-ink">
          {period === "monthly" ? "Laporan Bulanan" : "Laporan Mingguan"}
        </h2>
        <p className="mt-1 text-sm text-mutedink">
          Ringkasan siap dibagikan ke keluarga atau pemberi modal.
        </p>
      </div>

      <div className="flex gap-2 rounded-full border border-hairline bg-white p-1" data-testid="period-switch">
        {[
          { key: "weekly", label: "7 hari" },
          { key: "monthly", label: "30 hari" },
        ].map((p) => (
          <button
            key={p.key}
            data-testid={`period-${p.key}-btn`}
            onClick={() => setPeriod(p.key)}
            className={`h-11 flex-1 rounded-full text-sm font-bold transition-colors ${
              period === p.key ? "bg-forest text-sand" : "text-mutedink hover:text-forest"
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>

      {loading && (
        <p className="flex items-center gap-2 text-sm text-mutedink">
          <Loader2 className="h-4 w-4 animate-spin" /> Menyusun laporan…
        </p>
      )}

      {data && !loading && (
        <>
          <div className="rounded-2xl bg-forest p-5 text-sand shadow-floating" data-testid="report-summary">
            <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.16em] text-sand/60">
              <CalendarRange className="h-3.5 w-3.5" strokeWidth={2.6} />
              {data.period}
            </div>
            <p className="mt-2 font-display text-3xl font-extrabold tracking-tight" data-testid="report-revenue">
              {rupiah(data.revenue)}
            </p>
            <p className="text-xs text-sand/70">
              Total pemasukan {period === "monthly" ? "30 hari terakhir" : "minggu ini"}
            </p>
            <div className="mt-4 grid grid-cols-3 gap-3 border-t border-white/15 pt-4 text-xs">
              <div>
                <p className="text-sand/60">Pengeluaran</p>
                <p className="mt-1 font-display text-sm font-bold">{rupiah(data.expense)}</p>
              </div>
              <div>
                <p className="text-sand/60">Laba</p>
                <p className="mt-1 font-display text-sm font-bold">{rupiah(data.profit)}</p>
              </div>
              <div>
                <p className="text-sand/60">Rata-rata/hari</p>
                <p className="mt-1 font-display text-sm font-bold">{rupiah(data.avg_per_day)}</p>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-forest/15 bg-forest-light p-5" data-testid="report-narrative">
            <p className="text-sm leading-relaxed text-forest">{data.narrative}</p>
          </div>

          <section className="space-y-3">
            <h3 className="font-display text-base font-bold text-ink">Menu terlaris</h3>
            {data.top_items.length === 0 && <p className="text-sm text-mutedink">Belum ada penjualan pada periode ini.</p>}
            {data.top_items.map((t, i) => (
              <div
                key={t.name}
                data-testid={`report-top-item-${i}`}
                className="flex items-center justify-between rounded-2xl border border-hairline bg-white p-4 shadow-card"
              >
                <div className="flex items-center gap-3">
                  <span className="flex h-8 w-8 items-center justify-center rounded-full bg-forest-light font-display text-sm font-extrabold text-forest">
                    {i + 1}
                  </span>
                  <div>
                    <p className="font-display text-sm font-bold text-ink">{t.name}</p>
                    <p className="text-xs text-mutedink">{Math.round(t.qty)} porsi terjual</p>
                  </div>
                </div>
                <p className="font-display text-sm font-extrabold text-forest">{rupiah(t.revenue)}</p>
              </div>
            ))}
          </section>

          <section className="space-y-3" data-testid="expense-breakdown">
            <h3 className="font-display text-base font-bold text-ink">Ke mana uang pergi</h3>
            {(data.expense_breakdown || []).length === 0 && (
              <p className="text-sm text-mutedink">Belum ada pengeluaran pada periode ini.</p>
            )}
            {(data.expense_breakdown || []).map((c, i) => (
              <div
                key={c.category}
                data-testid={`expense-cat-${i}`}
                className="rounded-2xl border border-hairline bg-white p-4 shadow-card"
              >
                <div className="flex items-baseline justify-between">
                  <p className="font-display text-sm font-bold capitalize text-ink">{c.category}</p>
                  <p className="font-display text-sm font-extrabold text-terracotta">{rupiah(c.total)}</p>
                </div>
                <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-terracotta transition-[width] duration-700"
                    style={{ width: `${Math.max(3, c.pct)}%` }}
                  />
                </div>
                <p className="mt-1.5 text-xs text-mutedink">{c.pct}% dari total pengeluaran</p>
              </div>
            ))}
            {(data.top_expenses || []).length > 0 && (
              <div className="rounded-2xl border border-hairline bg-white p-4 shadow-card">
                <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-mutedink">
                  Pengeluaran terbesar
                </p>
                <div className="mt-2 space-y-2">
                  {data.top_expenses.map((e, i) => (
                    <div key={i} className="flex items-center justify-between text-sm" data-testid={`top-expense-${i}`}>
                      <span className="text-ink">{e.title}</span>
                      <span className="font-display font-bold text-terracotta">{rupiah(e.total)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>

          {data.best_day && (            <div className="flex items-center gap-3 rounded-2xl border border-hairline bg-white p-4 shadow-card">
              <TrendingUp className="h-5 w-5 text-forest" strokeWidth={2.4} />
              <p className="text-sm text-ink">
                Hari terbaik{" "}
                <span className="font-bold">
                  {new Date(data.best_day.date).toLocaleDateString("id-ID", { weekday: "long", day: "numeric", month: "short" })}
                </span>{" "}
                — {rupiah(data.best_day.revenue)}
              </p>
            </div>
          )}

          <div className="flex gap-3">
            <Button
              data-testid="report-share-btn"
              onClick={() => window.open(data.share_link, "_blank")}
              className="h-14 flex-1 rounded-full bg-forest text-base font-bold hover:bg-forest-hover"
            >
              <Share2 className="mr-2 h-5 w-5" strokeWidth={2.5} />
              Bagikan
            </Button>
            <Button
              data-testid="report-copy-btn"
              variant="outline"
              onClick={copy}
              className="h-14 rounded-full border-forest/25 px-6 font-bold text-forest hover:bg-forest-light"
            >
              <Copy className="mr-2 h-4 w-4" strokeWidth={2.5} />
              Salin
            </Button>
          </div>

          <pre
            data-testid="report-share-text"
            className="whitespace-pre-wrap rounded-2xl border border-hairline bg-white p-4 font-sans text-xs leading-relaxed text-mutedink"
          >
            {data.share_text}
          </pre>
        </>
      )}
    </div>
  );
}
