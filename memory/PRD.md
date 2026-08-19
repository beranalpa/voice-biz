# VoiceBiz — PRD

## Problem Statement (original)
Build a polished full-stack web app called VoiceBiz: an AI business assistant for Indonesian micro-business owners and social-commerce sellers. Core idea: "Talk to your business. Get things done." Users speak or type informal Indonesian (e.g. "Hari ini saya jual dua nasi goreng dan tiga es teh, total 87 ribu"); VoiceBiz understands intent, extracts business info, and stores structured business data. MVP: (1) Talk to VoiceBiz — voice with text fallback + confirmation before saving; (2) Business Memory — sales, expenses, customers, receivables, inventory, updated from natural language, real stored data for calculations; (3) AI Business Brief — today's performance dashboard with insights (declining sales, outstanding payments, low stock, inactive customers) and recommended next actions. Mobile-first, premium Indonesian SaaS feel, realistic Indonesian demo data.

## Architecture
- Backend: FastAPI (`/app/backend/server.py`), MongoDB via Motor. Modules: `nlu.py` (LLM NLU + Q&A + briefing), `seed.py` (Indonesian demo data).
- AI: OpenAI `gpt-5.6-luna` via `emergentintegrations` LlmChat (EMERGENT_LLM_KEY) for NLU/answers/briefing; `whisper-1` (OpenAISpeechToText) for Indonesian voice transcription.
- Frontend: React (CRA + Tailwind + shadcn), mobile-container layout (max-w-md), pages `Home.jsx` / `Memory.jsx`, components `TalkPanel`, `ConfirmSheet`, `StatCards`, `InsightList`, `TrendChart`.
- Endpoints: `POST /api/voice/transcribe`, `POST /api/nlu/parse`, `POST /api/nlu/commit`, `GET /api/dashboard`, `GET /api/brief`, `GET /api/memory`, `POST /api/demo/reset`.

## Users
- Warung / food-stall owner (primary): logs sales, expenses, debts by talking.
- Social-commerce seller: tracks orders, receivables, restock needs from chat-style language.

## Core requirements (static)
1. Voice-first input with text fallback, informal Indonesian understanding.
2. Confirmation card (Simpan/Edit) before persisting.
3. Business memory: sales, expenses, customers, receivables, inventory.
4. Dashboard from real stored data + AI insights with recommended actions.
5. Bahasa Indonesia UI, mobile-first, no auth (single demo user).

## Implemented (2026-06)
- Indonesian NLU: intents sale / expense / receivable / receivable_payment / inventory / customer / question, with Indonesian number parsing ("87 ribu", "1,5 juta", "20k").
- Confirmation sheet with editable total & customer before save; question intent answers grounded in stored data.
- Commit pipeline: sales decrement matching inventory, receivable payments reduce remaining balance, customers auto-created/touched, activity log.
- Dashboard: revenue/expense/profit today, vs-yesterday delta, 7-day trend bars, rule-based insights (sales drop, outstanding receivables, low stock, inactive customers) each with a recommended action, activity feed.
- AI daily briefing endpoint + UI card.
- Seeded realistic Indonesian food-business demo data + reset button.
- Voice recording via MediaRecorder → Whisper (`language=id`), graceful fallback to text.
- Tested: backend 12/12 pytest pass; frontend flows verified (chips, text input, save → dashboard update, edit mode, question answer, memory tabs, briefing).

## Backlog
P0: none blocking.
P1: WhatsApp-style shareable daily recap, receivable reminder message generator, per-item price learning (auto price memory), weekly/monthly report view.
P2: multi-user auth + multiple outlets, offline queue for weak signal, export to Excel/PDF, product margin & best-seller analytics, push notification reminders.

## Next tasks
- Voice streaming feedback (live partial transcript).
- Undo last saved entry.
- Onboarding first-run walkthrough in Bahasa Indonesia.
