import random
from datetime import datetime, timezone, timedelta


def _iso(days_ago: int = 0, hour: int = 10) -> str:
    d = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return d.replace(hour=hour % 24, minute=15, second=0, microsecond=0).isoformat()


MENU = [
    ("Nasi Goreng Spesial", 20000),
    ("Ayam Geprek", 22000),
    ("Es Teh Manis", 5000),
    ("Es Jeruk", 6000),
    ("Paket Nasi Box", 25000),
    ("Mie Goreng Jawa", 18000),
]

BAHAN = [
    ("Beras", "kg", 13000, "bahan baku"),
    ("Ayam potong", "kg", 35000, "bahan baku"),
    ("Telur", "kg", 28000, "bahan baku"),
    ("Minyak goreng", "liter", 18000, "bahan baku"),
    ("Sayur & bumbu", "paket", 42000, "bahan baku"),
    ("Gas LPG", "tabung", 22000, "operasional"),
]


def demo_data() -> dict:
    rnd = random.Random(7)
    sales = []
    expenses = []

    # 60 hari riwayat agar tren, perbandingan periode (7 & 30 hari), dan riwayat belanja terasa hidup
    for days_ago in range(59, -1, -1):
        weekend = (datetime.now(timezone.utc) - timedelta(days=days_ago)).weekday() >= 5
        n_trx = rnd.randint(2, 4) if weekend else rnd.randint(1, 3)
        if days_ago == 0:
            n_trx = 2
        for i in range(n_trx):
            name, price = rnd.choice(MENU)
            qty = rnd.randint(2, 9 if weekend else 6)
            customer = rnd.choice([None, None, "Bu Ani", "Pak Budi", "Mbak Rina"])
            sales.append({
                "items": [{"name": name, "qty": qty, "unit": "porsi", "unit_price": price,
                           "subtotal": qty * price}],
                "total": qty * price,
                "customer_name": customer,
                "note": "Pesanan WhatsApp" if customer else None,
                "created_at": _iso(days_ago, 8 + i * 4),
            })
        if days_ago % 3 == 0 or days_ago == 0:
            bahan, unit, harga, kategori = rnd.choice(BAHAN)
            qty = rnd.randint(2, 6)
            harga_hari_ini = harga + rnd.choice([-1500, 0, 0, 1500, 3000])
            expenses.append({
                "title": f"{bahan} {qty} {unit}",
                "total": qty * harga_hari_ini,
                "category": kategori,
                "note": "Toko Pak Slamet",
                "items": [{"name": bahan, "qty": qty, "unit": unit,
                           "unit_price": harga_hari_ini, "subtotal": qty * harga_hari_ini}],
                "created_at": _iso(days_ago, 7),
            })

    expenses.append({
        "title": "Listrik & air", "total": 145000, "category": "operasional",
        "note": "Tagihan bulanan", "items": [], "created_at": _iso(4, 9),
    })

    customers = [
        {"name": "Pak Budi", "phone": "0812-1111-2222", "note": "Langganan nasi box kantor", "last_active": _iso(2), "created_at": _iso(60)},
        {"name": "Bu Ani", "phone": "0813-3333-4444", "note": "Sering pesan untuk pengajian", "last_active": _iso(0), "created_at": _iso(70)},
        {"name": "Mbak Rina", "phone": "0857-5555-6666", "note": "Reseller ayam geprek", "last_active": _iso(1), "created_at": _iso(40)},
        {"name": "Mas Joko", "phone": "0878-7777-8888", "note": "Pelanggan ojol", "last_active": _iso(22), "created_at": _iso(80)},
    ]
    receivables = [
        {"customer_name": "Pak Budi", "amount": 150000, "paid_amount": 0, "status": "belum_lunas",
         "note": "Nasi box acara kantor minggu lalu", "created_at": _iso(7)},
        {"customer_name": "Mbak Rina", "amount": 90000, "paid_amount": 40000, "status": "belum_lunas",
         "note": "Kasbon ayam geprek", "created_at": _iso(3)},
        {"customer_name": "Mas Joko", "amount": 35000, "paid_amount": 35000, "status": "lunas",
         "note": None, "created_at": _iso(12)},
    ]
    inventory = [
        {"name": "Beras", "qty": 12, "unit": "kg", "min_qty": 10, "updated_at": _iso(0)},
        {"name": "Ayam potong", "qty": 2, "unit": "kg", "min_qty": 5, "updated_at": _iso(0)},
        {"name": "Telur", "qty": 3, "unit": "kg", "min_qty": 4, "updated_at": _iso(1)},
        {"name": "Gas LPG", "qty": 1, "unit": "tabung", "min_qty": 2, "updated_at": _iso(2)},
        {"name": "Es batu", "qty": 20, "unit": "balok", "min_qty": 5, "updated_at": _iso(0)},
        {"name": "Minyak goreng", "qty": 8, "unit": "liter", "min_qty": 4, "updated_at": _iso(1)},
    ]
    activities = [
        {"kind": "sale", "text": "Penjualan hari ini tercatat", "created_at": _iso(0, 8)},
        {"kind": "receivable", "text": "Piutang Pak Budi — Rp150.000", "created_at": _iso(7)},
    ]
    return {
        "sales": sales,
        "expenses": expenses,
        "customers": customers,
        "receivables": receivables,
        "inventory": inventory,
        "activities": activities,
    }
