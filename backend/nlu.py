import json
import os
import re
import uuid
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

MODEL_PROVIDER = "openai"
MODEL_NAME = "gpt-5.6-luna"

SYSTEM_PROMPT = """Kamu adalah mesin pemahaman bahasa (NLU) untuk VoiceBiz, asisten bisnis AI untuk pemilik usaha mikro Indonesia (warung, jualan online).

Tugasmu: mengubah ucapan/tulisan informal berbahasa Indonesia menjadi data bisnis terstruktur.

Balas HANYA dengan JSON valid (tanpa markdown, tanpa penjelasan) dengan bentuk:
{
  "intent": "sale" | "expense" | "receivable" | "receivable_payment" | "inventory" | "customer" | "question" | "correction" | "unknown",
  "title": "judul singkat Bahasa Indonesia, contoh: 'Penjualan baru terdeteksi'",
  "summary": "1 kalimat ringkas apa yang kamu pahami",
  "confidence": 0.0-1.0,
  "items": [{"name": "nasi goreng", "qty": 2, "unit_price": 20000, "subtotal": 40000}],
  "total": 87000,
  "customer_name": "Pak Budi" | null,
  "category": "bahan baku" | "operasional" | null,
  "note": "catatan tambahan" | null,
  "due_note": "minggu lalu" | null,
  "question": "pertanyaan pengguna kalau intent question" | null
}

Aturan angka Indonesia (WAJIB, dalam Rupiah bulat):
- "87 ribu" = 87000, "150rb" = 150000, "1,5 juta" = 1500000, "20k" = 20000, "dua ratus lima puluh ribu" = 250000.
- Kalau hanya total disebut dan ada beberapa item tanpa harga masing-masing, isi total saja dan biarkan unit_price null.
- Kalau qty tidak disebut, anggap 1.

Aturan intent:
- "sale": penjualan/laku/terjual/dibeli pelanggan.
- "expense": belanja, bayar, beli bahan, modal, gaji, sewa, listrik.
- "receivable": pelanggan berhutang / kasbon / belum bayar / utang.
- "receivable_payment": pelanggan melunasi / sudah bayar utang.
- "inventory": stok masuk/tambah stok/sisa stok barang.
- "customer": info pelanggan baru tanpa transaksi.
- "question": pertanyaan tentang bisnis (contoh: "berapa untung hari ini?", "siapa yang masih ngutang?").
- "correction": pengguna memperbaiki catatan terakhir, misalnya "salah, itu 50 ribu", "bukan 87 ribu tapi 97 ribu", "harusnya nasi goreng bukan mie goreng", "ganti nama jadi Bu Ani". Isi `total` dengan nilai BENAR yang baru (kalau disebut), `items` dengan satu item nama yang benar (kalau disebut), `customer_name` dengan nama yang benar (kalau disebut). Judul: "Koreksi catatan terakhir".
- Field yang tidak relevan isi null atau [].
"""

ANSWER_PROMPT = """Kamu adalah penasihat bisnis VoiceBiz untuk pemilik usaha mikro Indonesia.
Jawab pertanyaan pemilik usaha HANYA berdasarkan data bisnis JSON yang diberikan.
Jawab dalam Bahasa Indonesia yang santai, singkat (maks 3 kalimat), sebut angka Rupiah dengan format Rp1.234.000.
Selalu tutup dengan satu saran tindakan konkret."""


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError(f"LLM tidak mengembalikan JSON: {text[:200]}")
    return json.loads(match.group(0))


def _chat(system_message: str) -> LlmChat:
    return LlmChat(
        api_key=os.environ["EMERGENT_LLM_KEY"],
        session_id=f"voicebiz-{uuid.uuid4()}",
        system_message=system_message,
    ).with_model(MODEL_PROVIDER, MODEL_NAME)


async def parse_text(text: str) -> dict:
    chat = _chat(SYSTEM_PROMPT)
    resp = await chat.send_message(UserMessage(text=text))
    data = _extract_json(resp if isinstance(resp, str) else str(resp))
    data.setdefault("items", [])
    data.setdefault("intent", "unknown")
    data.setdefault("confidence", 0.5)
    return data


async def answer_question(question: str, context: dict) -> str:
    chat = _chat(ANSWER_PROMPT)
    payload = f"DATA BISNIS:\n{json.dumps(context, ensure_ascii=False, default=str)}\n\nPERTANYAAN: {question}"
    resp = await chat.send_message(UserMessage(text=payload))
    return resp if isinstance(resp, str) else str(resp)


async def parse_receipt(image_b64: str) -> dict:
    chat = _chat(
        "Kamu membaca foto nota/struk belanja pemilik warung Indonesia (tulisan tangan atau cetak).\n"
        "Ekstrak pengeluaran dari gambar. Balas HANYA JSON:\n"
        '{"title":"nama toko atau ringkasan belanja","items":[{"name":"beras","qty":2,"unit_price":65000,'
        '"subtotal":130000}],"total":195000,"category":"bahan baku"|"operasional"|"lainnya",'
        '"note":"catatan singkat","confidence":0.0-1.0}\n'
        "Semua nominal dalam Rupiah bulat tanpa titik. Kalau total tidak terbaca, jumlahkan subtotal item. "
        "Kalau gambar bukan nota, balas {\"total\":0,\"items\":[],\"confidence\":0}."
    )
    resp = await chat.send_message(
        UserMessage(text="Bacakan nota ini menjadi data pengeluaran.", file_contents=[ImageContent(image_base64=image_b64)])
    )
    return _extract_json(resp if isinstance(resp, str) else str(resp))


async def generate_reminders(receivables: list) -> list:
    chat = _chat(
        "Kamu membantu pemilik warung Indonesia menagih utang pelanggan dengan sopan dan menjaga hubungan baik.\n"
        "Untuk setiap pelanggan, tulis satu pesan WhatsApp Bahasa Indonesia: ramah, hormat, maksimal 2 kalimat, "
        "sebut nominal dengan format Rp150.000, sertakan sapaan sesuai nama, boleh 1 emoji 🙏, jangan mengancam, "
        "dan tawarkan opsi bayar bertahap kalau utang sudah lebih dari 7 hari.\n"
        'Balas HANYA JSON: {"reminders":[{"customer_name":"...","message":"..."}]}'
    )
    resp = await chat.send_message(UserMessage(text=json.dumps(receivables, ensure_ascii=False)))
    data = _extract_json(resp if isinstance(resp, str) else str(resp))
    return data.get("reminders", [])


async def generate_weekly(report: dict) -> str:
    chat = _chat(
        "Kamu penasihat bisnis VoiceBiz. Dari data laporan mingguan JSON, tulis ringkasan Bahasa Indonesia "
        "yang mudah dipahami keluarga atau pemberi modal: maksimal 3 kalimat, sebut angka Rupiah format Rp1.234.000, "
        "sebut menu terlaris, dan tutup dengan satu rekomendasi untuk minggu depan. Tanpa markdown."
    )
    resp = await chat.send_message(UserMessage(text=json.dumps(report, ensure_ascii=False, default=str)))
    return resp if isinstance(resp, str) else str(resp)


async def generate_advice(context: dict) -> str:
    chat = _chat(
        "Kamu penasihat bisnis VoiceBiz. Berdasarkan data JSON, tulis 1 paragraf briefing harian "
        "Bahasa Indonesia (maks 45 kata) untuk pemilik warung: kondisi hari ini + 1 tindakan prioritas hari ini."
    )
    resp = await chat.send_message(UserMessage(text=json.dumps(context, ensure_ascii=False, default=str)))
    return resp if isinstance(resp, str) else str(resp)
