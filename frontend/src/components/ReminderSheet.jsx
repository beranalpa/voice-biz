import { useEffect, useState } from "react";
import { Copy, Loader2, MessageCircle, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "./ui/button";
import { getReminders, rupiah } from "../lib/api";

export const ReminderSheet = ({ onClose }) => {
  const [reminders, setReminders] = useState(null);
  const [active, setActive] = useState(0);

  useEffect(() => {
    getReminders()
      .then((r) => setReminders(r.reminders))
      .catch(() => {
        toast.error("Gagal membuat pesan penagihan");
        onClose();
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const current = reminders?.[active];

  const copy = async () => {
    await navigator.clipboard.writeText(current.message);
    toast.success("Pesan disalin");
  };

  return (
    <div className="fixed inset-0 z-[65] flex items-end justify-center" data-testid="reminder-sheet">
      <div className="absolute inset-0 bg-ink/40 backdrop-blur-sm" onClick={onClose} />
      <div className="vb-rise relative z-10 w-full max-w-md rounded-t-3xl border-t border-hairline bg-white p-6 pb-8 shadow-[0_-8px_30px_rgba(0,0,0,0.12)]">
        <button
          data-testid="reminder-close-btn"
          onClick={onClose}
          className="absolute right-5 top-5 rounded-full p-2 text-mutedink transition-colors hover:bg-muted"
        >
          <X className="h-4 w-4" />
        </button>

        <h3 className="font-display text-xl font-extrabold tracking-tight text-ink">Tagih via WhatsApp</h3>
        <p className="mt-1 text-sm text-mutedink">Pesan sopan dibuat AI, siap kirim tanpa merusak hubungan.</p>

        {!reminders && (
          <p className="mt-6 flex items-center gap-2 text-sm text-mutedink">
            <Loader2 className="h-4 w-4 animate-spin" /> Menyusun pesan…
          </p>
        )}

        {reminders?.length === 0 && (
          <p className="mt-6 text-sm text-forest" data-testid="reminder-empty">
            Tidak ada piutang yang perlu ditagih. Semua sudah lunas 🎉
          </p>
        )}

        {reminders?.length > 0 && (
          <>
            <div className="mt-4 flex gap-2 overflow-x-auto pb-1 no-scrollbar">
              {reminders.map((r, i) => (
                <button
                  key={r.id}
                  data-testid={`reminder-tab-${i}`}
                  onClick={() => setActive(i)}
                  className={`shrink-0 rounded-full border px-4 py-2 text-xs font-bold transition-colors ${
                    i === active
                      ? "border-forest bg-forest-light text-forest"
                      : "border-hairline bg-sand text-mutedink"
                  }`}
                >
                  {r.customer_name} · {rupiah(r.remaining)}
                </button>
              ))}
            </div>

            <div className="mt-4 rounded-2xl border border-hairline bg-sand p-4">
              <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-mutedink">
                {current.customer_name} · utang {current.days_ago} hari · {current.phone || "nomor belum ada"}
              </p>
              <p className="mt-2 text-sm leading-relaxed text-ink" data-testid="reminder-message">
                {current.message}
              </p>
            </div>

            <div className="mt-5 flex gap-3">
              <Button
                data-testid="reminder-send-btn"
                disabled={!current.wa_link}
                onClick={() => window.open(current.wa_link, "_blank")}
                className="h-14 flex-1 rounded-full bg-forest text-base font-bold hover:bg-forest-hover"
              >
                <MessageCircle className="mr-2 h-5 w-5" strokeWidth={2.5} />
                Kirim WhatsApp
              </Button>
              <Button
                data-testid="reminder-copy-btn"
                variant="outline"
                onClick={copy}
                className="h-14 rounded-full border-forest/25 px-6 font-bold text-forest hover:bg-forest-light"
              >
                <Copy className="mr-2 h-4 w-4" strokeWidth={2.5} />
                Salin
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};
