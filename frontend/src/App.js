import { useState } from "react";
import { Home as HomeIcon, Brain, FileBarChart, RotateCcw, Sparkles } from "lucide-react";
import { Toaster, toast } from "sonner";
import Home from "./pages/Home";
import Memory from "./pages/Memory";
import Report from "./pages/Report";
import { ConfirmSheet } from "./components/ConfirmSheet";
import { DemoTour } from "./components/DemoTour";
import { commitDraft, correctLast, resetDemo } from "./lib/api";

export default function App() {
  const [tab, setTab] = useState("home");
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [tourOpen, setTourOpen] = useState(false);

  const bump = () => setRefreshKey((k) => k + 1);

  const handleSave = async (form) => {
    setSaving(true);
    try {
      if (form.intent === "correction") {
        const res = await correctLast({
          total: Number(form.total || 0) || null,
          customer_name: form.customer_name || null,
          item_name: form.items?.[0]?.name || null,
          raw_text: form.raw_text || null,
        });
        toast.success(res.message);
        setDraft(null);
        bump();
        return;
      }
      const res = await commitDraft({
        intent: form.intent,
        title: form.title,
        summary: form.summary,
        items: (form.items || []).map((i) => ({
          name: i.name,
          qty: Number(i.qty || 1),
          unit_price: i.unit_price ?? null,
          subtotal: i.subtotal ?? null,
        })),
        total: Number(form.total || 0),
        customer_name: form.customer_name || null,
        category: form.category || null,
        note: form.note || form.raw_text || null,
        raw_text: form.raw_text || null,
      });
      toast.success(res.message || "Tersimpan");
      setDraft(null);
      setRefreshKey((k) => k + 1);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    await resetDemo();
    setRefreshKey((k) => k + 1);
    toast.success("Data demo dimuat ulang");
  };

  return (
    <div className="min-h-screen w-full overflow-x-hidden bg-[#F2EFE9]">
      <Toaster position="top-center" richColors />
      <div className="relative mx-auto flex min-h-screen w-full max-w-md flex-col bg-sand shadow-2xl">
        <header className="sticky top-0 z-40 flex items-center justify-between border-b border-hairline bg-sand/85 px-6 py-4 backdrop-blur-xl">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-mutedink">
              {new Date().toLocaleDateString("id-ID", { weekday: "long", day: "numeric", month: "long" })}
            </p>
            <h1 className="font-display text-xl font-extrabold tracking-tight text-ink">
              VoiceBiz<span className="text-terracotta">.</span>
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <button
              data-testid="demo-tour-btn"
              onClick={() => {
                setTab("home");
                setTourOpen(true);
              }}
              className="flex items-center gap-1.5 rounded-full bg-forest px-3.5 py-2.5 text-[11px] font-bold text-sand shadow-card transition-transform active:scale-95"
            >
              <Sparkles className="h-3.5 w-3.5" strokeWidth={2.6} />
              Demo
            </button>
            <button
              data-testid="reset-demo-btn"
              onClick={handleReset}
              className="rounded-full border border-hairline bg-white p-2.5 text-mutedink transition-colors hover:text-forest"
              title="Muat ulang data demo"
            >
              <RotateCcw className="h-4 w-4" strokeWidth={2.4} />
            </button>
          </div>
        </header>

        <main className="flex-1 px-6 pb-28 pt-5">
          {tab === "home" && <Home refreshKey={refreshKey} onDraft={setDraft} onChanged={bump} />}
          {tab === "memory" && <Memory refreshKey={refreshKey} />}
          {tab === "report" && <Report refreshKey={refreshKey} />}
        </main>

        <nav className="fixed bottom-0 z-40 w-full max-w-md border-t border-hairline bg-white/90 px-6 py-3 backdrop-blur-xl">
          <div className="flex items-center justify-around">
            {[
              { key: "home", label: "Beranda", icon: HomeIcon },
              { key: "memory", label: "Memori", icon: Brain },
              { key: "report", label: "Laporan", icon: FileBarChart },
            ].map((t) => (
              <button
                key={t.key}
                data-testid={`nav-${t.key}`}
                onClick={() => setTab(t.key)}
                className={`flex min-h-[48px] flex-1 flex-col items-center gap-1 rounded-2xl py-1.5 text-[11px] font-bold transition-colors ${
                  tab === t.key ? "text-forest" : "text-mutedink"
                }`}
              >
                <t.icon className="h-5 w-5" strokeWidth={2.5} />
                {t.label}
              </button>
            ))}
          </div>
        </nav>

        {draft && (
          <ConfirmSheet
            draft={draft}
            saving={saving}
            onSave={handleSave}
            onCancel={() => setDraft(null)}
          />
        )}

        {tourOpen && <DemoTour onClose={() => setTourOpen(false)} onChanged={bump} onNavigate={setTab} />}
      </div>
    </div>
  );
}
