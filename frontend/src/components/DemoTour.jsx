import { useEffect, useRef, useState } from "react";
import { Check, FileBarChart, Loader2, MessageCircle, Mic, Pause, Play, Sparkles, Undo2, X } from "lucide-react";
import { Button } from "./ui/button";
import {
  commitDraft,
  correctLast,
  getReminders,
  getWeekly,
  parseText,
  resetDemo,
  rupiah,
  undoHistory,
  INTENT_LABELS,
} from "../lib/api";

const STEPS = [
  {
    kind: "say",
    text: "Hari ini saya jual dua nasi goreng dan tiga es teh, total 87 ribu",
    caption: "Satu ucapan jadi transaksi penjualan lengkap — tanpa isi form.",
  },
  {
    kind: "say",
    text: "Salah, tadi itu 97 ribu",
    caption: "Cukup bilang “salah” — catatan terakhir langsung diperbaiki, bukan dobel.",
    correct: true,
  },
  {
    kind: "say",
    text: "Pak Budi masih punya utang 150 ribu dari minggu lalu",
    caption: "VoiceBiz mengenali piutang dan langsung mengingat nama pelanggan.",
  },
  {
    kind: "say",
    text: "Beli ayam 3 kilo 105 ribu",
    caption: "Pengeluaran bahan baku tercatat, laba hari ini ikut menyesuaikan.",
  },
  {
    kind: "say",
    text: "Jual sepuluh es teh 50 ribu",
    caption: "Salah tangkap? Setiap catatan bisa dibatalkan dalam satu tap.",
    undo: true,
  },
  {
    kind: "reminder",
    text: "Tagihkan utang pelanggan saya lewat WhatsApp",
    caption: "AI menulis pesan penagihan yang sopan — hubungan tetap terjaga.",
  },
  {
    kind: "weekly",
    text: "Buatkan laporan mingguan untuk pemberi modal saya",
    caption: "Ringkasan siap kirim: pemasukan, laba, menu terlaris, saran minggu depan.",
  },
  {
    kind: "say",
    text: "Berapa untung saya hari ini?",
    caption: "Jawaban dihitung dari data nyata yang baru saja dicatat.",
  },
];

export const DemoTour = ({ onClose, onChanged, onNavigate }) => {
  const [index, setIndex] = useState(0);
  const [typed, setTyped] = useState("");
  const [phase, setPhase] = useState("typing");
  const [draft, setDraft] = useState(null);
  const [extra, setExtra] = useState(null);
  const [saved, setSaved] = useState(null);
  const [done, setDone] = useState(false);
  const [auto, setAuto] = useState(true);
  const tokenRef = useRef(0);
  const autoRef = useRef(true);

  useEffect(() => {
    autoRef.current = auto;
  }, [auto]);

  useEffect(() => {
    resetDemo().then(onChanged).catch(() => {});
    return () => {
      tokenRef.current += 1;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (done) return;
    const token = ++tokenRef.current;
    const alive = () => token === tokenRef.current;
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    const step = STEPS[index];

    (async () => {
      setDraft(null);
      setExtra(null);
      setSaved(null);
      setTyped("");
      setPhase("typing");
      for (let i = 1; i <= step.text.length; i += 2) {
        if (!alive()) return;
        setTyped(step.text.slice(0, i));
        await sleep(20);
      }
      if (!alive()) return;
      setTyped(step.text);
      setPhase("thinking");

      if (step.kind === "reminder") {
        try {
          const r = await getReminders();
          if (!alive()) return;
          setExtra({ kind: "reminder", reminders: r.reminders.slice(0, 2) });
          setPhase("saved");
        } catch {
          if (alive()) setPhase("error");
          return;
        }
      } else if (step.kind === "weekly") {
        try {
          const r = await getWeekly();
          if (!alive()) return;
          setExtra({ kind: "weekly", report: r });
          setPhase("saved");
        } catch {
          if (alive()) setPhase("error");
          return;
        }
      } else {
        let d;
        try {
          d = await parseText(step.text);
        } catch {
          if (alive()) setPhase("error");
          return;
        }
        if (!alive()) return;
        setDraft(d);
        setPhase("result");
        await sleep(1500);
        if (!alive()) return;

        if (d.intent !== "question" && d.intent !== "unknown") {
          setPhase("saving");
          let historyId = null;
          try {
            const res = step.correct || d.intent === "correction"
              ? await correctLast({
                  total: Number(d.total || 0) || null,
                  customer_name: d.customer_name || null,
                  item_name: d.items?.[0]?.name || null,
                  raw_text: step.text,
                })
              : await commitDraft({
              intent: d.intent,
              title: d.title,
              items: (d.items || []).map((it) => ({
                name: it.name,
                qty: Number(it.qty || 1),
                unit_price: it.unit_price ?? null,
                subtotal: it.subtotal ?? null,
              })),
              total: Number(d.total || 0),
              customer_name: d.customer_name || null,
              category: d.category || null,
              note: d.note || step.text,
              raw_text: step.text,
            });
            if (!alive()) return;
            historyId = res.history_id;
            setSaved(res.message);
            onChanged();
          } catch {
            if (!alive()) return;
            setSaved("Tidak bisa disimpan — lanjut ke contoh berikutnya.");
          }

          if (step.undo && historyId) {
            await sleep(1800);
            if (!alive()) return;
            setPhase("undoing");
            try {
              const res = await undoHistory(historyId);
              if (!alive()) return;
              setSaved(res.message + " — angka di dashboard kembali seperti semula.");
              onChanged();
            } catch {
              /* ignore */
            }
          }
        }
        setPhase("saved");
      }

      await sleep(step.kind === "say" ? 2200 : 3600);
      if (!alive()) return;
      if (autoRef.current) advance();
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index, done]);

  const advance = () => {
    if (index + 1 >= STEPS.length) {
      tokenRef.current += 1;
      setDone(true);
    } else {
      setIndex((i) => i + 1);
    }
  };

  const goto = (tab) => {
    onNavigate?.(tab);
    onClose();
  };

  const step = STEPS[index];

  return (
    <div className="fixed inset-0 z-[70] flex items-end justify-center" data-testid="demo-tour">
      <div className="absolute inset-0 bg-ink/45 backdrop-blur-[2px]" />
      <div className="vb-rise relative z-10 max-h-[90vh] w-full max-w-md overflow-y-auto rounded-t-3xl border-t border-hairline bg-white p-6 pb-8 shadow-[0_-8px_30px_rgba(0,0,0,0.16)] no-scrollbar">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-forest-light text-forest">
              <Sparkles className="h-4 w-4" strokeWidth={2.5} />
            </span>
            <div>
              <p className="font-display text-sm font-extrabold text-ink">Mode Demo Juri</p>
              <p className="text-[11px] text-mutedink">
                {done ? "Selesai" : `Babak ${index + 1} dari ${STEPS.length}`}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            {!done && (
              <button
                data-testid="demo-toggle-auto-btn"
                onClick={() => setAuto((a) => !a)}
                className="rounded-full border border-hairline p-2 text-mutedink transition-colors hover:text-forest"
                title={auto ? "Jeda otomatis" : "Lanjut otomatis"}
              >
                {auto ? <Pause className="h-4 w-4" strokeWidth={2.4} /> : <Play className="h-4 w-4" strokeWidth={2.4} />}
              </button>
            )}
            <button
              data-testid="demo-close-btn"
              onClick={onClose}
              className="rounded-full border border-hairline p-2 text-mutedink transition-colors hover:text-terracotta"
            >
              <X className="h-4 w-4" strokeWidth={2.4} />
            </button>
          </div>
        </div>

        <div className="mt-4 flex gap-1.5">
          {STEPS.map((_, i) => (
            <span
              key={i}
              className={`h-1.5 flex-1 rounded-full transition-colors ${
                done || i < index ? "bg-forest" : i === index ? "bg-ochre" : "bg-hairline"
              }`}
            />
          ))}
        </div>

        {done ? (
          <div className="mt-6" data-testid="demo-done">
            <h3 className="font-display text-2xl font-extrabold tracking-tight text-ink">
              7 babak, nol formulir.
            </h3>
            <p className="mt-2 text-sm leading-relaxed text-mutedink">
              Penjualan tercatat, piutang dibuat, pengeluaran masuk, catatan salah dibatalkan, pesan penagihan
              WhatsApp dibuat AI, laporan mingguan siap kirim, dan laba dihitung dari data nyata.
            </p>
            <div className="mt-5 grid grid-cols-2 gap-3">
              <Button
                data-testid="demo-goto-memory-btn"
                variant="outline"
                onClick={() => goto("memory")}
                className="h-12 rounded-full border-forest/25 font-bold text-forest hover:bg-forest-light"
              >
                <MessageCircle className="mr-2 h-4 w-4" strokeWidth={2.5} />
                Tagih utang
              </Button>
              <Button
                data-testid="demo-goto-report-btn"
                variant="outline"
                onClick={() => goto("report")}
                className="h-12 rounded-full border-forest/25 font-bold text-forest hover:bg-forest-light"
              >
                <FileBarChart className="mr-2 h-4 w-4" strokeWidth={2.5} />
                Laporan
              </Button>
            </div>
            <div className="mt-3 flex gap-3">
              <Button
                data-testid="demo-restart-btn"
                variant="outline"
                onClick={() => {
                  setDone(false);
                  setIndex(0);
                  setAuto(true);
                }}
                className="h-12 flex-1 rounded-full border-hairline font-bold text-mutedink"
              >
                Ulangi demo
              </Button>
              <Button
                data-testid="demo-finish-btn"
                onClick={onClose}
                className="h-12 flex-1 rounded-full bg-forest font-bold hover:bg-forest-hover"
              >
                Coba sendiri
              </Button>
            </div>
          </div>
        ) : (
          <div className="mt-5">
            <div className="flex items-start gap-3 rounded-2xl bg-forest p-4 text-sand">
              <Mic className="mt-0.5 h-4 w-4 shrink-0" strokeWidth={2.6} />
              <p className="text-sm leading-relaxed" data-testid="demo-utterance">
                “{typed}
                {phase === "typing" && <span className="ml-0.5 animate-pulse">▍</span>}”
              </p>
            </div>

            <div className="mt-4 min-h-[120px]">
              {phase === "thinking" && (
                <p className="flex items-center gap-2 text-sm text-mutedink" data-testid="demo-thinking">
                  <Loader2 className="h-4 w-4 animate-spin" /> VoiceBiz sedang bekerja…
                </p>
              )}
              {phase === "error" && (
                <p className="text-sm text-terracotta">Babak ini gagal dimuat. Lanjut manual di bawah.</p>
              )}

              {draft && phase !== "thinking" && (
                <div className="vb-rise rounded-2xl border border-hairline bg-sand p-4" data-testid="demo-draft">
                  <span className="inline-flex rounded-full bg-forest-light px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.14em] text-forest">
                    {INTENT_LABELS[draft.intent] || draft.intent}
                  </span>
                  <p className="mt-2 font-display text-base font-bold text-ink">{draft.title}</p>
                  {draft.intent === "question" ? (
                    <p className="mt-1 text-sm leading-relaxed text-mutedink" data-testid="demo-answer">
                      {draft.answer}
                    </p>
                  ) : (
                    <div className="mt-2 flex items-end justify-between">
                      <p className="text-xs text-mutedink">
                        {draft.customer_name ? `${draft.customer_name} · ` : ""}
                        {(draft.items || []).map((i) => `${i.qty}× ${i.name}`).join(", ") || draft.summary}
                      </p>
                      <p className="font-display text-xl font-extrabold text-forest">{rupiah(draft.total)}</p>
                    </div>
                  )}
                </div>
              )}

              {extra?.kind === "reminder" && (
                <div className="space-y-3" data-testid="demo-reminders">
                  {extra.reminders.map((r) => (
                    <div key={r.id} className="vb-rise rounded-2xl border border-hairline bg-sand p-4">
                      <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-mutedink">
                        {r.customer_name} · {rupiah(r.remaining)} · {r.days_ago} hari
                      </p>
                      <p className="mt-1.5 text-sm leading-relaxed text-ink">{r.message}</p>
                    </div>
                  ))}
                </div>
              )}

              {extra?.kind === "weekly" && (
                <div className="vb-rise rounded-2xl border border-hairline bg-sand p-4" data-testid="demo-weekly">
                  <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-mutedink">
                    {extra.report.period}
                  </p>
                  <div className="mt-2 flex items-end justify-between">
                    <p className="text-xs text-mutedink">
                      Laba {rupiah(extra.report.profit)} · {extra.report.transactions} transaksi
                    </p>
                    <p className="font-display text-xl font-extrabold text-forest">{rupiah(extra.report.revenue)}</p>
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-ink">{extra.report.narrative}</p>
                </div>
              )}

              {(phase === "saving" || phase === "undoing") && (
                <p className="mt-3 flex items-center gap-2 text-sm text-mutedink">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {phase === "undoing" ? "Membatalkan catatan…" : "Menyimpan…"}
                </p>
              )}

              {saved && (
                <p
                  className={`vb-rise mt-3 flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold ${
                    step.undo && phase === "saved"
                      ? "bg-terracotta-light text-[#A63A2A]"
                      : "bg-forest-light text-forest"
                  }`}
                  data-testid="demo-saved"
                >
                  {step.undo && phase === "saved" ? (
                    <Undo2 className="h-4 w-4" strokeWidth={2.8} />
                  ) : (
                    <Check className="h-4 w-4" strokeWidth={2.8} />
                  )}
                  {saved}
                </p>
              )}
            </div>

            <p className="mt-2 text-xs italic text-mutedink" data-testid="demo-caption">
              {step.caption}
            </p>

            <Button
              data-testid="demo-next-btn"
              onClick={advance}
              variant="outline"
              className="mt-4 h-12 w-full rounded-full border-forest/25 font-bold text-forest hover:bg-forest-light"
            >
              {index + 1 >= STEPS.length ? "Lihat ringkasan" : "Lanjut babak berikutnya"}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
};
