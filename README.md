# Cue – Voice-First Business Operating System

> Manage your kirana, retail store, or wholesale shop simply by speaking in **Hindi, Hinglish, or English**.

---

## Architecture Highlights

- **Frontend:** Next.js 15 (App Router), React, TypeScript, Tailwind CSS, `MediaRecorder` + Web Audio `AnalyserNode`, `SpeechSynthesis` TTS (with instant voice barge-in), `IndexedDB` FIFO offline queue.
- **Backend:** Python FastAPI, Pydantic v2 (`extra="forbid"`), Supabase JWT verification (JWKS + Auth fallback), `SecurityPolicyEngine`, 30-Day rolling daily memory (`Asia/Kolkata`), `EntityResolver`, and atomic PostgreSQL RPCs.
- **AI & Speech (100% Free Cloud Split, Zero Local PC Load):**
  - **Speech-to-Text:** Groq Free Whisper (`whisper-large-v3-turbo`) primary + modular adapters (`faster_whisper`, `gemini_audio`, `indic_conformer`).
  - **AI Parser:** Google Gemini Free Tier (`gemini-3.5-flash-lite` + resilient fallback) acting strictly as an **untrusted read-only JSON parser** (zero DB/SQL/destructive permissions) + optional `ollama` adapter.
- **Database & Auth:** Supabase Free Tier (PostgreSQL, Row Level Security across 19 tables, Email/Password + Google OAuth, `Free / Growth / Pro` subscription tiers).

---

## Quick Setup Guide

### 1. Apply Supabase SQL Migrations
In your Supabase Dashboard → **SQL Editor**, run these 4 migration files in exact order:
1. [001_schema.sql](file:///c:/Users/nitin/OneDrive/Documents/cue/backend/app/db/migrations/001_schema.sql)
2. [002_rls_and_security.sql](file:///c:/Users/nitin/OneDrive/Documents/cue/backend/app/db/migrations/002_rls_and_security.sql)
3. [003_atomic_rpcs.sql](file:///c:/Users/nitin/OneDrive/Documents/cue/backend/app/db/migrations/003_atomic_rpcs.sql)
4. [004_seed_plans.sql](file:///c:/Users/nitin/OneDrive/Documents/cue/backend/app/db/migrations/004_seed_plans.sql)

### 2. Configure Environment Files
Copy `backend/.env.example` → `backend/.env` and `frontend/.env.local.example` → `frontend/.env.local`, filling in your Supabase, Gemini, and Groq keys (`.env` and `.env.local` are strictly git-ignored).

### 3. Start Backend (FastAPI)
```bash
cd backend
.\.venv\Scripts\uvicorn.exe app.main:app --reload --port 8000
```

### 4. Start Frontend (Next.js)
```bash
cd frontend
npm run dev
```

Open **http://localhost:3000**, sign up at `/login`, choose **Free Pilot** at `/onboarding` to seed your store, and start speaking!

---

## Automated Tests

```bash
cd backend
.\.venv\Scripts\pytest.exe -v
```
