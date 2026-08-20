import asyncio
import base64
import hashlib
import io
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
from fastapi import APIRouter, FastAPI, File, HTTPException, UploadFile, Response
from motor.motor_asyncio import AsyncIOMotorClient
from PIL import Image
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
    unit: Optional[str] = None
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
    items: List[SaleItem] = []
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
    add_to_inventory: bool = False


class CorrectionRequest(BaseModel):
    total: Optional[float] = None
    customer_name: Optional[str] = None
    item_name: Optional[str] = None
    raw_text: Optional[str] = None


class SettingsUpdate(BaseModel):
    daily_target: Optional[float] = None


class RestockRequest(BaseModel):
    qty: Optional[float] = None


_seed_lock = asyncio.Lock()
_reset_lock = asyncio.Lock()


async def ensure_seed() -> None:
    async with _seed_lock:
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


async def record_history(intent: str, message: str, raw_text: Optional[str], ops: List[dict],
                         draft: Optional[dict] = None) -> str:
    res = await db.history.insert_one({
        "intent": intent,
        "message": message,
        "raw_text": raw_text,
        "ops": ops,
        "draft": draft,
        "reverted": False,
        "created_at": now_iso(),
    })
    return str(res.inserted_id)


async def revert_ops(h: dict):
    for op in reversed(h.get("ops", [])):
        if op["op"] == "delete":
            await db[op["coll"]].delete_one({"_id": ObjectId(op["id"])})
        elif op["op"] == "set":
            await db[op["coll"]].update_one({"_id": ObjectId(op["id"])}, {"$set": op["fields"]})
    await db.history.update_one({"_id": h["_id"]}, {"$set": {"reverted": True, "reverted_at": now_iso()}})


async def get_settings_doc() -> dict:
    doc = await db.settings.find_one({"key": "app"})
    if not doc:
        doc = {"key": "app", "daily_target": 300000}
        await db.settings.insert_one(doc)
    return doc


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


CommitResult = tuple[str, List[dict]]


async def _adjust_inventory(name: str, delta: float, unit: Optional[str] = None,
                            absolute: Optional[float] = None, create_missing: bool = True) -> List[dict]:
    inv = await db.inventory.find_one({"name": {"$regex": f"^{name}$", "$options": "i"}})
    if inv:
        new_qty = absolute if absolute is not None else max(0, inv["qty"] + delta)
        await db.inventory.update_one(
            {"_id": inv["_id"]}, {"$set": {"qty": new_qty, "updated_at": now_iso()}}
        )
        return [{"op": "set", "coll": "inventory", "id": str(inv["_id"]),
                 "fields": {"qty": inv["qty"], "updated_at": inv["updated_at"]}}]
    if not create_missing:
        return []
    qty = absolute if absolute is not None else max(0, delta)
    res = await db.inventory.insert_one(
        InventoryItem(name=name, qty=qty, unit=unit or "pcs", min_qty=max(1, round(qty / 2))).to_mongo()
    )
    return [{"op": "delete", "coll": "inventory", "id": str(res.inserted_id)}]


async def _commit_sale(req: CommitRequest, total: float) -> CommitResult:
    items = [i.model_dump() for i in req.items]
    if not total:
        total = sum((i.get("subtotal") or (i.get("qty") or 1) * (i.get("unit_price") or 0)) for i in items)
    res = await db.sales.insert_one(
        Sale(items=req.items, total=total, customer_name=req.customer_name, note=req.note).to_mongo()
    )
    ops: List[dict] = [{"op": "delete", "coll": "sales", "id": str(res.inserted_id)}]
    for it in items:
        ops += await _adjust_inventory(it["name"], -(it.get("qty") or 1), create_missing=False)
    ops += await touch_customer(req.customer_name)
    label = ", ".join(f"{int(i['qty'])} {i['name']}" for i in items) or "Penjualan"
    ops.append(await log_activity("sale", f"Penjualan {label} — {rupiah(total)}"))
    return f"Penjualan {rupiah(total)} tersimpan", ops


async def _commit_expense(req: CommitRequest, total: float) -> CommitResult:
    title = (req.items[0].name if req.items else None) or req.note or req.title or "Pengeluaran"
    res = await db.expenses.insert_one(
        Expense(title=title, total=total, category=req.category, note=req.note, items=req.items).to_mongo()
    )
    ops: List[dict] = [{"op": "delete", "coll": "expenses", "id": str(res.inserted_id)}]
    message = f"Pengeluaran {rupiah(total)} tersimpan"
    if req.add_to_inventory and req.items:
        for it in req.items:
            ops += await _adjust_inventory(it.name, it.qty or 1, it.unit or req.inventory_unit)
        message += f" & stok {', '.join(it.name for it in req.items)} bertambah"
    ops.append(await log_activity("expense", f"Pengeluaran {title} — {rupiah(total)}"))
    return message, ops


async def _commit_receivable(req: CommitRequest, total: float) -> CommitResult:
    name = req.customer_name or "Pelanggan"
    res = await db.receivables.insert_one(
        Receivable(customer_name=name, amount=total, note=req.note).to_mongo()
    )
    ops: List[dict] = [{"op": "delete", "coll": "receivables", "id": str(res.inserted_id)}]
    ops += await touch_customer(name)
    ops.append(await log_activity("receivable", f"Piutang {name} — {rupiah(total)}"))
    return f"Piutang {name} {rupiah(total)} tersimpan", ops


async def _commit_receivable_payment(req: CommitRequest, total: float) -> CommitResult:
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
    ops: List[dict] = [{"op": "set", "coll": "receivables", "id": str(rec["_id"]),
                        "fields": {"paid_amount": rec.get("paid_amount", 0), "status": rec["status"]}}]
    ops += await touch_customer(rec["customer_name"])
    ops.append(await log_activity("receivable_payment", f"{rec['customer_name']} bayar utang {rupiah(pay)}"))
    return f"Pembayaran {rupiah(pay)} dari {rec['customer_name']} dicatat", ops


async def _commit_inventory(req: CommitRequest, total: float) -> CommitResult:
    ops: List[dict] = []
    results = []
    for it in req.items or []:
        ops += await _adjust_inventory(it.name, 0, it.unit or req.inventory_unit, absolute=it.qty)
        results.append(f"{it.name} {int(it.qty)}")
    ops.append(await log_activity("inventory", f"Stok diperbarui: {', '.join(results) or '-'}"))
    return "Stok diperbarui", ops


async def _commit_customer(req: CommitRequest, total: float) -> CommitResult:
    name = req.customer_name or "Pelanggan"
    ops: List[dict] = await touch_customer(name)
    if req.note:
        await db.customers.update_one({"name": name}, {"$set": {"note": req.note}})
    ops.append(await log_activity("customer", f"Pelanggan baru: {name}"))
    return f"Pelanggan {name} tersimpan", ops


COMMIT_HANDLERS = {
    "sale": _commit_sale,
    "expense": _commit_expense,
    "receivable": _commit_receivable,
    "receivable_payment": _commit_receivable_payment,
    "inventory": _commit_inventory,
    "customer": _commit_customer,
}


async def apply_commit(req: CommitRequest) -> CommitResult:
    handler = COMMIT_HANDLERS.get(req.intent)
    if not handler:
        raise HTTPException(status_code=400, detail="Intent ini tidak bisa disimpan")
    return await handler(req, float(req.total or 0))


@api_router.post("/nlu/commit")
async def commit(req: CommitRequest):
    message, ops = await apply_commit(req)
    history_id = await record_history(req.intent, message, req.raw_text, ops, req.model_dump())
    return {"ok": True, "message": message, "history_id": history_id}


@api_router.post("/nlu/correct")
async def correct_last(req: CorrectionRequest):
    h = await db.history.find_one(
        {"reverted": False, "draft": {"$ne": None}}, sort=[("created_at", -1)]
    )
    if not h:
        raise HTTPException(status_code=404, detail="Belum ada catatan yang bisa dikoreksi")

    draft = dict(h["draft"])
    await revert_ops(h)

    if req.customer_name:
        draft["customer_name"] = req.customer_name
    items = draft.get("items") or []
    if req.item_name and items:
        items[0]["name"] = req.item_name
    if req.total:
        draft["total"] = req.total
        if len(items) == 1:
            qty = items[0].get("qty") or 1
            items[0]["subtotal"] = req.total
            items[0]["unit_price"] = round(req.total / qty) if qty else req.total
        else:
            for it in items:
                it["subtotal"] = None
                it["unit_price"] = None
    draft["items"] = items
    draft["raw_text"] = req.raw_text or draft.get("raw_text")

    new_req = CommitRequest(**draft)
    message, ops = await apply_commit(new_req)
    history_id = await record_history(new_req.intent, f"Dikoreksi → {message}", req.raw_text, ops, draft)
    return {
        "ok": True,
        "message": f"Catatan sebelumnya diperbaiki. {message}",
        "history_id": history_id,
        "previous": h["message"],
    }


@api_router.get("/purchases/history")
async def purchase_history():
    expenses = await db.expenses.find({}, {"_id": 0}).to_list(2000)
    groups: dict[str, dict] = {}
    for e in expenses:
        rows = e.get("items") or [{"name": e["title"], "qty": 1, "unit": None,
                                   "unit_price": e["total"], "subtotal": e["total"]}]
        for it in rows:
            key = (it.get("name") or e["title"]).strip().lower()
            g = groups.setdefault(key, {
                "name": (it.get("name") or e["title"]).strip().title(),
                "times": 0, "total_spent": 0, "total_qty": 0,
                "unit": it.get("unit"), "prices": [], "last_at": e["created_at"],
            })
            qty = it.get("qty") or 1
            sub = it.get("subtotal") or (qty * (it.get("unit_price") or 0)) or 0
            g["times"] += 1
            g["total_spent"] += sub
            g["total_qty"] += qty
            g["unit"] = g["unit"] or it.get("unit")
            if it.get("unit_price"):
                g["prices"].append({"price": it["unit_price"], "at": e["created_at"]})
            if e["created_at"] > g["last_at"]:
                g["last_at"] = e["created_at"]

    out = [_purchase_row(g) for g in groups.values()]
    out.sort(key=lambda x: x["total_spent"], reverse=True)
    return {"purchases": out}


def _purchase_hint(group: dict, cheapest: Optional[float], latest: Optional[float]) -> Optional[str]:
    if cheapest and latest and latest > cheapest * 1.1:
        return (
            f"Harga terakhir {rupiah(latest)}, pernah dapat {rupiah(cheapest)}. "
            f"Coba nego atau bandingkan pemasok."
        )
    if group["times"] >= 3:
        return f"Sudah {group['times']}× beli — minta harga langganan ke pemasok."
    return None


def _purchase_row(group: dict) -> dict:
    prices = sorted(group["prices"], key=lambda p: p["at"])
    cheapest = min((p["price"] for p in prices), default=None)
    latest = prices[-1]["price"] if prices else None
    return {
        "name": group["name"],
        "times": group["times"],
        "total_spent": round(group["total_spent"]),
        "total_qty": round(group["total_qty"], 2),
        "unit": group["unit"],
        "avg_unit_price": round(sum(p["price"] for p in prices) / len(prices)) if prices else None,
        "cheapest_unit_price": cheapest,
        "latest_unit_price": latest,
        "last_at": group["last_at"],
        "hint": _purchase_hint(group, cheapest, latest),
    }


@api_router.get("/brief/audio")
async def brief_audio(text: str):
    from emergentintegrations.llm.openai import OpenAITextToSpeech

    clean = re.sub(r"[*_#>~|`]", "", text)
    clean = re.sub(r"https?://\S+", "", clean)
    clean = re.sub(r"[^\w\s.,!?%:;()/-]", "", clean, flags=re.UNICODE)
    clean = re.sub(r"\s+", " ", clean).strip()[:1200]
    if not clean:
        raise HTTPException(status_code=400, detail="Teks kosong")

    key = hashlib.sha256(f"{clean}|nova|tts-1|1.0".encode()).hexdigest()
    cached = await db.tts_cache.find_one({"key": key})
    if cached:
        return Response(content=cached["audio"], media_type="audio/mpeg",
                        headers={"Cache-Control": "public, max-age=86400"})
    audio: Optional[bytes] = None
    try:
        tts = OpenAITextToSpeech(api_key=os.environ["EMERGENT_LLM_KEY"])
        audio = await tts.generate_speech(text=clean, model="tts-1", voice="nova")
    except Exception as e:
        logger.exception("tts failed")
        raise HTTPException(status_code=500, detail=f"Gagal membuat suara: {e}")
    if not audio:
        raise HTTPException(status_code=500, detail="Suara kosong dari penyedia TTS")
    await db.tts_cache.insert_one({"key": key, "audio": audio, "created_at": now_iso()})
    return Response(content=audio, media_type="audio/mpeg",
                    headers={"Cache-Control": "public, max-age=86400"})


@api_router.get("/settings/suggest-target")
async def suggest_target():
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=29)
    sales = await db.sales.find({}, {"_id": 0}).to_list(3000)

    per_day: dict[str, float] = {}
    for s in sales:
        day = datetime.fromisoformat(s["created_at"]).date()
        if start <= day <= today:
            per_day[str(day)] = per_day.get(str(day), 0) + s["total"]

    active = [v for v in per_day.values() if v > 0]
    if not active:
        return {"suggested": 300000, "avg_30d": 0, "avg_active_day": 0, "active_days": 0,
                "reason": "Belum ada penjualan tercatat, mulai dari target Rp300.000/hari."}

    avg_30 = round(sum(active) / 30)
    avg_active = round(sum(active) / len(active))
    suggested = int(round(avg_active * 1.1 / 5000) * 5000)
    return {
        "suggested": suggested,
        "avg_30d": avg_30,
        "avg_active_day": avg_active,
        "active_days": len(active),
        "reason": (
            f"Rata-rata {rupiah(avg_active)}/hari dari {len(active)} hari jualan terakhir. "
            f"Target {rupiah(suggested)} = 10% di atas rata-rata, masih realistis dikejar."
        ),
    }


@api_router.get("/shopping-list")
async def shopping_list():
    inventory = await db.inventory.find({}).sort("qty", 1).to_list(200)
    items = []
    for i in inventory:
        if i["qty"] <= i["min_qty"]:
            target = max(i["min_qty"] * 2, i["min_qty"] + 1)
            items.append({
                "id": str(i["_id"]),
                "name": i["name"],
                "qty": i["qty"],
                "unit": i["unit"],
                "min_qty": i["min_qty"],
                "suggested_qty": round(target - i["qty"], 2),
                "target_qty": target,
            })
    lines = ["*Belanja warung hari ini*"] + [
        f"- {it['name']}: beli {it['suggested_qty']:g} {it['unit']} (sisa {it['qty']:g})" for it in items
    ]
    text = "\n".join(lines) if items else "Semua stok masih aman hari ini."
    return {
        "items": items,
        "share_text": text,
        "share_link": "https://wa.me/?text=" + quote(text),
    }


@api_router.post("/inventory/{iid}/restock")
async def restock_item(iid: str, req: RestockRequest):
    try:
        oid = ObjectId(iid)
    except Exception:
        raise HTTPException(status_code=400, detail="ID stok tidak valid")
    inv = await db.inventory.find_one({"_id": oid})
    if not inv:
        raise HTTPException(status_code=404, detail="Bahan tidak ditemukan")
    new_qty = req.qty if req.qty is not None else max(inv["min_qty"] * 2, inv["min_qty"] + 1)
    await db.inventory.update_one({"_id": oid}, {"$set": {"qty": new_qty, "updated_at": now_iso()}})
    ops = [{"op": "set", "coll": "inventory", "id": iid,
            "fields": {"qty": inv["qty"], "updated_at": inv["updated_at"]}}]
    ops.append(await log_activity("inventory", f"Belanja {inv['name']} → {new_qty:g} {inv['unit']}"))
    message = f"{inv['name']} diperbarui jadi {new_qty:g} {inv['unit']}"
    history_id = await record_history("inventory", message, "Tandai sudah dibeli", ops)
    return {"ok": True, "message": message, "history_id": history_id}


@api_router.post("/expenses/from-receipt")
async def expense_from_receipt(image: UploadFile = File(...)):
    content = await image.read()
    if not content:
        raise HTTPException(status_code=400, detail="Gambar kosong")
    try:
        img = Image.open(io.BytesIO(content))
        img = img.convert("RGB")
        img.thumbnail((1400, 1400))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=82)
        b64 = base64.b64encode(buf.getvalue()).decode()
    except Exception:
        raise HTTPException(status_code=400, detail="Format gambar tidak didukung")

    try:
        data = await nlu.parse_receipt(b64)
    except Exception as e:
        logger.exception("receipt parse failed")
        raise HTTPException(status_code=500, detail=f"Gagal membaca nota: {e}")

    items = data.get("items") or []
    total = float(data.get("total") or 0) or sum(
        (it.get("subtotal") or (it.get("qty") or 1) * (it.get("unit_price") or 0)) for it in items
    )
    if total <= 0:
        return {
            "intent": "unknown",
            "title": "Nota tidak terbaca",
            "summary": "Foto tidak bisa dibaca sebagai nota belanja. Coba foto lebih terang.",
            "items": [],
            "total": 0,
            "confidence": 0,
            "raw_text": "Foto nota belanja",
        }
    return {
        "intent": "expense",
        "title": "Pengeluaran dari nota terdeteksi",
        "summary": data.get("note") or f"{data.get('title') or 'Belanja'} — {len(items)} item",
        "items": items,
        "total": total,
        "category": data.get("category") or "bahan baku",
        "note": data.get("title") or "Belanja dari nota",
        "confidence": data.get("confidence", 0.8),
        "raw_text": "Foto nota belanja",
    }


@api_router.get("/settings")
async def read_settings():
    doc = await get_settings_doc()
    return {"daily_target": doc.get("daily_target", 300000)}


@api_router.put("/settings")
async def update_settings(req: SettingsUpdate):
    await get_settings_doc()
    if req.daily_target is not None:
        await db.settings.update_one({"key": "app"}, {"$set": {"daily_target": float(req.daily_target)}})
    doc = await get_settings_doc()
    return {"daily_target": doc.get("daily_target", 300000)}


@api_router.post("/receivables/{rid}/reminded")
async def mark_reminded(rid: str):
    try:
        oid = ObjectId(rid)
    except Exception:
        raise HTTPException(status_code=400, detail="ID piutang tidak valid")
    res = await db.receivables.update_one({"_id": oid}, {"$set": {"last_reminded_at": now_iso()}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Piutang tidak ditemukan")
    return {"ok": True, "message": "Ditandai sudah ditagih hari ini"}


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
    await revert_ops(h)
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
    today_str = str(datetime.now(timezone.utc).date())
    out = []
    for r, p in zip(receivables, payload):
        msg = by_name.get(r["customer_name"].lower()) or (
            f"Selamat pagi {r['customer_name']}, mohon izin mengingatkan sisa pembayaran "
            f"{rupiah(p['remaining'])}. Terima kasih banyak 🙏"
        )
        phone = phones.get(r["customer_name"].lower())
        last = r.get("last_reminded_at")
        out.append({
            "id": str(r["_id"]),
            "customer_name": r["customer_name"],
            "remaining": p["remaining"],
            "days_ago": p["days_ago"],
            "phone": phone,
            "message": msg,
            "wa_link": wa_link(phone, msg),
            "last_reminded_at": last,
            "reminded_today": bool(last and last[:10] == today_str),
        })
    return {"reminders": out}


@api_router.get("/reports/weekly")
async def weekly_report(period: str = "weekly"):
    days = 30 if period == "monthly" else 7
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days - 1)
    sales = await db.sales.find({}, {"_id": 0}).to_list(2000)
    expenses = await db.expenses.find({}, {"_id": 0}).to_list(2000)
    receivables = await db.receivables.find({}, {"_id": 0}).to_list(2000)

    def d(x):
        return datetime.fromisoformat(x["created_at"]).date()

    week_sales = [s for s in sales if start <= d(s) <= today]
    week_expenses = [e for e in expenses if start <= d(e) <= today]

    prev_start = start - timedelta(days=days)
    prev_end = start - timedelta(days=1)
    prev_sales = [s for s in sales if prev_start <= d(s) <= prev_end]
    prev_expenses = [e for e in expenses if prev_start <= d(e) <= prev_end]
    prev_revenue = sum(s["total"] for s in prev_sales)
    prev_expense = sum(e["total"] for e in prev_expenses)

    per_day = {}
    for s in week_sales:
        per_day[str(d(s))] = per_day.get(str(d(s)), 0) + s["total"]
    best_day = max(per_day.items(), key=lambda x: x[1]) if per_day else None
    outstanding = sum(r["amount"] - r.get("paid_amount", 0) for r in receivables if r["status"] != "lunas")

    data = _report_body(
        period, days, today, start, prev_start, prev_end, week_sales, week_expenses,
        prev_sales, prev_revenue, prev_expense, outstanding, best_day,
        top_selling_items(week_sales),
    )
    try:
        data["narrative"] = await nlu.generate_weekly(data)
    except Exception as e:
        logger.exception("weekly report failed")
        raise HTTPException(status_code=500, detail=f"Gagal membuat laporan: {e}")

    data["share_text"] = report_share_text(data, data["top_items"], outstanding, period)
    data["share_link"] = "https://wa.me/?text=" + quote(data["share_text"])
    return data


BULAN_ID = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def id_date(dt) -> str:
    return f"{dt.day} {BULAN_ID[dt.month - 1]}"


def pct_delta(now_v: float, prev_v: float) -> Optional[int]:
    if not prev_v:
        return None
    return round((now_v - prev_v) / prev_v * 100)


def top_selling_items(sales: List[dict], limit: int = 3) -> List[dict]:
    per_item: dict[str, dict] = {}
    for s in sales:
        for it in s.get("items", []):
            row = per_item.setdefault(it["name"], {"name": it["name"], "qty": 0, "revenue": 0})
            row["qty"] += it.get("qty") or 0
            row["revenue"] += it.get("subtotal") or (it.get("qty") or 1) * (it.get("unit_price") or 0)
    return sorted(per_item.values(), key=lambda x: x["revenue"], reverse=True)[:limit]


def expense_breakdown(expenses: List[dict], total_expense: float) -> List[dict]:
    per_cat: dict[str, float] = {}
    for e in expenses:
        cat = e.get("category") or "lainnya"
        per_cat[cat] = per_cat.get(cat, 0) + e["total"]
    return [
        {"category": k, "total": v, "pct": round(v / total_expense * 100) if total_expense else 0}
        for k, v in sorted(per_cat.items(), key=lambda x: x[1], reverse=True)
    ]


def report_share_text(data: dict, top_items: List[dict], outstanding: float, period: str) -> str:
    lines = [
        f"*Laporan VoiceBiz {'Bulanan' if period == 'monthly' else 'Mingguan'}* ({data['period']})",
        f"Pemasukan: {rupiah(data['revenue'])}",
        f"Pengeluaran: {rupiah(data['expense'])}",
        f"Laba: {rupiah(data['profit'])}",
        f"Transaksi: {data['transactions']} · Rata-rata/hari: {rupiah(data['avg_per_day'])}",
    ]
    cmp_ = data["comparison"]
    if cmp_["revenue_delta"] is not None:
        arah = "naik" if cmp_["revenue_delta"] >= 0 else "turun"
        lines.append(f"Omzet {arah} {abs(cmp_['revenue_delta'])}% dari {cmp_['label']} ({rupiah(cmp_['revenue'])})")
    if top_items:
        lines.append("Terlaris: " + ", ".join(f"{t['name']} ({int(t['qty'])})" for t in top_items))
    if outstanding:
        lines.append(f"Piutang belum tertagih: {rupiah(outstanding)}")
    lines += ["", data["narrative"]]
    return "\n".join(lines)


def _report_body(period: str, days: int, today, start, prev_start, prev_end,
                 week_sales: List[dict], week_expenses: List[dict], prev_sales: List[dict],
                 prev_revenue: float, prev_expense: float, outstanding: float,
                 best_day, top_items: List[dict]) -> dict:
    revenue = sum(s["total"] for s in week_sales)
    expense = sum(e["total"] for e in week_expenses)
    top_expenses = sorted(week_expenses, key=lambda x: x["total"], reverse=True)[:3]
    return {
        "period_type": period,
        "days": days,
        "period": f"{id_date(start)} – {id_date(today)} {today.year}",
        "revenue": revenue,
        "expense": expense,
        "profit": revenue - expense,
        "transactions": len(week_sales),
        "avg_per_day": round(revenue / days),
        "top_items": top_items,
        "best_day": {"date": best_day[0], "revenue": best_day[1]} if best_day else None,
        "outstanding_receivables": outstanding,
        "expense_breakdown": expense_breakdown(week_expenses, expense),
        "comparison": {
            "label": "7 hari sebelumnya" if days == 7 else "30 hari sebelumnya",
            "period": f"{id_date(prev_start)} – {id_date(prev_end)}",
            "revenue": prev_revenue,
            "expense": prev_expense,
            "profit": prev_revenue - prev_expense,
            "transactions": len(prev_sales),
            "revenue_delta": pct_delta(revenue, prev_revenue),
            "expense_delta": pct_delta(expense, prev_expense),
            "profit_delta": pct_delta(revenue - expense, prev_revenue - prev_expense),
        },
        "top_expenses": [{"title": e["title"], "total": e["total"], "category": e.get("category")}
                         for e in top_expenses],
    }


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


def _target_insight(rev_today: float, daily_target: float, target_remaining: float) -> dict:
    hour_wib = (datetime.now(timezone.utc) + timedelta(hours=7)).hour
    if target_remaining > 0:
        return {
            "type": "info", "icon": "target",
            "title": f"Sisa {rupiah(target_remaining)} untuk capai target hari ini",
            "body": f"Target {rupiah(daily_target)} · sudah {round(rev_today / daily_target * 100) if daily_target else 0}% tercapai.",
            "action": (
                "Masih ada waktu — tawarkan paket hemat ke pelanggan langganan lewat WhatsApp."
                if hour_wib < 16
                else "Sisa jam ramai malam: dorong menu terlaris dan bundling minuman."
            ),
        }
    return {
        "type": "good", "icon": "target",
        "title": "Target harian tercapai 🎉",
        "body": f"Omzet {rupiah(rev_today)} dari target {rupiah(daily_target)}.",
        "action": "Naikkan target besok sedikit agar usaha terus tumbuh.",
    }


def _trend_insight(rev_today: float, rev_yesterday: float) -> Optional[dict]:
    if rev_yesterday and rev_today < rev_yesterday * 0.7:
        drop = round((1 - rev_today / rev_yesterday) * 100)
        return {
            "type": "warning", "icon": "trending-down",
            "title": f"Penjualan turun {drop}% dari kemarin",
            "body": f"Hari ini {rupiah(rev_today)} vs kemarin {rupiah(rev_yesterday)}.",
            "action": "Broadcast promo di WhatsApp Status sore ini untuk menarik pembeli.",
        }
    if rev_yesterday and rev_today > rev_yesterday:
        return {
            "type": "good", "icon": "trending-up",
            "title": "Penjualan naik dari kemarin",
            "body": f"Hari ini {rupiah(rev_today)} vs kemarin {rupiah(rev_yesterday)}.",
            "action": "Siapkan stok bahan favorit agar tidak kehabisan besok.",
        }
    return None


def build_insights(rev_today: float, rev_yesterday: float, daily_target: float, target_remaining: float,
                   outstanding_list: List[dict], low_stock: List[dict], inactive: List[dict]) -> List[dict]:
    insights = [_target_insight(rev_today, daily_target, target_remaining)]
    trend = _trend_insight(rev_today, rev_yesterday)
    if trend:
        insights.append(trend)
    if outstanding_list:
        top = max(outstanding_list, key=lambda x: x["remaining"])
        insights.append({
            "type": "warning", "icon": "hand-coins",
            "title": f"Piutang belum tertagih {rupiah(sum(r['remaining'] for r in outstanding_list))}",
            "body": f"Terbesar: {top['customer_name']} {rupiah(top['remaining'])}.",
            "action": f"Kirim pengingat sopan ke {top['customer_name']} hari ini.",
        })
    if low_stock:
        insights.append({
            "type": "danger", "icon": "package-x",
            "title": f"{len(low_stock)} bahan hampir habis",
            "body": ", ".join(f"{i['name']} (sisa {int(i['qty'])} {i['unit']})" for i in low_stock[:3]),
            "action": "Belanja bahan ini sebelum jam sibuk sore.",
        })
    if inactive:
        insights.append({
            "type": "info", "icon": "user-round-x",
            "title": f"{len(inactive)} pelanggan lama tidak kembali",
            "body": ", ".join(c["name"] for c in inactive[:3]),
            "action": "Tawarkan diskon 10% lewat chat pribadi untuk mengaktifkan mereka.",
        })
    return insights


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

    settings = await get_settings_doc()
    daily_target = float(settings.get("daily_target", 300000))
    target_remaining = max(0, daily_target - rev_today)
    insights = build_insights(rev_today, rev_yesterday, daily_target, target_remaining,
                              outstanding_list, low_stock, inactive)

    return {
        "date": str(today),
        "revenue_today": rev_today,
        "expense_today": exp_today,
        "profit_today": rev_today - exp_today,
        "revenue_yesterday": rev_yesterday,
        "daily_target": daily_target,
        "target_remaining": target_remaining,
        "target_progress": round(min(100, rev_today / daily_target * 100)) if daily_target else 0,
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
    async with _reset_lock:
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
