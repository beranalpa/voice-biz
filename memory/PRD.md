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

## Sudah diimplementasikan (2026-06)- Tap to Talk: rekam mic (MediaRecorder) → Whisper → NLU; fallback input teks + contoh chip
- Confirmation sheet: judul intent, item, total, tombol Simpan/Edit (edit total & nama pelanggan)
- Intent didukung: sale, expense, receivable, receivable_payment, inventory, customer, question
- Business Memory: 5 tab (Jual, Biaya, Piutang, Stok, Pelanggan) dari data nyata
- Penjualan otomatis mengurangi stok; pembayaran utang mengurangi sisa piutang
- Dashboard: pendapatan/pengeluaran/laba hari ini, delta vs kemarin, tren 7 hari, aktivitas terbaru
- Insight + rekomendasi tindakan: penjualan turun, piutang tertagih, stok rendah, pelanggan tidak aktif
- Briefing AI harian (LLM, grounded pada data nyata)
- Data demo warung Indonesia + tombol reset demo
- Testing agent: backend 12/12 PASS, frontend semua alur inti PASS

### Iterasi 2 (2026-06)
- **Riwayat & Undo**: setiap commit tercatat di koleksi `history` beserta operasi balikan (`ops`); `POST /api/history/{id}/undo` mengembalikan stok, piutang, penjualan, pengeluaran, pelanggan, dan aktivitas ke kondisi sebelumnya. Feed riwayat percakapan di Beranda dengan tombol Batalkan.
- **Tagih via WhatsApp**: `GET /api/receivables/reminders` membuat pesan penagihan sopan (LLM) per pelanggan yang masih berutang + `wa.me` deep link; UI sheet di tab Piutang (Kirim WhatsApp / Salin).
- **Laporan Mingguan**: `GET /api/reports/weekly` (omzet, biaya, laba, rata-rata/hari, menu terlaris, hari terbaik, piutang, narasi LLM, `share_text` + `share_link`); tab Laporan dengan tombol Bagikan & Salin.
- **Mode Demo Juri**: tur 7 babak sekali klik (tombol "Demo" di header) yang memainkan perintah suara paling mengesankan, menyimpan otomatis, mendemokan Undo, pesan penagihan WhatsApp, laporan mingguan, lalu jawaban laba dari data nyata. Bisa dijeda/lanjut manual, dan reset data demo di awal.

### Iterasi 3 (2026-06)
- **Tandai Sudah Ditagih**: `POST /api/receivables/{id}/reminded` menyimpan `last_reminded_at`; endpoint reminders mengembalikan `reminded_today`, UI menampilkan badge "Sudah ditagih hari ini", chip bertanda ✓, dan tombol berubah jadi "Kirim lagi". Menandai otomatis saat Kirim/Salin.
- **Target Harian**: koleksi `settings` (`daily_target`, default Rp300.000) + `GET/PUT /api/settings`; dashboard mengirim `daily_target`, `target_remaining`, `target_progress`; kartu Target di Beranda (progress bar, sisa kejar, ubah target inline) dan insight khusus yang menyesuaikan saran berdasarkan jam (WIB).
- **Laporan Bulanan**: `GET /api/reports/weekly?period=weekly|monthly` (7 vs 30 hari, rata-rata per hari mengikuti periode, judul share text menyesuaikan); toggle "7 hari / 30 hari" di tab Laporan.
- **Koreksi Lewat Suara**: intent `correction` di NLU ("salah, itu 50 ribu"); `POST /api/nlu/correct` membatalkan catatan terakhir (pakai `draft` yang tersimpan di history) lalu mencatat ulang dengan nilai/nama/item yang benar, tercatat sebagai "Dikoreksi → …". Tersedia sebagai chip contoh di Tap to Talk dan satu babak baru di Mode Demo Juri (total 8 babak).

### Iterasi 4 (2026-06)
- **Target Otomatis**: `GET /api/settings/suggest-target` menghitung rata-rata omzet 30 hari (hari aktif) dan menyarankan target 10% di atasnya (dibulatkan Rp5.000); kartu Target menampilkan alasan + tombol "Pakai saran".
- **Grafik Pengeluaran**: laporan mengirim `expense_breakdown` (per kategori + persentase) dan `top_expenses`; ditampilkan sebagai bar di tab Laporan ("Ke mana uang pergi") mengikuti periode 7/30 hari.
- **Pengingat Belanja**: `GET /api/shopping-list` (bahan di bawah stok minimum + jumlah yang perlu dibeli + teks siap salin/WA) dan `POST /api/inventory/{id}/restock` yang tercatat di history sehingga bisa di-undo. Kartu "Belanja sebelum jam sibuk" di Beranda dengan tombol "Sudah beli".
- **Catat Lewat Foto**: `POST /api/expenses/from-receipt` — foto nota di-resize (Pillow) lalu dibaca `gpt-5.6-luna` (vision, ImageContent) menjadi draft pengeluaran (item, qty, harga, total, kategori) yang muncul di kartu konfirmasi. Tombol kamera di panel Tap to Talk.

## Backlog
### P0
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
