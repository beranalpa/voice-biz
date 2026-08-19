import { useEffect, useState } from "react";
import { History, Undo2 } from "lucide-react";
import { toast } from "sonner";
import { getHistory, undoHistory } from "../lib/api";

const fmtTime = (iso) =>
  new Date(iso).toLocaleString("id-ID", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export const HistoryFeed = ({ refreshKey, onChanged }) => {
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(null);

  useEffect(() => {
    getHistory()
      .then((r) => setItems(r.history))
      .catch(() => {});
  }, [refreshKey]);

  const undo = async (id) => {
    setBusy(id);
    try {
      const res = await undoHistory(id);
      toast.success(res.message);
      onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal membatalkan");
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="space-y-3" data-testid="history-feed">
      <div className="flex items-center gap-2">
        <History className="h-4 w-4 text-forest" strokeWidth={2.4} />
        <h3 className="font-display text-base font-bold text-ink">Riwayat percakapan</h3>
      </div>
      {items.length === 0 && (
        <p className="rounded-2xl border border-hairline bg-white p-4 text-sm text-mutedink">
          Belum ada catatan dari percakapan. Coba ucapkan satu transaksi.
        </p>
      )}
      {items.map((h, i) => (
        <article
          key={h.id}
          data-testid={`history-row-${i}`}
          className={`rounded-2xl border border-hairline bg-white p-4 shadow-card ${h.reverted ? "opacity-60" : ""}`}
        >
          {h.raw_text && <p className="text-xs italic text-mutedink">“{h.raw_text}”</p>}
          <div className="mt-1.5 flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="font-display text-sm font-bold text-ink">{h.message}</p>
              <p className="text-xs text-mutedink">
                {fmtTime(h.created_at)}
                {h.reverted ? " · dibatalkan" : ""}
              </p>
            </div>
            {!h.reverted && (
              <button
                data-testid={`history-undo-btn-${i}`}
                disabled={busy === h.id}
                onClick={() => undo(h.id)}
                className="flex shrink-0 items-center gap-1.5 rounded-full border border-hairline px-3 py-2 text-xs font-bold text-terracotta transition-colors hover:bg-terracotta-light disabled:opacity-50"
              >
                <Undo2 className="h-3.5 w-3.5" strokeWidth={2.6} />
                {busy === h.id ? "…" : "Batalkan"}
              </button>
            )}
          </div>
        </article>
      ))}
    </section>
  );
};
