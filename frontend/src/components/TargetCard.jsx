import { useEffect, useState } from "react";
import { Check, Pencil, Target, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { rupiah, suggestTarget, updateSettings } from "../lib/api";

export const TargetCard = ({ data, onChanged }) => {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const [suggestion, setSuggestion] = useState(null);

  useEffect(() => {
    suggestTarget().then(setSuggestion).catch(() => {});
  }, []);

  if (!data) return null;
  const pct = data.target_progress ?? 0;
  const done = data.target_remaining === 0;

  const apply = async (n) => {
    await updateSettings({ daily_target: n });
    setEditing(false);
    toast.success(`Target harian jadi ${rupiah(n)}`);
    onChanged();
  };

  const save = async () => {
    const n = Number(value);
    if (!n || n <= 0) {
      toast.error("Masukkan target yang valid");
      return;
    }
    await apply(n);
  };

  return (
    <section
      data-testid="target-card"
      className="rounded-2xl border border-hairline bg-white p-5 shadow-card"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <Target className="h-4 w-4 text-forest" strokeWidth={2.5} />
          <h3 className="font-display text-base font-bold text-ink">Target hari ini</h3>
        </div>
        {editing ? (
          <button
            data-testid="target-save-btn"
            onClick={save}
            className="flex items-center gap-1.5 rounded-full bg-forest px-3 py-1.5 text-xs font-bold text-sand"
          >
            <Check className="h-3.5 w-3.5" strokeWidth={2.8} /> Simpan
          </button>
        ) : (
          <button
            data-testid="target-edit-btn"
            onClick={() => {
              setValue(String(data.daily_target || 0));
              setEditing(true);
            }}
            className="flex items-center gap-1.5 rounded-full border border-hairline px-3 py-1.5 text-xs font-bold text-mutedink transition-colors hover:text-forest"
          >
            <Pencil className="h-3.5 w-3.5" strokeWidth={2.6} /> Ubah
          </button>
        )}
      </div>

      {editing ? (
        <input
          data-testid="target-input"
          type="number"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && save()}
          className="mt-4 h-12 w-full rounded-xl border border-hairline bg-sand px-4 font-display text-lg font-bold text-ink outline-none focus:border-forest/40"
        />
      ) : (
        <>
          <div className="mt-3 flex items-end justify-between">
            <p className="font-display text-2xl font-extrabold tracking-tight text-ink" data-testid="target-progress-text">
              {pct}%
            </p>
            <p className="text-xs text-mutedink">
              {rupiah(data.revenue_today)} / {rupiah(data.daily_target)}
            </p>
          </div>
          <div className="mt-2 h-2.5 w-full overflow-hidden rounded-full bg-muted">
            <div
              className={`h-full rounded-full transition-[width] duration-700 ${done ? "bg-forest" : "bg-ochre"}`}
              style={{ width: `${Math.max(3, pct)}%` }}
            />
          </div>
          <p
            className={`mt-3 text-sm font-semibold ${done ? "text-forest" : "text-ink"}`}
            data-testid="target-remaining-text"
          >
            {done
              ? "Target tercapai — mantap! Pertahankan sampai tutup warung."
              : `Sisa ${rupiah(data.target_remaining)} lagi untuk capai target hari ini.`}
          </p>

          {suggestion && Math.abs(suggestion.suggested - (data.daily_target || 0)) > 1000 && (
            <div className="mt-4 rounded-xl border border-forest/15 bg-forest-light p-3.5" data-testid="target-suggestion">
              <p className="text-xs leading-relaxed text-forest">{suggestion.reason}</p>
              <button
                data-testid="target-apply-suggestion-btn"
                onClick={() => apply(suggestion.suggested)}
                className="mt-2.5 flex items-center gap-1.5 rounded-full bg-forest px-3.5 py-2 text-xs font-bold text-sand transition-transform active:scale-95"
              >
                <Wand2 className="h-3.5 w-3.5" strokeWidth={2.6} />
                Pakai saran {rupiah(suggestion.suggested)}
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
};
