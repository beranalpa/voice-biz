import { useState } from "react";
import { Home as HomeIcon, Brain, RotateCcw } from "lucide-react";
import { Toaster, toast } from "sonner";
import Home from "./pages/Home";
import Memory from "./pages/Memory";
import { ConfirmSheet } from "./components/ConfirmSheet";
import { commitDraft, resetDemo } from "./lib/api";

export default function App() {
  const [tab, setTab] = useState("home");
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const handleSave = async (form) => {
    setSaving(true);
    try {
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
              data-testid="reset-demo-btn"
              onClick={handleReset}
              className="rounded-full border border-hairline bg-white p-2.5 text-mutedink transition-colors hover:text-forest"
              title="Muat ulang data demo"
            >
              <RotateCcw className="h-4 w-4" strokeWidth={2.4} />
            </button>
            <img
              src="https://images.unsplash.com/photo-1655462502318-a5ff79542ce7?w=96&h=96&fit=crop"
              alt="Profil pemilik"
              className="h-10 w-10 rounded-full border-2 border-white object-cover shadow-card"
            />
          </div>
        </header>

        <main className="flex-1 px-6 pb-28 pt-5">
          {tab === "home" ? (
            <Home refreshKey={refreshKey} onDraft={setDraft} />
          ) : (
            <Memory refreshKey={refreshKey} />
          )}
        </main>

        <nav className="fixed bottom-0 z-40 w-full max-w-md border-t border-hairline bg-white/90 px-6 py-3 backdrop-blur-xl">
          <div className="flex items-center justify-around">
            {[
              { key: "home", label: "Beranda", icon: HomeIcon },
              { key: "memory", label: "Memori", icon: Brain },
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
      </div>
    </div>
  );
}
