import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Annotated, Any, List, Optional

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


async def log_activity(kind: str, text: str):
    await db.activities.insert_one({"kind": kind, "text": text, "created_at": now_iso()})


def rupiah(n: float) -> str:
    return "Rp" + f"{int(n):,}".replace(",", ".")


async def touch_customer(name: Optional[str]):
    if not name:
        return
    existing = await db.customers.find_one({"name": {"$regex": f"^{name}$", "$options": "i"}})
    if existing:
        await db.customers.update_one({"_id": existing["_id"]}, {"$set": {"last_active": now_iso()}})
    else:
        await db.customers.insert_one(Customer(name=name).to_mongo())


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
    if intent == "sale":
        items = [i.model_dump() for i in req.items]
        if not total:
            total = sum((i.get("subtotal") or (i.get("qty") or 1) * (i.get("unit_price") or 0)) for i in items)
        sale = Sale(items=req.items, total=total, customer_name=req.customer_name, note=req.note)
        await db.sales.insert_one(sale.to_mongo())
        for it in items:
            inv = await db.inventory.find_one({"name": {"$regex": f"^{it['name']}$", "$options": "i"}})
            if inv:
                await db.inventory.update_one(
                    {"_id": inv["_id"]},
                    {"$set": {"qty": max(0, inv["qty"] - (it.get("qty") or 1)), "updated_at": now_iso()}},
                )
        await touch_customer(req.customer_name)
        label = ", ".join(f"{int(i['qty'])} {i['name']}" for i in items) or "Penjualan"
        await log_activity("sale", f"Penjualan {label} — {rupiah(total)}")
        return {"ok": True, "message": f"Penjualan {rupiah(total)} tersimpan"}

    if intent == "expense":
        title = (req.items[0].name if req.items else None) or req.note or req.title or "Pengeluaran"
        exp = Expense(title=title, total=total, category=req.category, note=req.note)
        await db.expenses.insert_one(exp.to_mongo())
        await log_activity("expense", f"Pengeluaran {title} — {rupiah(total)}")
        return {"ok": True, "message": f"Pengeluaran {rupiah(total)} tersimpan"}

    if intent == "receivable":
        name = req.customer_name or "Pelanggan"
        rec = Receivable(customer_name=name, amount=total, note=req.note)
        await db.receivables.insert_one(rec.to_mongo())
        await touch_customer(name)
        await log_activity("receivable", f"Piutang {name} — {rupiah(total)}")
        return {"ok": True, "message": f"Piutang {name} {rupiah(total)} tersimpan"}

    if intent == "receivable_payment":
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
        await touch_customer(rec["customer_name"])
        await log_activity("receivable_payment", f"{rec['customer_name']} bayar utang {rupiah(pay)}")
        return {"ok": True, "message": f"Pembayaran {rupiah(pay)} dari {rec['customer_name']} dicatat"}

    if intent == "inventory":
        results = []
        for it in req.items or []:
            inv = await db.inventory.find_one({"name": {"$regex": f"^{it.name}$", "$options": "i"}})
            if inv:
                await db.inventory.update_one(
                    {"_id": inv["_id"]}, {"$set": {"qty": it.qty, "updated_at": now_iso()}}
                )
            else:
                await db.inventory.insert_one(
                    InventoryItem(name=it.name, qty=it.qty, unit=req.inventory_unit or "pcs", min_qty=2).to_mongo()
                )
            results.append(f"{it.name} {int(it.qty)}")
        await log_activity("inventory", f"Stok diperbarui: {', '.join(results) or '-'}")
        return {"ok": True, "message": "Stok diperbarui"}

    if intent == "customer":
        name = req.customer_name or "Pelanggan"
        await touch_customer(name)
        if req.note:
            await db.customers.update_one({"name": name}, {"$set": {"note": req.note}})
        await log_activity("customer", f"Pelanggan baru: {name}")
        return {"ok": True, "message": f"Pelanggan {name} tersimpan"}

    raise HTTPException(status_code=400, detail="Intent ini tidak bisa disimpan")


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
            "title": f"Penjualan naik dari kemarin",
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
    for coll in ["sales", "expenses", "customers", "receivables", "inventory", "activities"]:
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
