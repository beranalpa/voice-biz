from datetime import datetime, timezone, timedelta


def _iso(days_ago=0, hour=10):
    d = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return d.replace(hour=hour % 24, minute=15, second=0, microsecond=0).isoformat()


def demo_data():
    sales = [
        {"items": [{"name": "Nasi Goreng Spesial", "qty": 3, "unit_price": 20000, "subtotal": 60000}], "total": 60000, "customer_name": "Bu Ani", "note": "Pesanan pagi", "created_at": _iso(0, 8)},
        {"items": [{"name": "Es Teh Manis", "qty": 6, "unit_price": 5000, "subtotal": 30000}], "total": 30000, "customer_name": None, "note": "Pembeli lewat", "created_at": _iso(0, 9)},
        {"items": [{"name": "Ayam Geprek", "qty": 4, "unit_price": 22000, "subtotal": 88000}], "total": 88000, "customer_name": "Mbak Rina", "note": "Order via WhatsApp", "created_at": _iso(1, 12)},
        {"items": [{"name": "Nasi Goreng Spesial", "qty": 5, "unit_price": 20000, "subtotal": 100000}], "total": 100000, "customer_name": None, "note": None, "created_at": _iso(1, 18)},
        {"items": [{"name": "Paket Nasi Box", "qty": 10, "unit_price": 25000, "subtotal": 250000}], "total": 250000, "customer_name": "Pak Budi", "note": "Acara kantor", "created_at": _iso(2, 11)},
        {"items": [{"name": "Es Jeruk", "qty": 8, "unit_price": 6000, "subtotal": 48000}], "total": 48000, "customer_name": None, "note": None, "created_at": _iso(3, 15)},
        {"items": [{"name": "Ayam Geprek", "qty": 6, "unit_price": 22000, "subtotal": 132000}], "total": 132000, "customer_name": "Mbak Rina", "note": None, "created_at": _iso(4, 13)},
        {"items": [{"name": "Nasi Goreng Spesial", "qty": 9, "unit_price": 20000, "subtotal": 180000}], "total": 180000, "customer_name": None, "note": "Hari ramai", "created_at": _iso(5, 19)},
        {"items": [{"name": "Paket Nasi Box", "qty": 8, "unit_price": 25000, "subtotal": 200000}], "total": 200000, "customer_name": "Bu Ani", "note": "Pengajian RT", "created_at": _iso(6, 10)},
    ]
    expenses = [
        {"title": "Beras 10 kg", "total": 130000, "category": "bahan baku", "note": "Toko Pak Slamet", "created_at": _iso(0, 7)},
        {"title": "Ayam potong 5 kg", "total": 175000, "category": "bahan baku", "note": None, "created_at": _iso(1, 7)},
        {"title": "Gas LPG 3 kg", "total": 22000, "category": "operasional", "note": None, "created_at": _iso(2, 8)},
        {"title": "Listrik & air", "total": 145000, "category": "operasional", "note": "Tagihan bulanan", "created_at": _iso(4, 9)},
        {"title": "Sayur & bumbu", "total": 85000, "category": "bahan baku", "note": "Pasar pagi", "created_at": _iso(5, 6)},
    ]
    customers = [
        {"name": "Pak Budi", "phone": "0812-1111-2222", "note": "Langganan nasi box kantor", "last_active": _iso(2), "created_at": _iso(30)},
        {"name": "Bu Ani", "phone": "0813-3333-4444", "note": "Sering pesan untuk pengajian", "last_active": _iso(0), "created_at": _iso(45)},
        {"name": "Mbak Rina", "phone": "0857-5555-6666", "note": "Reseller ayam geprek", "last_active": _iso(1), "created_at": _iso(20)},
        {"name": "Mas Joko", "phone": "0878-7777-8888", "note": "Pelanggan ojol", "last_active": _iso(22), "created_at": _iso(60)},
    ]
    receivables = [
        {"customer_name": "Pak Budi", "amount": 150000, "paid_amount": 0, "status": "belum_lunas", "note": "Nasi box acara kantor minggu lalu", "created_at": _iso(7)},
        {"customer_name": "Mbak Rina", "amount": 90000, "paid_amount": 40000, "status": "belum_lunas", "note": "Kasbon ayam geprek", "created_at": _iso(3)},
        {"customer_name": "Mas Joko", "amount": 35000, "paid_amount": 35000, "status": "lunas", "note": None, "created_at": _iso(12)},
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
        {"kind": "sale", "text": "Penjualan 3 Nasi Goreng Spesial — Rp60.000", "created_at": _iso(0, 8)},
        {"kind": "expense", "text": "Pengeluaran beras 10 kg — Rp130.000", "created_at": _iso(0, 7)},
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
