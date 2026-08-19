import { rupiah } from "../lib/api";

export const TrendChart = ({ trend = [] }) => {
  const max = Math.max(1, ...trend.map((t) => t.revenue));
  return (
    <section data-testid="trend-chart" className="rounded-2xl border border-hairline bg-white p-5 shadow-card">
      <div className="flex items-baseline justify-between">
        <h3 className="font-display text-base font-bold text-ink">7 hari terakhir</h3>
        <span className="text-xs text-mutedink">Puncak {rupiah(max)}</span>
      </div>
      <div className="mt-5 flex h-28 items-end gap-2">
        {trend.map((t, i) => (
          <div key={t.date} className="flex flex-1 flex-col items-center gap-2">
            <div
              className="w-full rounded-t-md bg-forest/85 transition-[height] duration-500"
              style={{ height: `${Math.max(6, (t.revenue / max) * 100)}%`, opacity: 0.45 + (i / trend.length) * 0.55 }}
              title={rupiah(t.revenue)}
            />
            <span className="text-[10px] font-medium text-mutedink">{t.label}</span>
          </div>
        ))}
      </div>
    </section>
  );
};
