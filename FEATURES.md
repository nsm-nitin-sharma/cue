# Cue – Master Product Feature Tracker

> **Purpose:** Living source of truth for every discussed feature, security control, UX requirement, and architectural capability in **Cue**.  
> **Legend:** `[x]` Built & Verified | `[~]` Ready / Requires SQL Migration Run in Supabase | `[ ]` Pending

---

## 1. Project Foundation, GitHub & Hardcore Security

- [x] Initialize Git repository on `main` with strict secret-blocking `.gitignore`
- [x] Author enterprise implementation blueprint ([IMPLEMENTATION_PLAN.md](file:///c:/Users/nitin/OneDrive/Documents/cue/IMPLEMENTATION_PLAN.md))
- [x] Connect GitHub remote & push milestone commits (zero secrets ever committed)
- [x] Verify Supabase JWT (`auth.uid()`) on every API route (`deps.py` + `security.py`); never trust client/LLM-supplied `user_id` or `business_id`
- [x] Enforce Supabase Row Level Security (RLS) across all business tables (`002_rls_and_security.sql` live in Supabase)
- [x] **AI-as-Untrusted-Parser Sandboxing:** LLM has zero DB, SQL, shell, or task-execution authority; outputs strict JSON only
- [x] **Pydantic v2 Schema Firewall (`extra="forbid"`):** Strict enum-locked intents, regex-checked IDs/dates, bounded quantities & array lengths
- [x] **Zero Destructive Intents (`SecurityPolicyEngine`):** No AI/voice intents for delete, wipe, drop, or bulk reset (`POLICY_BLOCKED`)
- [x] **Append-Only Immutable Ledger:** Corrections/undos insert compensating reversal records + immutable `audit_trail` (no hard deletes)
- [x] **3-Tier Execution Gate:** Auto-execute safe actions, clarify on doubt, confirm Tier-3 actions via cryptographic `pending_confirmations` token
- [x] **`₹5,000` High-Value Confirmation Threshold:** Single transactions `>= ₹5,000` or cross-day reversals require explicit confirmation
- [x] **Negative Stock Blocking:** Prevent silent negative stock by default; prompt owner for clarification
- [x] **Atomic PostgreSQL RPCs + `SELECT ... FOR UPDATE`:** Applied in Supabase (`003_atomic_rpcs.sql`)
- [x] **Strict Idempotency:** Client UUID `operation_id` + `payload_hash` enforced via `UNIQUE (business_id, operation_id)` and `409 Conflict` check
- [x] **API & Upload Hardening:** Audio MIME/magic-byte validation, max file size/duration, rate limiting, CORS allowlist, security headers, PII-redacted logs

---

## 2. Authentication, Onboarding & Subscription SaaS

- [x] **Email + Password** signup & login via Supabase Auth
- [x] **Google OAuth** login via Supabase Auth (UI + callback wired; toggle Google provider in Supabase Auth when ready)
- [x] **Subscription Tiers (`Free`, `Growth`, `Pro`):**
  - [x] `Free` tier active out-of-the-box for testing within defined quotas (`250/mo`, no payment required)
  - [x] `Growth` & `Pro` configurable tiers with DB-driven feature/quota flags (no hardcoded pricing)
  - [x] Server-side tier entitlement & monthly quota enforcement (`entitlements.py`)
- [x] Store onboarding flow + optional Kirana sample catalog & alias seeder (`rpc_onboard_business`)
- [x] `business_members` multi-staff RBAC schema readiness

---

## 3. Voice Pipeline & Modular AI/Speech Stack (100% Free)

- [x] Browser `MediaRecorder` capture with cross-browser codec negotiation (`webm/opus` → `webm` → `mp4`)
- [x] Web Audio API live frequency waveform + RMS energy visualization
- [x] Browser `SpeechSynthesis` spoken responses (`hi-IN` / `en-IN` voices + mute/replay controls)
- [x] **Voice Barge-In / Auto-Stop TTS:** Cue immediately stops speaking whenever the user starts speaking or activates the mic
- [x] **Modular `STTProvider` Interface:**
  - [x] Default: **Groq Free Tier Whisper (`whisper-large-v3-turbo`)** (zero PC load, preserves Gemini quota)
  - [x] Optional local: **`faster-whisper`** (`base`/`small` int8 CPU)
  - [x] Optional fallback: **Google Gemini Audio (Free Tier)**
  - [x] Extensible adapter: **AI4Bharat IndicConformer** (for regional language evaluation)
- [x] **Modular `LLMProvider` Interface:**
  - [x] Primary: **Google Gemini API (Free Tier)** (`gemini-3.5-flash-lite` + resilient fallback) — zero PC load
  - [x] Optional local: **Ollama** (disabled by default)
- [x] Hindi, English, and Hinglish code-switching + Indian accent/vocabulary support
- [x] Extensible language architecture for future Indian regional languages

---

## 4. Strict "Do You Mean This?" Clarification & Catalog Intelligence

- [x] **Multi-Command Batch Execution (Single-Breath Operations):**
  - [x] Extract and execute multiple distinct operations from one spoken utterance (e.g., *"20 Maggi aayi, 10 Pepsi ki bottle aayi, aur 5 Maggi biki"*)
  - [x] Preserve chronological order within the same utterance (receive before sale so stock updates accurately)
  - [x] Partial batch resolution: execute clear, valid items while holding ambiguous/missing-field items in `pending_batch_items`
- [x] **Zero-Guessing Ambiguity Rule:** Any uncertain match or missing field pauses execution and asks *"Do you mean ...?"*
- [x] **Verified Alias Learning:** Saying *"Coke"* when DB has *"Coca-Cola"* asks *"Do you mean Coca-Cola?"*:
  - [x] On **Yes**: Executes transaction atomically **and saves `"Coke"` as a verified alias** in `product_aliases`
  - [x] On **No**: Aborts candidate and asks for further clarification
- [x] Multi-product disambiguation (*"20 Pepsi bik gayi"* → *"Pepsi 500ml ya Pepsi 2L?"* → replying just *"500ml"* by voice or tap merges `"500ml"` with the held quantity `20`)
- [x] Duplicate customer disambiguation (using phone last-4 digits / area note / balance, resolvable by voice reply like *"Gupta"* or chip tap)
- [x] **Brand-New Product / Customer Creation (Voice + Pop-Up):**
  - [x] Cue asks *"Kya naya product add karun?"* AND displays an interactive confirmation pop-up on screen
  - [x] Confirming via **either voice or screen button** closes the pop-up, creates the item, and commits the transaction atomically
- [x] **Schema-Driven Multi-Turn Slot-Filling (Required Field Prompting Across All Intents):**
  - [x] Holds partial draft without committing incomplete records whenever required business/DB fields are missing
  - [x] Stock Receive (`inventory_receive`): asks purchase/cost price if not provided
  - [x] Sales, Expenses, Payments & New Product missing-slot prompting
- [x] Hinglish/Hindi number & fraction parser (`pav = 0.25`, `aadha = 0.5`, `dedh = 1.5`, `dhai = 2.5`, `darjan = 12`)
- [x] Unit normalization (`piece/nag/bottle`, `packet/pkt`, `kg/kilo`, `litre/L`, `box/peti`) & `product_unit_conversions` (`500g → 0.5 kg`, incompatible unit rejection)

---

## 5. Conversational Memory, 30-Day History & Business Day Replay

- [x] **One Chat = One Business Day:** Continuous daily chat thread (`UNIQUE (business_id, conversation_date)` in `Asia/Kolkata`) synced across reloads/devices
- [x] Same-day anaphora & multi-turn context (*"20 Pepsi bottles aayi hain"* → *"Unmein se 3 damaged hain"* → net `+17`)
- [x] **30-Day (1-Month) Cross-Day Memory Retrieval:** Queries past 30 days of `conversation_messages` + ledger transactions
- [x] **`> 30 Days` Boundary Guard:** References older than 30 days politely explain the 30-day chat memory window and point to permanent **Reports / Ledger** views
- [x] **Corrections, Reversals & Undo:** (*"10 packets bik gaye"* → *"Actually 7 the"* OR *"20 chotti pepsi bik gyi"* → *"20 pepsi nahi 10 hi biki"*) extracts post-negation target quantities, adjusts net stock/amount atomically, and logs immutable `audit_trail`
- [x] **Business Day Replay:** Multi-transaction end-of-day narration, relative dates (`aaj`, `kal`, `parso`), `transaction_date` vs `created_at` separation in `Asia/Kolkata`, and Daily Business Summary generation

---

## 6. Core Business Ledger & Future BI Foundation

- [x] Required Database Tables (`001_schema.sql` live in Supabase): `businesses`, `products`, `product_aliases`, `inventory`, `inventory_movements`, `customers`, `sales`, `sale_items`, `expenses`, `conversations`, `voice_transactions`
- [x] Additional Enterprise Tables (`001_schema.sql` live in Supabase): `business_members`, `product_unit_conversions`, `customer_payments`, `conversation_messages`, `pending_confirmations`, `subscription_plans`, `business_subscriptions`, `business_insights_events`
- [x] Voice & UI Inventory: Receive, Deduct, Damage/Expiry, Adjustment, Low-stock alerts, Movement History
- [x] Voice & UI Sales: Cash, Partial, and Credit (`Udhaar`) sales with itemized breakdown
- [x] Voice & UI Customers: Customer credit ledger, payment collection, pending balance queries
- [x] Voice & UI Expenses: Categorized daily shop expenses
- [x] Natural Business Queries (*"Aaj kitni sale hui?"*, *"Ramesh ka kitna payment pending hai?"*)
- [x] **Future BI Foundation (Section 10):** Clean time-series collection + `analytics_foundation.py` modular stub

---

## 7. Speech Error Handling & Offline Connectivity Resilience

- [x] Empty/silent/noisy recording rejection with instant retry prompt (no LLM waste or DB mutation)
- [x] Partial clarification (ask user to repeat only unclear quantity or detail)
- [x] **Browser `IndexedDB` FIFO Offline Queue:** Stores audio/pending operations offline with `Pending Sync` badge, replays strictly in chronological order on reconnect with idempotency protection

---

## 8. Bespoke Minimal UI/UX ("Warm Ledger & Studio Voice")

- [x] Desktop-first, responsive enterprise light theme (`#F7F8FA` porcelain canvas, `#0F172A` obsidian ink, `#1D4ED8` precision cobalt voice accent, tabular monospace numerals)
- [x] **Voice Desk (Home):** Prominent **Living Mic Orb** (`Space` / `Ctrl+M` shortcut), live waveform, clear status states
- [x] Tactile **Paper-Slip Receipt Cards** in the conversation stream with quick `Undo` / `Edit` / `Confirm` controls
- [x] **30-Day Daily Chat Drawer** (`Today`, `Yesterday`, ..., past 30 days)
- [x] Live **"Today's Register"** pulse ticker & slide-over drawer
- [x] Dedicated Dashboard Views: **Inventory**, **Sales**, **Customers (Udhaar)**, **Expenses**, and **Reports / Business Day Replay**

---

## 9. Automated Testing & Verification

- [x] Security Tests (`test_security_and_policy.py`): Destructive-intent blocking, prompt-injection defense, Pydantic firewall, `₹5,000` confirmation gate, audio magic-byte validation, PII redaction
- [x] Unit & Domain Tests (`test_domain_and_resolver.py`): Hinglish number/fraction parser, post-negation extraction, unit converter, `"Do you mean?"` + disambiguation merging, `>30 days` boundary, multi-command parsing
- [x] Frontend Verification: TypeScript strict check & Next.js production build
- [ ] End-to-End Live Voice Walkthrough against Supabase (after running SQL migrations in Supabase SQL Editor)
