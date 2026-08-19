"""VoiceBiz backend integration tests (pytest)."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://voice-commerce-12.preview.emergentagent.com").rstrip("/")
# Read frontend .env if available
try:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
                break
except FileNotFoundError:
    pass

API = f"{BASE_URL}/api"


@pytest.fixture(scope="module", autouse=True)
def reset_before_all():
    r = requests.post(f"{API}/demo/reset", timeout=30)
    assert r.status_code == 200


# ---------- Basic reads ----------
def test_root():
    r = requests.get(f"{API}/", timeout=15)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_dashboard_shape():
    r = requests.get(f"{API}/dashboard", timeout=20)
    assert r.status_code == 200
    d = r.json()
    for k in ["revenue_today", "expense_today", "profit_today", "trend", "insights", "activities"]:
        assert k in d
    assert len(d["trend"]) == 7
    # insights recommend actions
    if d["insights"]:
        assert any("action" in i for i in d["insights"])


def test_memory_seeded():
    r = requests.get(f"{API}/memory", timeout=20)
    assert r.status_code == 200
    m = r.json()
    for k in ["sales", "expenses", "customers", "receivables", "inventory"]:
        assert len(m[k]) > 0, f"{k} not seeded"
    # Indonesian names
    names = [c["name"] for c in m["customers"]]
    assert "Pak Budi" in names


def test_brief_llm():
    r = requests.get(f"{API}/brief", timeout=60)
    assert r.status_code == 200, r.text
    b = r.json().get("brief", "")
    assert isinstance(b, str) and len(b) > 10


# ---------- NLU parsing ----------
def test_parse_sale():
    r = requests.post(f"{API}/nlu/parse", json={"text": "Hari ini saya jual dua nasi goreng dan tiga es teh, total 87 ribu"}, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["intent"] == "sale"
    assert d.get("total") == 87000
    assert len(d.get("items") or []) >= 1


def test_parse_receivable():
    r = requests.post(f"{API}/nlu/parse", json={"text": "Pak Budi masih punya utang 150 ribu dari minggu lalu"}, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["intent"] == "receivable"
    assert (d.get("customer_name") or "").lower().find("budi") >= 0
    assert d.get("total") == 150000


def test_parse_expense():
    r = requests.post(f"{API}/nlu/parse", json={"text": "Beli ayam 3 kg 105 ribu"}, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["intent"] == "expense"
    assert d.get("total") == 105000


def test_parse_question():
    r = requests.post(f"{API}/nlu/parse", json={"text": "Berapa untung saya hari ini?"}, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["intent"] == "question"
    assert isinstance(d.get("answer"), str) and len(d["answer"]) > 5


# ---------- Commit flows ----------
def _dashboard():
    return requests.get(f"{API}/dashboard", timeout=20).json()


def _memory():
    return requests.get(f"{API}/memory", timeout=20).json()


def test_commit_sale_updates_revenue_and_inventory():
    before = _dashboard()
    mem_before = _memory()
    ayam_before = next((i for i in mem_before["inventory"] if i["name"].lower() == "ayam potong"), None)

    payload = {
        "intent": "sale",
        "items": [{"name": "Ayam potong", "qty": 1, "unit_price": 25000, "subtotal": 25000}],
        "total": 25000,
    }
    r = requests.post(f"{API}/nlu/commit", json=payload, timeout=20)
    assert r.status_code == 200, r.text
    after = _dashboard()
    assert after["revenue_today"] >= before["revenue_today"] + 25000
    if ayam_before:
        mem_after = _memory()
        ayam_after = next((i for i in mem_after["inventory"] if i["name"].lower() == "ayam potong"), None)
        assert ayam_after["qty"] == max(0, ayam_before["qty"] - 1)


def test_commit_receivable_increases_outstanding():
    before = _dashboard()
    payload = {"intent": "receivable", "customer_name": "Bu Testing", "total": 55000}
    r = requests.post(f"{API}/nlu/commit", json=payload, timeout=20)
    assert r.status_code == 200
    after = _dashboard()
    assert after["outstanding_receivables"] >= before["outstanding_receivables"] + 55000
    mem = _memory()
    assert any(rec["customer_name"] == "Bu Testing" for rec in mem["receivables"])


def test_commit_receivable_payment_for_pak_budi():
    mem_before = _memory()
    budi_before = next((r for r in mem_before["receivables"] if r["customer_name"] == "Pak Budi" and r["status"] != "lunas"), None)
    assert budi_before is not None, "Pak Budi receivable missing"
    remaining_before = budi_before["amount"] - budi_before.get("paid_amount", 0)

    payload = {"intent": "receivable_payment", "customer_name": "Pak Budi", "total": 50000}
    r = requests.post(f"{API}/nlu/commit", json=payload, timeout=20)
    assert r.status_code == 200, r.text

    mem_after = _memory()
    budi_after = next((r for r in mem_after["receivables"] if r["customer_name"] == "Pak Budi"), None)
    remaining_after = budi_after["amount"] - budi_after.get("paid_amount", 0)
    assert remaining_after == remaining_before - 50000


def test_demo_reset_restores():
    r = requests.post(f"{API}/demo/reset", timeout=30)
    assert r.status_code == 200
    mem = _memory()
    # Bu Testing added in earlier test should now be gone
    assert not any(rec["customer_name"] == "Bu Testing" for rec in mem["receivables"])
    # Pak Budi original piutang restored to 150000, unpaid
    budi = next(r for r in mem["receivables"] if r["customer_name"] == "Pak Budi")
    assert budi["amount"] == 150000
    assert budi.get("paid_amount", 0) == 0
