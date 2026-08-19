import { useEffect, useState } from "react";
import { Check, Pencil, X, MessageCircleQuestion } from "lucide-react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { INTENT_LABELS, rupiah } from "../lib/api";

export const ConfirmSheet = ({ draft, onSave, onCancel, saving }) => {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(draft);

  useEffect(() => {
    setForm(draft);
    setEditing(false);
  }, [draft]);

  if (!draft) return null;
  const isQuestion = draft.intent === "question";
  const unknown = draft.intent === "unknown";

  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center" data-testid="confirm-sheet">
      <div className="absolute inset-0 bg-ink/40 backdrop-blur-sm" onClick={onCancel} />
      <div className="vb-rise relative z-10 w-full max-w-md rounded-t-3xl border-t border-hairline bg-white p-6 pb-8 shadow-[0_-8px_30px_rgba(0,0,0,0.12)]">
        <button
          onClick={onCancel}
          data-testid="confirm-close-btn"
          className="absolute right-5 top-5 rounded-full p-2 text-mutedink transition-colors hover:bg-muted"
        >
          <X className="h-4 w-4" />
        </button>

        <span className="inline-flex rounded-full bg-forest-light px-3 py-1 text-[10px] font-bold uppercase tracking-[0.14em] text-forest">
          {INTENT_LABELS[draft.intent] || draft.intent}
        </span>
        <h2 className="mt-3 font-display text-2xl font-extrabold tracking-tight text-ink" data-testid="confirm-title">
          {draft.title || (isQuestion ? "Jawaban VoiceBiz" : "Data terdeteksi")}
        </h2>
        {draft.summary && <p className="mt-1 text-sm text-mutedink">{draft.summary}</p>}

        {draft.raw_text && (
          <p className="mt-4 rounded-xl bg-muted px-3 py-2 text-xs italic text-mutedink" data-testid="confirm-raw-text">
            “{draft.raw_text}”
          </p>
        )}

        {isQuestion ? (
          <div className="mt-4 flex gap-3 rounded-2xl border border-forest/15 bg-forest-light p-4" data-testid="confirm-answer">
            <MessageCircleQuestion className="mt-0.5 h-5 w-5 shrink-0 text-forest" strokeWidth={2.4} />
            <p className="text-sm leading-relaxed text-forest">{draft.answer}</p>
          </div>
        ) : unknown ? (
          <p className="mt-4 text-sm text-terracotta" data-testid="confirm-unknown">
            Maaf, saya belum paham. Coba ucapkan lagi lebih spesifik, misalnya “jual 2 nasi goreng total 40 ribu”.
          </p>
        ) : (
          <div className="mt-4 space-y-3">
            {(form.customer_name || draft.intent.includes("receivable") || draft.intent === "customer") && (
              <Field
                label="Pelanggan"
                editing={editing}
                value={form.customer_name || ""}
                onChange={(v) => setForm({ ...form, customer_name: v })}
                testid="field-customer"
              />
            )}
            {(form.items || []).map((it, i) => (
              <div
                key={i}
                className="flex items-center justify-between rounded-2xl border border-hairline bg-sand px-4 py-3"
                data-testid={`draft-item-${i}`}
              >
                <div>
                  <p className="font-display text-sm font-bold text-ink">{it.name}</p>
                  <p className="text-xs text-mutedink">
                    {it.qty}× {it.unit_price ? rupiah(it.unit_price) : "—"}
                  </p>
                </div>
                <p className="font-display text-sm font-bold text-forest">
                  {rupiah(it.subtotal || (it.qty || 1) * (it.unit_price || 0))}
                </p>
              </div>
            ))}
            <div className="flex items-center justify-between border-t border-hairline pt-3">
              <span className="text-xs font-bold uppercase tracking-[0.14em] text-mutedink">Total</span>
              {editing ? (
                <Input
                  data-testid="field-total"
                  type="number"
                  value={form.total || 0}
                  onChange={(e) => setForm({ ...form, total: Number(e.target.value) })}
                  className="h-11 w-40 rounded-xl border-hairline text-right font-display font-bold"
                />
              ) : (
                <span className="font-display text-2xl font-extrabold tracking-tight text-forest" data-testid="confirm-total">
                  {rupiah(form.total)}
                </span>
              )}
            </div>
          </div>
        )}

        <div className="mt-6 flex gap-3">
          {isQuestion || unknown ? (
            <Button
              data-testid="confirm-ok-btn"
              onClick={onCancel}
              className="h-14 flex-1 rounded-full bg-forest text-base font-bold hover:bg-forest-hover"
            >
              Mengerti
            </Button>
          ) : (
            <>
              <Button
                data-testid="confirm-save-btn"
                disabled={saving}
                onClick={() => onSave(form)}
                className="h-14 flex-1 rounded-full bg-forest text-base font-bold hover:bg-forest-hover"
              >
                <Check className="mr-2 h-5 w-5" strokeWidth={2.6} />
                {saving ? "Menyimpan…" : "Simpan"}
              </Button>
              <Button
                data-testid="confirm-edit-btn"
                variant="outline"
                onClick={() => setEditing((e) => !e)}
                className="h-14 rounded-full border-forest/25 px-6 text-base font-bold text-forest hover:bg-forest-light"
              >
                <Pencil className="mr-2 h-4 w-4" strokeWidth={2.6} />
                {editing ? "Selesai" : "Edit"}
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

const Field = ({ label, editing, value, onChange, testid }) => (
  <div className="flex items-center justify-between gap-3 rounded-2xl border border-hairline bg-sand px-4 py-3">
    <span className="text-xs font-bold uppercase tracking-[0.14em] text-mutedink">{label}</span>
    {editing ? (
      <Input
        data-testid={testid}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-10 w-44 rounded-xl border-hairline text-right"
      />
    ) : (
      <span className="font-display text-sm font-bold text-ink">{value || "—"}</span>
    )}
  </div>
);
