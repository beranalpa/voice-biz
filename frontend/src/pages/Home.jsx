import { useEffect, useState } from "react";
import { RefreshCw, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { StatCards } from "../components/StatCards";
import { TargetCard } from "../components/TargetCard";
import { HistoryFeed } from "../components/HistoryFeed";
import { TrendChart } from "../components/TrendChart";
import { InsightList } from "../components/InsightList";
import { TalkPanel } from "../components/TalkPanel";
import { getBrief, getDashboard } from "../lib/api";

const fmtTime = (iso) =>
  new Date(iso).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
// eslint-disable-next-line no-unused-vars
const _unused = fmtTime;

export default function Home({ refreshKey, onDraft, onChanged }) {
  const [data, setData] = useState(null);
  const [brief, setBrief] = useState(null);
  const [loadingBrief, setLoadingBrief] = useState(false);

  useEffect(() => {
    getDashboard().then(setData).catch(() => {});
  }, [refreshKey]);

  const loadBrief = async () => {
    setLoadingBrief(true);
    try {
      const r = await getBrief();
      setBrief(typeof r?.brief === "string" ? r.brief : "");
    } catch (e) {
      toast.error("Gagal membuat briefing. Coba lagi.");
    } finally {
      setLoadingBrief(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="home-page">
      <TalkPanel onDraft={onDraft} />

      <StatCards data={data} />

      <TargetCard data={data} onChanged={onChanged} />

      <section className="rounded-2xl border border-forest/15 bg-forest-light p-5" data-testid="brief-card">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-forest" strokeWidth={2.4} />
            <h3 className="font-display text-base font-bold text-forest">Briefing AI</h3>
          </div>
          <button
            data-testid="brief-refresh-btn"
            onClick={loadBrief}
            disabled={loadingBrief}
            className="flex items-center gap-1.5 rounded-full bg-white px-3 py-1.5 text-xs font-bold text-forest shadow-card transition-transform active:scale-95"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loadingBrief ? "animate-spin" : ""}`} strokeWidth={2.6} />
            {brief ? "Perbarui" : "Buat"}
          </button>
        </div>
        <p className="mt-3 text-sm leading-relaxed text-forest/90" data-testid="brief-text">
          {loadingBrief ? "Menyusun briefing hari ini…" : brief || "Tekan Buat untuk mendapatkan briefing harian dari VoiceBiz."}
        </p>
      </section>

      {data && <InsightList insights={data.insights} />}
      {data && <TrendChart trend={data.trend} />}

      <HistoryFeed refreshKey={refreshKey} onChanged={onChanged} />
    </div>
  );
}
