import logging
import os
import re
import tempfile
from urllib.parse import quote
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Annotated, List, Optional

from bson import ObjectId
from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, File, HTTPException, UploadFile
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import nlu  # noqa: E402
from seed import demo_data  # noqa: E402

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

app = FastAPI()
api_router = APIRouter(prefix="/api")
logger = logging.getLogger("voicebiz")
logging.basicConfig(level=logging.INFO)

PyObjectId = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]


class BaseDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    id: Optional[PyObjectId] = Field(default=None, alias="_id")

    def to_mongo(self) -> dict:
        doc = self.model_dump(by_alias=True, exclude_none=True)
        doc.pop("_id", None)
        return doc

    @classmethod
    def from_mongo(cls, doc: dict):
        return cls.model_validate(doc)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SaleItem(BaseModel):
    name: str
    qty: float = 1
    unit_price: Optional[float] = None
    subtotal: Optional[float] = None


class Sale(BaseDocument):
    items: List[SaleItem] = []
    total: float = 0
    customer_name: Optional[str] = None
    note: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)


class Expense(BaseDocument):
    title: str
    total: float = 0
    category: Optional[str] = None
    note: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)


class Customer(BaseDocument):
    name: str
    phone: Optional[str] = None
    note: Optional[str] = None
    last_active: str = Field(default_factory=now_iso)
    created_at: str = Field(default_factory=now_iso)


class Receivable(BaseDocument):
    customer_name: str
    amount: float = 0
    paid_amount: float = 0
    status: str = "belum_lunas"
    note: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)


class InventoryItem(BaseDocument):
    name: str
    qty: float = 0
    unit: str = "pcs"
    min_qty: float = 0
    updated_at: str = Field(default_factory=now_iso)


class Activity(BaseDocument):
    kind: str
    text: str
    created_at: str = Field(default_factory=now_iso)


class ParseRequest(BaseModel):
    text: str


class CommitRequest(BaseModel):
    intent: str
    title: Optional[str] = None
    summary: Optional[str] = None
    items: List[SaleItem] = []
    total: Optional[float] = 0
    customer_name: Optional[str] = None
    category: Optional[str] = None
    note: Optional[str] = None
    raw_text: Optional[str] = None
    inventory_unit: Optional[str] = None


async def ensure_seed():
    if await db.sales.count_documents({}) == 0:
        data = demo_data()
        for coll, docs in data.items():
            await db[coll].insert_many(docs)
        logger.info("Demo data seeded")


@app.on_event("startup")
async def startup():
    await ensure_seed()


def strip_ids(docs: List[dict]) -> List[dict]:
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs


async def log_activity(kind: str, text: str) -> dict:
    res = await db.activities.insert_one({"kind": kind, "text": text, "created_at": now_iso()})
    return {"op": "delete", "coll": "activities", "id": str(res.inserted_id)}


def rupiah(n: float) -> str:
    return "Rp" + f"{int(n):,}".replace(",", ".")


async def touch_customer(name: Optional[str]) -> List[dict]:
    if not name:
        return []
    existing = await db.customers.find_one({"name": {"$regex": f"^{name}$", "$options": "i"}})
    if existing:
        await db.customers.update_one({"_id": existing["_id"]}, {"$set": {"last_active": now_iso()}})
        return [{"op": "set", "coll": "customers", "id": str(existing["_id"]),
                 "fields": {"last_active": existing["last_active"]}}]
    res = await db.customers.insert_one(Customer(name=name).to_mongo())
    return [{"op": "delete", "coll": "customers", "id": str(res.inserted_id)}]


async def record_history(intent: str, message: str, raw_text: Optional[str], ops: List[dict]) -> str:
    res = await db.history.insert_one({
        "intent": intent,
        "message": message,
        "raw_text": raw_text,
        "ops": ops,
        "reverted": False,
        "created_at": now_iso(),
    })
    return str(res.inserted_id)


def wa_link(phone: Optional[str], message: str) -> Optional[str]:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    return f"https://wa.me/{digits}?text={quote(message)}"


# ---------- Voice / NLU ----------

@api_router.post("/voice/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    from emergentintegrations.llm.openai import OpenAISpeechToText

    suffix = Path(audio.filename or "rec.webm").suffix or ".webm"
    content = await audio.read()
    if not content:
        raise HTTPException(status_code=400, detail="Audio kosong")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        stt = OpenAISpeechToText(api_key=os.environ["EMERGENT_LLM_KEY"])
        with open(tmp_path, "rb") as f:
            resp = await stt.transcribe(
                file=f,
                model="whisper-1",
                response_format="json",
                language="id",
                prompt="Percakapan pemilik warung Indonesia tentang penjualan, pengeluaran, utang, dan stok.",
            )
        return {"text": getattr(resp, "text", str(resp))}
    except Exception as e:
        logger.exception("transcribe failed")
        raise HTTPException(status_code=500, detail=f"Gagal transkripsi: {e}")
    finally:
        os.unlink(tmp_path)


@api_router.post("/nlu/parse")
async def parse(req: ParseRequest):
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Teks kosong")
    try:
        draft = await nlu.parse_text(text)
    except Exception as e:
        logger.exception("parse failed")
        raise HTTPException(status_code=500, detail=f"Gagal memahami: {e}")

    draft["raw_text"] = text
    if draft.get("intent") == "question":
        ctx = await business_context()
        draft["answer"] = await nlu.answer_question(draft.get("question") or text, ctx)
    return draft


@api_router.post("/nlu/commit")
async def commit(req: CommitRequest):
    intent = req.intent
    total = float(req.total or 0)
    ops: List[dict] = []

    if intent == "sale":
        items = [i.model_dump() for i in req.items]
        if not total:
            total = sum((i.get("subtotal") or (i.get("qty") or 1) * (i.get("unit_price") or 0)) for i in items)
        sale = Sale(items=req.items, total=total, customer_name=req.customer_name, note=req.note)
        res = await db.sales.insert_one(sale.to_mongo())
        ops.append({"op": "delete", "coll": "sales", "id": str(res.inserted_id)})
        for it in items:
            inv = await db.inventory.find_one({"name": {"$regex": f"^{it['name']}$", "$options": "i"}})
            if inv:
                await db.inventory.update_one(
                    {"_id": inv["_id"]},
                    {"$set": {"qty": max(0, inv["qty"] - (it.get("qty") or 1)), "updated_at": now_iso()}},
                )
                ops.append({"op": "set", "coll": "inventory", "id": str(inv["_id"]),
                            "fields": {"qty": inv["qty"], "updated_at": inv["updated_at"]}})
        ops += await touch_customer(req.customer_name)
        label = ", ".join(f"{int(i['qty'])} {i['name']}" for i in items) or "Penjualan"
        message = f"Penjualan {rupiah(total)} tersimpan"
        ops.append(await log_activity("sale", f"Penjualan {label} — {rupiah(total)}"))

    elif intent == "expense":
        title = (req.items[0].name if req.items else None) or req.note or req.title or "Pengeluaran"
        exp = Expense(title=title, total=total, category=req.category, note=req.note)
        res = await db.expenses.insert_one(exp.to_mongo())
        ops.append({"op": "delete", "coll": "expenses", "id": str(res.inserted_id)})
        message = f"Pengeluaran {rupiah(total)} tersimpan"
        ops.append(await log_activity("expense", f"Pengeluaran {title} — {rupiah(total)}"))

    elif intent == "receivable":
        name = req.customer_name or "Pelanggan"
        rec = Receivable(customer_name=name, amount=total, note=req.note)
        res = await db.receivables.insert_one(rec.to_mongo())
        ops.append({"op": "delete", "coll": "receivables", "id": str(res.inserted_id)})
        ops += await touch_customer(name)
        message = f"Piutang {name} {rupiah(total)} tersimpan"
        ops.append(await log_activity("receivable", f"Piutang {name} — {rupiah(total)}"))

    elif intent == "receivable_payment":
        name = req.customer_name or ""
        rec = await db.receivables.find_one(
            {"customer_name": {"$regex": f"^{name}$", "$options": "i"}, "status": "belum_lunas"}
        )
        if not rec:
            raise HTTPException(status_code=404, detail=f"Piutang untuk {name or 'pelanggan'} tidak ditemukan")
        pay = total or (rec["amount"] - rec.get("paid_amount", 0))
        paid = rec.get("paid_amount", 0) + pay
        status = "lunas" if paid >= rec["amount"] else "belum_lunas"
        await db.receivables.update_one({"_id": rec["_id"]}, {"$set": {"paid_amount": paid, "status": status}})
        ops.append({"op": "set", "coll": "receivables", "id": str(rec["_id"]),
                    "fields": {"paid_amount": rec.get("paid_amount", 0), "status": rec["status"]}})
        ops += await touch_customer(rec["customer_name"])
        message = f"Pembayaran {rupiah(pay)} dari {rec['customer_name']} dicatat"
        ops.append(await log_activity("receivable_payment", f"{rec['customer_name']} bayar utang {rupiah(pay)}"))

    elif intent == "inventory":
        results = []
        for it in req.items or []:
            inv = await db.inventory.find_one({"name": {"$regex": f"^{it.name}$", "$options": "i"}})
            if inv:
                await db.inventory.update_one(
                    {"_id": inv["_id"]}, {"$set": {"qty": it.qty, "updated_at": now_iso()}}
                )
                ops.append({"op": "set", "coll": "inventory", "id": str(inv["_id"]),
                            "fields": {"qty": inv["qty"], "updated_at": inv["updated_at"]}})
            else:
                res = await db.inventory.insert_one(
                    InventoryItem(name=it.name, qty=it.qty, unit=req.inventory_unit or "pcs", min_qty=2).to_mongo()
                )
                ops.append({"op": "delete", "coll": "inventory", "id": str(res.inserted_id)})
            results.append(f"{it.name} {int(it.qty)}")
        message = "Stok diperbarui"
        ops.append(await log_activity("inventory", f"Stok diperbarui: {', '.join(results) or '-'}"))

    elif intent == "customer":
        name = req.customer_name or "Pelanggan"
        ops += await touch_customer(name)
        if req.note:
            await db.customers.update_one({"name": name}, {"$set": {"note": req.note}})
        message = f"Pelanggan {name} tersimpan"
        ops.append(await log_activity("customer", f"Pelanggan baru: {name}"))

    else:
        raise HTTPException(status_code=400, detail="Intent ini tidak bisa disimpan")

    history_id = await record_history(intent, message, req.raw_text, ops)
    return {"ok": True, "message": message, "history_id": history_id}


@api_router.get("/history")
async def history():
    docs = await db.history.find({}).sort("created_at", -1).to_list(50)
    return {"history": strip_ids(docs)}


@api_router.post("/history/{hid}/undo")
async def undo_history(hid: str):
    try:
        h = await db.history.find_one({"_id": ObjectId(hid)})
    except Exception:
        raise HTTPException(status_code=400, detail="ID riwayat tidak valid")
    if not h:
        raise HTTPException(status_code=404, detail="Riwayat tidak ditemukan")
    if h.get("reverted"):
        raise HTTPException(status_code=400, detail="Catatan ini sudah dibatalkan")
    for op in reversed(h.get("ops", [])):
        if op["op"] == "delete":
            await db[op["coll"]].delete_one({"_id": ObjectId(op["id"])})
        elif op["op"] == "set":
            await db[op["coll"]].update_one({"_id": ObjectId(op["id"])}, {"$set": op["fields"]})
    await db.history.update_one({"_id": h["_id"]}, {"$set": {"reverted": True, "reverted_at": now_iso()}})
    return {"ok": True, "message": f"Dibatalkan: {h['message']}"}


@api_router.get("/receivables/reminders")
async def receivable_reminders():
    receivables = await db.receivables.find({"status": {"$ne": "lunas"}}).sort("created_at", 1).to_list(50)
    if not receivables:
        return {"reminders": []}
    customers = await db.customers.find({}, {"_id": 0}).to_list(200)
    phones = {c["name"].lower(): c.get("phone") for c in customers}
    payload = [
        {
            "customer_name": r["customer_name"],
            "remaining": r["amount"] - r.get("paid_amount", 0),
            "days_ago": (datetime.now(timezone.utc) - datetime.fromisoformat(r["created_at"])).days,
            "note": r.get("note"),
        }
        for r in receivables
    ]
    try:
        messages = await nlu.generate_reminders(payload)
    except Exception as e:
        logger.exception("reminders failed")
        raise HTTPException(status_code=500, detail=f"Gagal membuat pesan penagihan: {e}")

    by_name = {m.get("customer_name", "").lower(): m.get("message", "") for m in messages}
    out = []
    for r, p in zip(receivables, payload):
        msg = by_name.get(r["customer_name"].lower()) or (
            f"Selamat pagi {r['customer_name']}, mohon izin mengingatkan sisa pembayaran "
            f"{rupiah(p['remaining'])}. Terima kasih banyak 🙏"
        )
        phone = phones.get(r["customer_name"].lower())
        out.append({
            "id": str(r["_id"]),
            "customer_name": r["customer_name"],
            "remaining": p["remaining"],
            "days_ago": p["days_ago"],
            "phone": phone,
            "message": msg,
            "wa_link": wa_link(phone, msg),
        })
    return {"reminders": out}


@api_router.get("/reports/weekly")
async def weekly_report():
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=6)
    sales = await db.sales.find({}, {"_id": 0}).to_list(2000)
    expenses = await db.expenses.find({}, {"_id": 0}).to_list(2000)
    receivables = await db.receivables.find({}, {"_id": 0}).to_list(2000)

    def d(x):
        return datetime.fromisoformat(x["created_at"]).date()

    week_sales = [s for s in sales if start <= d(s) <= today]
    week_expenses = [e for e in expenses if start <= d(e) <= today]
    revenue = sum(s["total"] for s in week_sales)
    expense = sum(e["total"] for e in week_expenses)

    per_item: dict[str, dict] = {}
    for s in week_sales:
        for it in s.get("items", []):
            row = per_item.setdefault(it["name"], {"name": it["name"], "qty": 0, "revenue": 0})
            row["qty"] += it.get("qty") or 0
            row["revenue"] += it.get("subtotal") or (it.get("qty") or 1) * (it.get("unit_price") or 0)
    top_items = sorted(per_item.values(), key=lambda x: x["revenue"], reverse=True)[:3]

    per_day = {}
    for s in week_sales:
        per_day[str(d(s))] = per_day.get(str(d(s)), 0) + s["total"]
    best_day = max(per_day.items(), key=lambda x: x[1]) if per_day else None
    outstanding = sum(r["amount"] - r.get("paid_amount", 0) for r in receivables if r["status"] != "lunas")

    bulan = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]

    def id_date(dt):
        return f"{dt.day} {bulan[dt.month - 1]}"

    data = {
        "period": f"{id_date(start)} – {id_date(today)} {today.year}",
        "revenue": revenue,
        "expense": expense,
        "profit": revenue - expense,
        "transactions": len(week_sales),
        "avg_per_day": round(revenue / 7),
        "top_items": top_items,
        "best_day": {"date": best_day[0], "revenue": best_day[1]} if best_day else None,
        "outstanding_receivables": outstanding,
    }
    try:
        data["narrative"] = await nlu.generate_weekly(data)
    except Exception as e:
        logger.exception("weekly report failed")
        raise HTTPException(status_code=500, detail=f"Gagal membuat laporan: {e}")

    lines = [
        f"*Laporan VoiceBiz* ({data['period']})",
        f"Pemasukan: {rupiah(revenue)}",
        f"Pengeluaran: {rupiah(expense)}",
        f"Laba: {rupiah(data['profit'])}",
        f"Transaksi: {len(week_sales)} · Rata-rata/hari: {rupiah(data['avg_per_day'])}",
    ]
    if top_items:
        lines.append("Terlaris: " + ", ".join(f"{t['name']} ({int(t['qty'])})" for t in top_items))
    if outstanding:
        lines.append(f"Piutang belum tertagih: {rupiah(outstanding)}")
    lines.append("")
    lines.append(data["narrative"])
    data["share_text"] = "\n".join(lines)
    data["share_link"] = "https://wa.me/?text=" + quote(data["share_text"])
    return data


# ---------- Business data ----------

async def business_context() -> dict:
    today = datetime.now(timezone.utc).date()
    sales = await db.sales.find({}, {"_id": 0}).to_list(1000)
    expenses = await db.expenses.find({}, {"_id": 0}).to_list(1000)
    receivables = await db.receivables.find({}, {"_id": 0}).to_list(1000)
    inventory = await db.inventory.find({}, {"_id": 0}).to_list(1000)
    customers = await db.customers.find({}, {"_id": 0}).to_list(1000)

    def d(x):
        return datetime.fromisoformat(x["created_at"]).date()

    rev_today = sum(s["total"] for s in sales if d(s) == today)
    exp_today = sum(e["total"] for e in expenses if d(e) == today)
    rev_yesterday = sum(s["total"] for s in sales if d(s) == today - timedelta(days=1))
    outstanding = sum(r["amount"] - r.get("paid_amount", 0) for r in receivables if r["status"] != "lunas")
    low_stock = [i for i in inventory if i["qty"] <= i["min_qty"]]
    inactive = [
        c for c in customers
        if (datetime.now(timezone.utc) - datetime.fromisoformat(c["last_active"])).days >= 14
    ]
    return {
        "tanggal": str(today),
        "pendapatan_hari_ini": rev_today,
        "pengeluaran_hari_ini": exp_today,
        "laba_hari_ini": rev_today - exp_today,
        "pendapatan_kemarin": rev_yesterday,
        "total_piutang_belum_lunas": outstanding,
        "stok_rendah": [{"nama": i["name"], "sisa": i["qty"], "unit": i["unit"]} for i in low_stock],
        "pelanggan_tidak_aktif": [c["name"] for c in inactive],
        "piutang": [
            {"pelanggan": r["customer_name"], "sisa": r["amount"] - r.get("paid_amount", 0)}
            for r in receivables if r["status"] != "lunas"
        ],
        "jumlah_transaksi_hari_ini": len([s for s in sales if d(s) == today]),
    }


@api_router.get("/dashboard")
async def dashboard():
    today = datetime.now(timezone.utc).date()
    sales = await db.sales.find({}, {"_id": 0}).to_list(2000)
    expenses = await db.expenses.find({}, {"_id": 0}).to_list(2000)
    receivables = await db.receivables.find({}, {"_id": 0}).to_list(2000)
    inventory = await db.inventory.find({}, {"_id": 0}).to_list(2000)
    customers = await db.customers.find({}, {"_id": 0}).to_list(2000)
    activities = await db.activities.find({}).sort("created_at", -1).to_list(12)

    def d(x):
        return datetime.fromisoformat(x["created_at"]).date()

    rev_today = sum(s["total"] for s in sales if d(s) == today)
    exp_today = sum(e["total"] for e in expenses if d(e) == today)
    rev_yesterday = sum(s["total"] for s in sales if d(s) == today - timedelta(days=1))
    trend = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        trend.append({
            "label": ["Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"][day.weekday() + 1 if day.weekday() < 6 else 0],
            "date": str(day),
            "revenue": sum(s["total"] for s in sales if d(s) == day),
        })

    outstanding_list = [
        {"customer_name": r["customer_name"], "remaining": r["amount"] - r.get("paid_amount", 0)}
        for r in receivables if r["status"] != "lunas"
    ]
    outstanding = sum(r["remaining"] for r in outstanding_list)
    low_stock = [i for i in inventory if i["qty"] <= i["min_qty"]]
    inactive = [
        c for c in customers
        if (datetime.now(timezone.utc) - datetime.fromisoformat(c["last_active"])).days >= 14
    ]

    insights = []
    if rev_yesterday and rev_today < rev_yesterday * 0.7:
        drop = round((1 - rev_today / rev_yesterday) * 100)
        insights.append({
            "type": "warning", "icon": "trending-down",
            "title": f"Penjualan turun {drop}% dari kemarin",
            "body": f"Hari ini {rupiah(rev_today)} vs kemarin {rupiah(rev_yesterday)}.",
            "action": "Broadcast promo di WhatsApp Status sore ini untuk menarik pembeli.",
        })
    elif rev_today > rev_yesterday and rev_yesterday:
        insights.append({
            "type": "good", "icon": "trending-up",
            "title": "Penjualan naik dari kemarin",
            "body": f"Hari ini {rupiah(rev_today)} vs kemarin {rupiah(rev_yesterday)}.",
            "action": "Siapkan stok bahan favorit agar tidak kehabisan besok.",
        })
    if outstanding_list:
        top = max(outstanding_list, key=lambda x: x["remaining"])
        insights.append({
            "type": "warning", "icon": "hand-coins",
            "title": f"Piutang belum tertagih {rupiah(outstanding)}",
            "body": f"Terbesar: {top['customer_name']} {rupiah(top['remaining'])}.",
            "action": f"Kirim pengingat sopan ke {top['customer_name']} hari ini.",
        })
    if low_stock:
        names = ", ".join(f"{i['name']} (sisa {int(i['qty'])} {i['unit']})" for i in low_stock[:3])
        insights.append({
            "type": "danger", "icon": "package-x",
            "title": f"{len(low_stock)} bahan hampir habis",
            "body": names,
            "action": "Belanja bahan ini sebelum jam sibuk sore.",
        })
    if inactive:
        insights.append({
            "type": "info", "icon": "user-round-x",
            "title": f"{len(inactive)} pelanggan lama tidak kembali",
            "body": ", ".join(c["name"] for c in inactive[:3]),
            "action": "Tawarkan diskon 10% lewat chat pribadi untuk mengaktifkan mereka.",
        })

    return {
        "date": str(today),
        "revenue_today": rev_today,
        "expense_today": exp_today,
        "profit_today": rev_today - exp_today,
        "revenue_yesterday": rev_yesterday,
        "transactions_today": len([s for s in sales if d(s) == today]),
        "outstanding_receivables": outstanding,
        "low_stock_count": len(low_stock),
        "customers_count": len(customers),
        "trend": trend,
        "insights": insights,
        "activities": strip_ids(activities),
    }


@api_router.get("/brief")
async def brief():
    ctx = await business_context()
    try:
        text = await nlu.generate_advice(ctx)
    except Exception as e:
        logger.exception("brief failed")
        raise HTTPException(status_code=500, detail=f"Gagal membuat briefing: {e}")
    return {"brief": text}


@api_router.get("/memory")
async def memory():
    sales = await db.sales.find({}).sort("created_at", -1).to_list(100)
    expenses = await db.expenses.find({}).sort("created_at", -1).to_list(100)
    customers = await db.customers.find({}).sort("last_active", -1).to_list(100)
    receivables = await db.receivables.find({}).sort("created_at", -1).to_list(100)
    inventory = await db.inventory.find({}).sort("name", 1).to_list(100)
    return {
        "sales": strip_ids(sales),
        "expenses": strip_ids(expenses),
        "customers": strip_ids(customers),
        "receivables": strip_ids(receivables),
        "inventory": strip_ids(inventory),
    }


@api_router.post("/demo/reset")
async def reset_demo():
    for coll in ["sales", "expenses", "customers", "receivables", "inventory", "activities", "history"]:
        await db[coll].delete_many({})
    await ensure_seed()
    return {"ok": True, "message": "Data demo dimuat ulang"}


@api_router.get("/")
async def root():
    return {"app": "VoiceBiz", "status": "ok"}


app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
