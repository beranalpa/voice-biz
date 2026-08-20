"""VoiceBiz backend integration tests (pytest).

Single module (loadscope => single xdist worker) because all tests share one
preview backend and mutate demo state sequentially.
"""
import io
import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
                break
assert BASE_URL, "REACT_APP_BACKEND_URL missing"
API = f"{BASE_URL}/api"
T = 40
LLM_T = 120


@pytest.fixture(scope="module", autouse=True)
def reset_before_all():
    r = requests.post(f"{API}/demo/reset", timeout=60)
    assert r.status_code == 200


def _dashboard():
    return requests.get(f"{API}/dashboard", timeout=T).json()


def _memory():
    return requests.get(f"{API}/memory", timeout=T).json()


def _inv(name):
    return next((i for i in _memory()["inventory"] if i["name"].lower() == name.lower()), None)


def _commit(payload):
    r = requests.post(f"{API}/nlu/commit", json=payload, timeout=T)
    assert r.status_code == 200, r.text
    return r.json()


def _undo(hid):
    r = requests.post(f"{API}/history/{hid}/undo", timeout=T)
    assert r.status_code == 200, r.text
    return r.json()


# ---------- basics ----------
def test_root():
    r = requests.get(f"{API}/", timeout=T)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_demo_reset_dataset_60_days():
    m = _memory()
    for k in ["sales", "expenses", "customers", "receivables", "inventory"]:
        assert len(m[k]) > 0, f"{k} not seeded"
    # sales list is capped at 100 docs by design; use expenses (unique per 3 days over 60d)
    assert len(m["customers"]) == 4, m["customers"]
    assert len(m["inventory"]) == 6, m["inventory"]
    assert len(m["receivables"]) == 3, m["receivables"]
    exp_days = {e["created_at"][:10] for e in m["expenses"]}
    assert max(exp_days) and min(exp_days)
    from datetime import datetime
    span = (datetime.fromisoformat(max(exp_days)) - datetime.fromisoformat(min(exp_days))).days
    assert span >= 50, f"expected ~60 days seed span, got {span}"
    assert any(e.get("items") for e in m["expenses"]), "expenses have no items"
    assert "Pak Budi" in [c["name"] for c in m["customers"]]


# ---------- FIX 1b: concurrent resets must not duplicate ----------
def test_concurrent_demo_resets_do_not_duplicate():
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=5) as ex:
        results = list(ex.map(lambda _: requests.post(f"{API}/demo/reset", timeout=90), range(5)))
    assert all(r.status_code == 200 for r in results), [r.status_code for r in results]
    m = _memory()
    assert len(m["customers"]) == 4, f"duplicated customers: {len(m['customers'])}"
    assert len(m["inventory"]) == 6, f"duplicated inventory: {len(m['inventory'])}"
    assert len(m["receivables"]) == 3, f"duplicated receivables: {len(m['receivables'])}"
    # no duplicate inventory names
    names = [i["name"] for i in m["inventory"]]
    assert len(names) == len(set(names)), names


# ---------- dashboard ----------
def test_dashboard_shape():
    d = _dashboard()
    for k in ["revenue_today", "expense_today", "profit_today", "daily_target",
              "target_remaining", "target_progress", "trend", "insights", "activities"]:
        assert k in d, k
    assert len(d["trend"]) == 7
    assert d["insights"], "no insights"
    assert d["insights"][0]["icon"] == "target", "first insight must be daily-target"
    for i in d["insights"]:
        assert i.get("action"), f"insight missing action: {i}"
    assert isinstance(d["activities"], list)
    assert all("_id" not in a for a in d["activities"])


# ---------- commit: sale ----------
def test_commit_sale_decrements_inventory_no_new_docs_and_undo():
    before_rev = _dashboard()["revenue_today"]
    ayam_before = _inv("Ayam potong")
    assert ayam_before is not None
    inv_count_before = len(_memory()["inventory"])

    res = _commit({
        "intent": "sale",
        "items": [
            {"name": "Ayam potong", "qty": 1, "unit_price": 25000, "subtotal": 25000},
            {"name": "Nasi Goreng Spesial", "qty": 2, "unit_price": 20000, "subtotal": 40000},
        ],
        "total": 65000,
        "raw_text": "TEST_sale",
    })
    hid = res["history_id"]

    after = _dashboard()
    assert after["revenue_today"] == before_rev + 65000
    mem = _memory()
    ayam_after = next(i for i in mem["inventory"] if i["name"].lower() == "ayam potong")
    assert ayam_after["qty"] == max(0, ayam_before["qty"] - 1)
    # menu item must NOT create an inventory doc
    assert not any(i["name"].lower() == "nasi goreng spesial" for i in mem["inventory"]), \
        "sale created inventory doc for menu item"
    assert len(mem["inventory"]) == inv_count_before

    _undo(hid)
    d = _dashboard()
    assert d["revenue_today"] == before_rev
    assert _inv("Ayam potong")["qty"] == ayam_before["qty"]


# ---------- commit: expense ----------
def test_commit_expense_add_to_inventory_true_and_undo():
    before_exp = _dashboard()["expense_today"]
    telur_before = _inv("Telur")
    assert telur_before is not None
    res = _commit({
        "intent": "expense",
        "items": [{"name": "Telur", "qty": 2, "unit": "kg", "unit_price": 28000, "subtotal": 56000}],
        "total": 56000,
        "category": "bahan baku",
        "add_to_inventory": True,
        "raw_text": "TEST_expense_add",
    })
    assert "stok" in res["message"].lower()
    assert _dashboard()["expense_today"] == before_exp + 56000
    assert _inv("Telur")["qty"] == telur_before["qty"] + 2

    _undo(res["history_id"])
    assert _dashboard()["expense_today"] == before_exp
    assert _inv("Telur")["qty"] == telur_before["qty"]


def test_commit_expense_add_to_inventory_creates_new_ingredient():
    name = "TEST_Kecap"
    assert _inv(name) is None
    res = _commit({
        "intent": "expense",
        "items": [{"name": name, "qty": 3, "unit": "botol", "unit_price": 10000, "subtotal": 30000}],
        "total": 30000,
        "add_to_inventory": True,
        "raw_text": "TEST_expense_new",
    })
    created = _inv(name)
    assert created is not None and created["qty"] == 3 and created["unit"] == "botol"
    _undo(res["history_id"])
    assert _inv(name) is None


def test_commit_expense_add_to_inventory_false_does_not_touch_stock():
    before_exp = _dashboard()["expense_today"]
    telur_before = _inv("Telur")["qty"]
    res = _commit({
        "intent": "expense",
        "items": [{"name": "Telur", "qty": 5, "unit": "kg", "unit_price": 28000, "subtotal": 140000}],
        "total": 140000,
        "add_to_inventory": False,
        "raw_text": "TEST_expense_noinv",
    })
    assert _inv("Telur")["qty"] == telur_before
    assert _dashboard()["expense_today"] == before_exp + 140000
    _undo(res["history_id"])
    assert _dashboard()["expense_today"] == before_exp


# ---------- commit: receivable / payment ----------
def test_commit_receivable_and_payment_and_undo():
    before_out = _dashboard()["outstanding_receivables"]
    res = _commit({"intent": "receivable", "customer_name": "TEST_Bu Sari",
                   "total": 80000, "raw_text": "TEST_receivable"})
    assert _dashboard()["outstanding_receivables"] == before_out + 80000
    rec = next(r for r in _memory()["receivables"] if r["customer_name"] == "TEST_Bu Sari")
    assert rec["amount"] == 80000 and rec["status"] == "belum_lunas"

    pay = _commit({"intent": "receivable_payment", "customer_name": "TEST_Bu Sari",
                   "total": 30000, "raw_text": "TEST_payment"})
    rec2 = next(r for r in _memory()["receivables"] if r["customer_name"] == "TEST_Bu Sari")
    assert rec2["paid_amount"] == 30000
    assert rec2["amount"] - rec2["paid_amount"] == 50000

    _undo(pay["history_id"])
    rec3 = next(r for r in _memory()["receivables"] if r["customer_name"] == "TEST_Bu Sari")
    assert rec3.get("paid_amount", 0) == 0 and rec3["status"] == "belum_lunas"

    _undo(res["history_id"])
    assert not any(r["customer_name"] == "TEST_Bu Sari" for r in _memory()["receivables"])
    assert _dashboard()["outstanding_receivables"] == before_out


def test_receivable_payment_unknown_customer_404():
    r = requests.post(f"{API}/nlu/commit", json={"intent": "receivable_payment",
                                                 "customer_name": "TEST_NoBody", "total": 1000}, timeout=T)
    assert r.status_code == 404, r.text


def test_commit_unknown_intent_400():
    r = requests.post(f"{API}/nlu/commit", json={"intent": "banana", "total": 1}, timeout=T)
    assert r.status_code == 400


# ---------- commit: inventory (absolute) / customer ----------
def test_commit_inventory_absolute_and_undo():
    beras_before = _inv("Beras")["qty"]
    res = _commit({"intent": "inventory",
                   "items": [{"name": "Beras", "qty": 40, "unit": "kg"}],
                   "raw_text": "TEST_inventory"})
    assert _inv("Beras")["qty"] == 40
    _undo(res["history_id"])
    assert _inv("Beras")["qty"] == beras_before


def test_commit_customer_and_undo():
    res = _commit({"intent": "customer", "customer_name": "TEST_Pak Rudi",
                   "note": "langganan", "raw_text": "TEST_customer"})
    assert any(c["name"] == "TEST_Pak Rudi" for c in _memory()["customers"])
    _undo(res["history_id"])
    assert not any(c["name"] == "TEST_Pak Rudi" for c in _memory()["customers"])


def test_undo_twice_rejected():
    res = _commit({"intent": "customer", "customer_name": "TEST_Undo2", "raw_text": "TEST_undo2"})
    _undo(res["history_id"])
    r = requests.post(f"{API}/history/{res['history_id']}/undo", timeout=T)
    assert r.status_code == 400
    r2 = requests.post(f"{API}/history/not-an-id/undo", timeout=T)
    assert r2.status_code == 400


# ---------- correction ----------
def test_correct_last_sale_87k_to_97k():
    base_rev = _dashboard()["revenue_today"]
    _commit({"intent": "sale",
             "items": [{"name": "Paket Nasi Box", "qty": 1, "unit_price": 87000, "subtotal": 87000}],
             "total": 87000, "raw_text": "TEST jual paket 87 ribu"})
    assert _dashboard()["revenue_today"] == base_rev + 87000

    r = requests.post(f"{API}/nlu/correct", json={"total": 97000, "raw_text": "Salah, tadi itu 97 ribu"},
                      timeout=T)
    assert r.status_code == 200, r.text
    d = _dashboard()
    assert d["revenue_today"] == base_rev + 97000, "correction did not revert original entry"

    hist = requests.get(f"{API}/history", timeout=T).json()["history"]
    top = hist[0]
    assert top["message"].startswith("Dikoreksi"), top["message"]
    assert "97.000" in top["message"], top["message"]
    _undo(top["id"])
    assert _dashboard()["revenue_today"] == base_rev


# ---------- reports ----------
@pytest.mark.parametrize("period,days", [("weekly", 7), ("monthly", 30)])
def test_reports(period, days):
    r = requests.get(f"{API}/reports/weekly", params={"period": period}, timeout=LLM_T)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["days"] == days
    assert any(b in d["period"] for b in
               ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"])
    assert d["profit"] == d["revenue"] - d["expense"]
    assert d["avg_per_day"] == round(d["revenue"] / days)
    assert isinstance(d["top_items"], list) and d["top_items"]
    assert d["expense_breakdown"] and sum(x["pct"] for x in d["expense_breakdown"]) in range(95, 106)
    assert isinstance(d["top_expenses"], list)
    c = d["comparison"]
    for k in ["label", "period", "revenue", "expense", "profit", "revenue_delta",
              "expense_delta", "profit_delta"]:
        assert k in c, k
    assert isinstance(d["narrative"], str) and len(d["narrative"]) > 20
    # FIX 3: with the 60-day seed both weekly and monthly comparisons must be populated
    for k in ["revenue_delta", "expense_delta", "profit_delta"]:
        assert c[k] is not None, f"{period}: comparison.{k} is null (seed too short?)"
    assert ("naik" in d["share_text"] or "turun" in d["share_text"]), d["share_text"]
    assert c["label"] in d["share_text"], d["share_text"]
    assert d["share_link"].startswith("https://wa.me/?text=")


# ---------- purchases ----------
def test_purchases_history():
    r = requests.get(f"{API}/purchases/history", timeout=T)
    assert r.status_code == 200, r.text
    rows = r.json()["purchases"]
    assert rows
    for row in rows:
        for k in ["name", "times", "total_spent", "cheapest_unit_price", "latest_unit_price", "last_at"]:
            assert k in row, k
        if row["cheapest_unit_price"] and row["latest_unit_price"] and \
                row["latest_unit_price"] > row["cheapest_unit_price"] * 1.1:
            assert row["hint"], f"missing negotiation hint for {row['name']}"
    assert rows == sorted(rows, key=lambda x: x["total_spent"], reverse=True)


# ---------- reminders ----------
def test_reminders_and_mark_reminded():
    r = requests.get(f"{API}/receivables/reminders", timeout=LLM_T)
    assert r.status_code == 200, r.text
    rems = r.json()["reminders"]
    assert rems
    first = rems[0]
    for k in ["id", "customer_name", "remaining", "message", "wa_link", "reminded_today"]:
        assert k in first, k
    assert len(first["message"]) > 15
    assert first["wa_link"].startswith("https://wa.me/62")
    assert first["reminded_today"] is False

    m = requests.post(f"{API}/receivables/{first['id']}/reminded", timeout=T)
    assert m.status_code == 200, m.text
    again = requests.get(f"{API}/receivables/reminders", timeout=LLM_T).json()["reminders"]
    flagged = next(x for x in again if x["id"] == first["id"])
    assert flagged["reminded_today"] is True
    bad = requests.post(f"{API}/receivables/xyz/reminded", timeout=T)
    assert bad.status_code == 400


# ---------- shopping list / restock ----------
def test_shopping_list_and_restock_undo():
    r = requests.get(f"{API}/shopping-list", timeout=T)
    assert r.status_code == 200
    data = r.json()
    assert data["items"], "no low stock items in demo data"
    it = data["items"][0]
    assert it["qty"] <= it["min_qty"]
    assert it["suggested_qty"] > 0
    assert it["name"] in data["share_text"]
    assert data["share_link"].startswith("https://wa.me/?text=")

    res = requests.post(f"{API}/inventory/{it['id']}/restock", json={}, timeout=T)
    assert res.status_code == 200, res.text
    after = _inv(it["name"])
    assert after["qty"] > it["qty"]
    _undo(res.json()["history_id"])
    assert _inv(it["name"])["qty"] == it["qty"]
    assert requests.post(f"{API}/inventory/zzz/restock", json={}, timeout=T).status_code == 400


# ---------- settings ----------
def test_suggest_target_and_persist():
    r = requests.get(f"{API}/settings/suggest-target", timeout=T)
    assert r.status_code == 200
    s = r.json()
    assert s["suggested"] > 0 and s["suggested"] % 5000 == 0
    assert "Target" in s["reason"] or "target" in s["reason"]

    original = requests.get(f"{API}/settings", timeout=T).json()["daily_target"]
    new_target = 275000
    p = requests.put(f"{API}/settings", json={"daily_target": new_target}, timeout=T)
    assert p.status_code == 200 and p.json()["daily_target"] == new_target
    d = _dashboard()
    assert d["daily_target"] == new_target
    assert d["target_remaining"] == max(0, new_target - d["revenue_today"])
    requests.put(f"{API}/settings", json={"daily_target": original}, timeout=T)


# ---------- brief + TTS ----------
def test_brief_and_audio_cache():
    r = requests.get(f"{API}/brief", timeout=LLM_T)
    assert r.status_code == 200, r.text
    text = r.json()["brief"]
    assert isinstance(text, str) and len(text) > 20

    a1 = requests.get(f"{API}/brief/audio", params={"text": text[:400]}, timeout=LLM_T)
    assert a1.status_code == 200, a1.text[:300]
    assert a1.headers["content-type"].startswith("audio/mpeg")
    assert len(a1.content) > 1000
    a2 = requests.get(f"{API}/brief/audio", params={"text": text[:400]}, timeout=LLM_T)
    assert a2.status_code == 200
    assert a2.content == a1.content, "cached TTS mismatch"


# ---------- NLU parse ----------
def test_parse_sale_and_expense_and_question():
    r = requests.post(f"{API}/nlu/parse",
                      json={"text": "Hari ini saya jual dua nasi goreng dan tiga es teh, total 87 ribu"},
                      timeout=LLM_T)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["intent"] == "sale" and d.get("total") == 87000 and d.get("items")

    r2 = requests.post(f"{API}/nlu/parse", json={"text": "Beli ayam 3 kg 105 ribu"}, timeout=LLM_T)
    assert r2.status_code == 200, r2.text
    assert r2.json()["intent"] == "expense" and r2.json().get("total") == 105000

    r3 = requests.post(f"{API}/nlu/parse", json={"text": "Berapa untung saya hari ini?"}, timeout=LLM_T)
    assert r3.status_code == 200, r3.text
    assert r3.json()["intent"] == "question" and len(r3.json().get("answer") or "") > 5

    assert requests.post(f"{API}/nlu/parse", json={"text": "   "}, timeout=T).status_code == 400


# ---------- receipt vision ----------
def _receipt_jpeg() -> bytes:
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (600, 800), "white")
    dr = ImageDraw.Draw(img)
    lines = [
        "TOKO SEMBAKO PAK SLAMET",
        "Jl. Melati No. 12",
        "--------------------------",
        "Beras 5 kg      x 13000   65000",
        "Telur 2 kg      x 28000   56000",
        "Minyak 1 liter  x 18000   18000",
        "--------------------------",
        "TOTAL                    139000",
        "TUNAI                    150000",
    ]
    y = 40
    for ln in lines:
        dr.text((30, y), ln, fill="black")
        y += 40
    img = img.resize((1200, 1600))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def test_expense_from_receipt():
    files = {"image": ("receipt.jpg", _receipt_jpeg(), "image/jpeg")}
    r = requests.post(f"{API}/expenses/from-receipt", files=files, timeout=LLM_T)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["intent"] == "expense", f"receipt not recognised: {d}"
    assert d["total"] > 0
    assert d["items"], "no items extracted"
    it = d["items"][0]
    for k in ["name", "qty"]:
        assert k in it, k
    assert d.get("category")

    bad = requests.post(f"{API}/expenses/from-receipt",
                        files={"image": ("x.txt", b"not-an-image", "text/plain")}, timeout=T)
    assert bad.status_code == 400


# ---------- final reset ----------
def test_demo_reset_cleans_test_data():
    r = requests.post(f"{API}/demo/reset", timeout=60)
    assert r.status_code == 200
    m = _memory()
    assert not any(c["name"].startswith("TEST_") for c in m["customers"])
    assert not any(i["name"].startswith("TEST_") for i in m["inventory"])
    budi = next(x for x in m["receivables"] if x["customer_name"] == "Pak Budi")
    assert budi["amount"] == 150000 and budi.get("paid_amount", 0) == 0
