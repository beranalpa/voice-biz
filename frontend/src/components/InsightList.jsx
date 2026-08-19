import { HandCoins, PackageX, Sparkles, TrendingDown, TrendingUp, UserRoundX } from "lucide-react";

const ICONS = {
  "trending-down": TrendingDown,
  "trending-up": TrendingUp,
  "hand-coins": HandCoins,
  "package-x": PackageX,
  "user-round-x": UserRoundX,
};

const TONE = {
  warning: "border-ochre/30 bg-[#FDF6EA] text-[#8A6520]",
  danger: "border-terracotta/25 bg-terracotta-light text-[#A63A2A]",
  good: "border-forest/15 bg-forest-light text-forest",
  info: "border-hairline bg-white text-ink",
};

export const InsightList = ({ insights = [] }) => (
  <section className="space-y-3" data-testid="insight-list">
    <div className="flex items-center gap-2">
      <Sparkles className="h-4 w-4 text-forest" strokeWidth={2.4} />
      <h3 className="font-display text-base font-bold text-ink">Rekomendasi AI</h3>
    </div>
    {insights.length === 0 && (
      <p className="rounded-2xl border border-hairline bg-white p-4 text-sm text-mutedink">
        Semua terlihat sehat hari ini. Lanjutkan ritmenya.
      </p>
    )}
    {insights.map((ins, i) => {
      const Icon = ICONS[ins.icon] || Sparkles;
      return (
        <article
          key={i}
          data-testid={`insight-card-${i}`}
          className={`vb-rise rounded-2xl border p-4 ${TONE[ins.type] || TONE.info}`}
          style={{ animationDelay: `${i * 70}ms` }}
        >
          <div className="flex gap-3">
            <Icon className="mt-0.5 h-5 w-5 shrink-0" strokeWidth={2.4} />
            <div className="min-w-0">
              <p className="font-display text-sm font-bold leading-snug">{ins.title}</p>
              <p className="mt-1 text-xs opacity-80">{ins.body}</p>
              <p className="mt-3 rounded-xl bg-white/70 px-3 py-2 text-xs font-semibold">
                Lakukan: {ins.action}
              </p>
            </div>
          </div>
        </article>
      );
    })}
  </section>
);
