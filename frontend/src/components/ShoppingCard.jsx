import { useEffect, useState } from "react";
import { Check, Copy, ShoppingBasket, Sun } from "lucide-react";
import { toast } from "sonner";
import { getShoppingList, restockItem } from "../lib/api";

export const ShoppingCard = ({ refreshKey, onChanged }) => {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(null);

  useEffect(() => {
    getShoppingList().then(setData).catch(() => {});
  }, [refreshKey]);

  if (!data || data.items.length === 0) return null;

  const bought = async (item) => {
    setBusy(item.id);
    try {
      const res = await restockItem(item.id, item.target_qty);
      toast.success(res.message);
      const r = await getShoppingList();
      setData(r);
      onChanged();
    } catch {
      toast.error("Gagal memperbarui stok");
    } finally {
      setBusy(null);
    }
  };

  const copy = async () => {
    await navigator.clipboard.writeText(data.share_text);
    toast.success("Daftar belanja disalin");
  };

  return (
    <section
      data-testid="shopping-card"
      className="rounded-2xl border border-ochre/30 bg-[#FDF6EA] p-5"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 text-[#8A6520]">
          <Sun className="h-4 w-4" strokeWidth={2.5} />
          <h3 className="font-display text-base font-bold">Belanja sebelum jam sibuk</h3>
        </div>
        <button
          data-testid="shopping-copy-btn"
          onClick={copy}
          className="flex items-center gap-1.5 rounded-full bg-white px-3 py-1.5 text-xs font-bold text-[#8A6520] shadow-card"
        >
          <Copy className="h-3.5 w-3.5" strokeWidth={2.6} /> Salin
        </button>
      </div>
      <p className="mt-1 text-xs text-[#8A6520]/80">
        {data.items.length} bahan di bawah stok minimum. Beli sekarang agar tidak kehabisan saat ramai.
      </p>

      <div className="mt-4 space-y-2.5">
        {data.items.map((it, i) => (
          <div
            key={it.id}
            data-testid={`shopping-item-${i}`}
            className="flex items-center justify-between gap-3 rounded-xl bg-white p-3.5"
          >
            <div className="flex items-center gap-3">
              <ShoppingBasket className="h-4 w-4 text-[#8A6520]" strokeWidth={2.4} />
              <div>
                <p className="font-display text-sm font-bold text-ink">{it.name}</p>
                <p className="text-xs text-mutedink">
                  Beli {it.suggested_qty} {it.unit} · sisa {it.qty} {it.unit}
                </p>
              </div>
            </div>
            <button
              data-testid={`shopping-bought-btn-${i}`}
              disabled={busy === it.id}
              onClick={() => bought(it)}
              className="flex shrink-0 items-center gap-1.5 rounded-full bg-forest px-3.5 py-2 text-xs font-bold text-sand transition-transform active:scale-95 disabled:opacity-60"
            >
              <Check className="h-3.5 w-3.5" strokeWidth={2.8} />
              {busy === it.id ? "…" : "Sudah beli"}
            </button>
          </div>
        ))}
      </div>
    </section>
  );
};
