# VoiceBiz — PRD

## Problem Statement (asli)
Bangun web app full-stack "VoiceBiz": asisten bisnis AI untuk pemilik usaha mikro & social-commerce Indonesia. Prinsip: "Talk to your business. Get things done." Pengguna bicara/menulis bahasa Indonesia informal (mis. "Hari ini saya jual dua nasi goreng dan tiga es teh, total 87 ribu") → AI memahami intent, mengekstrak data bisnis, menyimpannya sebagai data terstruktur. 3 pilar MVP: (1) Talk to VoiceBiz (voice + fallback teks, konfirmasi sebelum simpan), (2) Business Memory (penjualan, pengeluaran, pelanggan, piutang, stok), (3) AI Business Brief (dashboard hari ini + insight + rekomendasi tindakan). Mobile-first, premium, data demo Indonesia.

## User choices
- Model NLU: OpenAI `gpt-5.6-luna` via EMERGENT_LLM_KEY
- Voice: OpenAI `whisper-1` (bahasa `id`)
- Tanpa autentikasi (single demo user)
- UI 100% Bahasa Indonesia
- Desain diserahkan ke design agent (Organic & Earthy: Warm Sand / Deep Forest / Terracotta, Manrope + DM Sans)

## Arsitektur
- Backend: FastAPI (`/app/backend/server.py`), NLU layer (`nlu.py`), demo seed (`seed.py`), MongoDB via MONGO_URL
- Frontend: React (CRA) mobile container max-w-md, Tailwind custom palette, shadcn UI, sonner toast
- Endpoint: `POST /api/voice/transcribe`, `POST /api/nlu/parse`, `POST /api/nlu/commit`, `GET /api/dashboard`, `GET /api/memory`, `GET /api/brief`, `POST /api/demo/reset`

## Sudah diimplementasikan (2026-06)
- Tap to Talk: rekam mic (MediaRecorder) → Whisper → NLU; fallback input teks + contoh chip
- Confirmation sheet: judul intent, item, total, tombol Simpan/Edit (edit total & nama pelanggan)
- Intent didukung: sale, expense, receivable, receivable_payment, inventory, customer, question
- Business Memory: 5 tab (Jual, Biaya, Piutang, Stok, Pelanggan) dari data nyata
- Penjualan otomatis mengurangi stok; pembayaran utang mengurangi sisa piutang
- Dashboard: pendapatan/pengeluaran/laba hari ini, delta vs kemarin, tren 7 hari, aktivitas terbaru
- Insight + rekomendasi tindakan: penjualan turun, piutang tertagih, stok rendah, pelanggan tidak aktif
- Briefing AI harian (LLM, grounded pada data nyata)
- Data demo warung Indonesia + tombol reset demo
- Testing agent: backend 12/12 PASS, frontend semua alur inti PASS

## Backlog
### P0
- Riwayat percakapan (chat log) tersimpan agar pengguna bisa lihat ulang perintah
- Koreksi/hapus transaksi salah dari Memori
### P1
- Multi-item edit di confirmation sheet (ubah qty/harga per item)
- Laporan mingguan/bulanan + ekspor WhatsApp/PDF
- Reminder tagih utang otomatis (template pesan WhatsApp)
### P2
- Autentikasi & multi-warung
- Grafik kategori pengeluaran, target harian
- PWA install + offline queue

## Next tasks
1. Riwayat percakapan + undo transaksi
2. Template pesan penagihan WhatsApp dari insight piutang
3. Laporan mingguan yang bisa dibagikan
