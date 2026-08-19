import { useEffect, useState } from "react";
import { Boxes, HandCoins, MessageCircle, Receipt, ShoppingBasket, Truck, Users } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { ReminderSheet } from "../components/ReminderSheet";
import { getMemory, getPurchases, rupiah } from "../lib/api";

const fmtDate = (iso) =>
  new Date(iso).toLocaleDateString("id-ID", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

const Row = ({ title, subtitle, right, tone = "text-forest", testid }) => (
  <div data-testid={testid} className="flex items-start justify-between gap-3 rounded-2xl border border-hairline bg-white p-4 shadow-card">
    <div className="min-w-0">
      <p className="font-display text-sm font-bold text-ink">{title}</p>
      {subtitle && <p className="mt-0.5 text-xs text-mutedink">{subtitle}</p>}
    </div>
    <p className={`shrink-0 font-display text-sm font-extrabold ${tone}`}>{right}</p>
  </div>
);

export default function Memory({ refreshKey }) {
  const [data, setData] = useState(null);
  const [purchases, setPurchases] = useState([]);
  const [reminderOpen, setReminderOpen] = useState(false);

  useEffect(() => {
    getMemory().then(setData).catch(() => {});
    getPurchases().then((r) => setPurchases(r.purchases)).catch(() => {});
  }, [refreshKey]);

  if (!data) return <p className="p-6 text-sm text-mutedink">Memuat memori bisnis…</p>;

  const tabs = [
    { key: "sales", label: "Jual", icon: ShoppingBasket },
    { key: "expenses", label: "Biaya", icon: Receipt },
    { key: "receivables", label: "Piutang", icon: HandCoins },
    { key: "inventory", label: "Stok", icon: Boxes },
    { key: "purchases", label: "Belanja", icon: Truck },
    { key: "customers", label: "Pelanggan", icon: Users },
  ];

  return (
    <div className="space-y-4" data-testid="memory-page">
      <div>
        <h2 className="font-display text-2xl font-extrabold tracking-tight text-ink">Memori Bisnis</h2>
        <p className="mt-1 text-sm text-mutedink">Semua yang VoiceBiz ingat tentang usaha Anda.</p>
      </div>

      <Tabs defaultValue="sales">
        <TabsList className="grid h-auto w-full grid-cols-6 rounded-2xl bg-white p-1">
          {tabs.map((t) => (
            <TabsTrigger
              key={t.key}
              value={t.key}
              data-testid={`memory-tab-${t.key}`}
              className="flex flex-col gap-1 rounded-xl py-2 text-[9px] font-semibold data-[state=active]:bg-forest-light data-[state=active]:text-forest"
            >
              <t.icon className="h-4 w-4" strokeWidth={2.4} />
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="sales" className="mt-4 space-y-3">
          {data.sales.map((s, i) => (
            <Row
              key={s.id}
              testid={`sale-row-${i}`}
              title={s.items?.map((it) => `${it.qty}× ${it.name}`).join(", ") || "Penjualan"}
              subtitle={`${fmtDate(s.created_at)}${s.customer_name ? ` · ${s.customer_name}` : ""}`}
              right={rupiah(s.total)}
            />
          ))}
        </TabsContent>

        <TabsContent value="expenses" className="mt-4 space-y-3">
          {data.expenses.map((e, i) => (
            <Row
              key={e.id}
              testid={`expense-row-${i}`}
              title={e.title}
              subtitle={`${fmtDate(e.created_at)}${e.category ? ` · ${e.category}` : ""}`}
              right={`-${rupiah(e.total)}`}
              tone="text-terracotta"
            />
          ))}
        </TabsContent>

        <TabsContent value="receivables" className="mt-4 space-y-3">
          {data.receivables.some((r) => r.status !== "lunas") && (
            <button
              data-testid="open-reminder-btn"
              onClick={() => setReminderOpen(true)}
              className="flex w-full items-center justify-between rounded-2xl bg-forest px-5 py-4 text-sand shadow-floating transition-transform active:scale-[0.98]"
            >
              <span className="text-left">
                <span className="block font-display text-sm font-bold">Tagih via WhatsApp</span>
                <span className="block text-xs text-sand/70">
                  Pesan sopan dibuat AI untuk {data.receivables.filter((r) => r.status !== "lunas").length} pelanggan
                </span>
              </span>
              <MessageCircle className="h-5 w-5" strokeWidth={2.5} />
            </button>
          )}
          {data.receivables.map((r, i) => (
            <Row
              key={r.id}
              testid={`receivable-row-${i}`}
              title={r.customer_name}
              subtitle={`${r.status === "lunas" ? "Lunas" : "Belum lunas"}${r.note ? ` · ${r.note}` : ""}`}
              right={rupiah(r.amount - (r.paid_amount || 0))}
              tone={r.status === "lunas" ? "text-mutedink" : "text-terracotta"}
            />
          ))}
        </TabsContent>

        <TabsContent value="inventory" className="mt-4 space-y-3">
          {data.inventory.map((it, i) => (
            <Row
              key={it.id}
              testid={`inventory-row-${i}`}
              title={it.name}
              subtitle={it.qty <= it.min_qty ? `Di bawah minimum (${it.min_qty} ${it.unit})` : `Aman · min ${it.min_qty} ${it.unit}`}
              right={`${it.qty} ${it.unit}`}
              tone={it.qty <= it.min_qty ? "text-terracotta" : "text-forest"}
            />
          ))}
        </TabsContent>

        <TabsContent value="purchases" className="mt-4 space-y-3">
          {purchases.length === 0 && (
            <p className="text-sm text-mutedink">Belum ada riwayat belanja bahan.</p>
          )}
          {purchases.map((p, i) => (
            <article
              key={p.name}
              data-testid={`purchase-row-${i}`}
              className="rounded-2xl border border-hairline bg-white p-4 shadow-card"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-display text-sm font-bold text-ink">{p.name}</p>
                  <p className="mt-0.5 text-xs text-mutedink">
                    {p.times}× beli
                    {p.total_qty && p.unit ? ` · total ${p.total_qty} ${p.unit}` : ""} · terakhir{" "}
                    {fmtDate(p.last_at).split(",")[0]}
                  </p>
                </div>
                <p className="shrink-0 font-display text-sm font-extrabold text-terracotta">
                  {rupiah(p.total_spent)}
                </p>
              </div>
              {p.latest_unit_price && (
                <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
                  <span className="rounded-full bg-sand px-2.5 py-1 font-semibold text-mutedink">
                    Terakhir {rupiah(p.latest_unit_price)}
                  </span>
                  {p.cheapest_unit_price !== p.latest_unit_price && (
                    <span className="rounded-full bg-forest-light px-2.5 py-1 font-semibold text-forest">
                      Termurah {rupiah(p.cheapest_unit_price)}
                    </span>
                  )}
                </div>
              )}
              {p.hint && (
                <p className="mt-2.5 rounded-xl bg-[#FDF6EA] px-3 py-2 text-xs font-medium text-[#8A6520]">
                  {p.hint}
                </p>
              )}
            </article>
          ))}
        </TabsContent>

        <TabsContent value="customers" className="mt-4 space-y-3">
          {data.customers.map((c, i) => (
            <Row
              key={c.id}
              testid={`customer-row-${i}`}
              title={c.name}
              subtitle={`${c.note || "Pelanggan"}${c.phone ? ` · ${c.phone}` : ""}`}
              right={`Aktif ${fmtDate(c.last_active).split(",")[0]}`}
              tone="text-mutedink"
            />
          ))}
        </TabsContent>
      </Tabs>

      {reminderOpen && <ReminderSheet onClose={() => setReminderOpen(false)} />}
    </div>
  );
}
