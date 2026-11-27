# Cue – Master Product Feature Tracker

> **Purpose:** Living source of truth for every discussed feature, security control, UX requirement, and architectural capability in **Cue**.  
> **Legend:** `[x]` Completed & Verified | `[~]` In Progress | `[ ]` Pending

---

## 1. Project Foundation, GitHub & Hardcore Security

- [x] Initialize Git repository on `main` with strict secret-blocking `.gitignore`
- [x] Author enterprise implementation blueprint ([IMPLEMENTATION_PLAN.md](file:///c:/Users/nitin/OneDrive/Documents/cue/IMPLEMENTATION_PLAN.md))
- [x] Connect GitHub remote & push milestone commits (zero secrets ever committed)
- [ ] Verify Supabase JWT (`auth.uid()`) on every API route; never trust client/LLM-supplied `user_id` or `business_id`
- [ ] Enforce Supabase Row Level Security (RLS) across all business tables
- [ ] **AI-as-Untrusted-Parser Sandboxing:** LLM has zero DB, SQL, shell, or task-execution authority; outputs strict JSON only
- [ ] **Pydantic v2 Schema Firewall (`extra="forbid"`):** Strict enum-locked intents, regex-checked IDs/dates, bounded quantities & array lengths
- [ ] **Zero Destructive Intents (`SecurityPolicyEngine`):** No AI/voice intents for delete, wipe, drop, or bulk reset (`POLICY_BLOCKED`)
- [ ] **Append-Only Immutable Ledger:** Corrections/undos insert compensating reversal records + immutable `audit_trail` (no hard deletes)
- [ ] **3-Tier Execution Gate:** Auto-execute safe actions, clarify on doubt, confirm Tier-3 actions via cryptographic `pending_confirmations` token
- [ ] **`₹5,000` High-Value Confirmation Threshold:** Single transactions `>= ₹5,000` or cross-day reversals require explicit confirmation
- [ ] **Negative Stock Blocking:** Prevent silent negative stock by default; prompt owner for clarification
- [ ] **Atomic PostgreSQL RPCs + `SELECT ... FOR UPDATE`:** Prevent race conditions on concurrent multi-device updates
- [ ] **Strict Idempotency:** Client UUID `operation_id` + `payload_hash` enforced via `UNIQUE (business_id, operation_id)`
- [ ] **API & Upload Hardening:** Audio MIME/magic-byte validation, max file size/duration, rate limiting, CORS allowlist, security headers, PII-redacted logs

---

## 2. Authentication, Onboarding & Subscription SaaS

- [ ] **Email + Password** signup & login via Supabase Auth
- [ ] **Google OAuth** login via Supabase Auth
- [ ] **Subscription Tiers (`Free`, `Growth`, `Pro`):**
  - [ ] `Free` tier active out-of-the-box for testing within defined quotas (no payment required)
  - [ ] `Growth` & `Pro` configurable tiers with DB-driven feature/quota flags (no hardcoded pricing)
  - [ ] Server-side tier entitlement & monthly quota enforcement
- [ ] Store onboarding flow + optional Kirana sample catalog & alias seeder
- [ ] `business_members` multi-staff RBAC schema readiness

---

## 3. Voice Pipeline & Modular AI/Speech Stack (100% Free)

- [x] Browser `MediaRecorder` capture with cross-browser codec negotiation (`webm/opus` → `webm` → `mp4`)
- [x] Web Audio API live frequency waveform + RMS silence/noise pre-check
- [x] Browser `SpeechSynthesis` spoken responses (`hi-IN` / `en-IN` voices + mute/replay controls)
- [x] **Voice Barge-In / Auto-Stop TTS:** Cue immediately stops speaking whenever the user starts speaking or activates the mic
- [ ] **Modular `STTProvider` Interface:**
  - [ ] Default: **Groq Free Tier Whisper (`whisper-large-v3-turbo`)** (zero PC load, preserves Gemini quota)
  - [ ] Optional local: **`faster-whisper`** (`base`/`small` int8 CPU)
  - [ ] Optional fallback: **Google Gemini Audio (Free Tier)**
  - [ ] Extensible adapter: **AI4Bharat IndicConformer** (for regional language evaluation)
- [ ] **Modular `LLMProvider` Interface:**
  - [ ] Primary: **Google Gemini API (Free Tier)** (`gemini-2.5-flash`) — zero PC load
  - [ ] Optional local: **Ollama** (disabled by default)
- [ ] Hindi, English, and Hinglish code-switching + Indian accent/vocabulary support
- [ ] Extensible language architecture for future Indian regional languages

---

## 4. Strict "Do You Mean This?" Clarification & Catalog Intelligence

- [ ] **Multi-Command Batch Execution (Single-Breath Operations):**
  - [ ] Extract and execute multiple distinct operations from one spoken utterance (e.g., *"20 Maggi aayi, 10 Pepsi ki bottle aayi, aur 5 Maggi biki"*) instead of forcing one-by-one turns
  - [ ] Preserve chronological order within the same utterance (e.g., receive before sale so stock updates accurately)
  - [ ] Partial batch resolution: execute clear, valid items immediately while holding only ambiguous/missing-field items in `pending_batch_slots` for targeted clarification
- [ ] **Zero-Guessing Ambiguity Rule:** Any uncertain match or missing field pauses execution and asks *"Do you mean ...?"*
- [ ] **Verified Alias Learning:** Saying *"Coke"* when DB has *"Coca-Cola"* asks *"Do you mean Coca-Cola?"*:
  - [ ] On **Yes**: Executes transaction atomically **and saves `"Coke"` as a verified alias** in `product_aliases`
  - [ ] On **No**: Aborts candidate and asks for further clarification
- [ ] Multi-product disambiguation (*"20 Pepsi bik gayi"* → *"Pepsi 500ml ya Pepsi 2L?"* → replying just *"500ml"* by voice or tap merges `"500ml"` with the held quantity `20` and executes without repeating the full sentence)
- [ ] Duplicate customer disambiguation (using phone last-4 digits / area note / balance, resolvable by voice reply like *"Gupta"* or chip tap)
- [ ] **Brand-New Product / Customer Creation (Voice + Pop-Up):**
  - [ ] Cue asks *"Kya naya product add karun?"* AND displays an interactive confirmation pop-up on screen
  - [ ] Confirming via **either voice or screen button** closes the pop-up, creates the item, and commits the transaction atomically
- [ ] **Schema-Driven Multi-Turn Slot-Filling (Required Field Prompting Across All Intents):**
  - [ ] Holds partial draft in `pending_slot_fill` without committing incomplete records whenever required business/DB fields are missing
  - [ ] Stock Receive (`inventory_receive`): asks purchase/cost price if not provided (e.g., *"5 Coca-Cola kis rate par kharidi?"*)
  - [ ] Sales (`record_sale`): asks missing selling price, payment type (`cash`/`credit`/`partial`), or customer name for udhaar
  - [ ] Expenses (`record_expense`): asks missing amount, category, or payment method (`cash`/`upi`/`bank`)
  - [ ] Customer Payments (`record_customer_payment`): asks missing customer, amount, or payment method
  - [ ] New Product (`create_product`): collects `name`, `base_unit`, `cost_price`, `selling_price` via voice or pop-up fields before saving
- [ ] Hinglish/Hindi number & fraction parser (`pav = 0.25`, `aadha = 0.5`, `dedh = 1.5`, `dhai = 2.5`, `darjan = 12`)
- [ ] Unit normalization (`piece/nag/bottle`, `packet/pkt`, `kg/kilo`, `litre/L`, `box/peti`) & `product_unit_conversions` (`500g → 0.5 kg`, `1 peti → 24 pcs`, incompatible unit rejection)

---

## 5. Conversational Memory, 30-Day History & Business Day Replay

- [ ] **One Chat = One Business Day:** Continuous daily chat thread (`UNIQUE (business_id, conversation_date)` in `Asia/Kolkata`) synced across reloads/devices
- [ ] Same-day anaphora & multi-turn context (*"20 Pepsi bottles aayi hain"* → *"Unmein se 3 damaged hain"* → net `+17`)
- [ ] **30-Day (1-Month) Cross-Day Memory Retrieval:** Queries past 30 days of `conversation_messages` + ledger transactions (e.g., *"Kal jo Pepsi aayi thi, wo expired thi"*)
- [ ] **`> 30 Days` Boundary Guard:** References older than 30 days (e.g., *"Do mahine pehle..."*) gracefully explain the 30-day chat memory window and point to permanent **Reports / Ledger** views
- [ ] **Corrections, Reversals & Undo:** (*"10 packets bik gaye"* → *"Actually 7 the"* OR *"20 chotti pepsi bik gyi"* → *"20 pepsi nahi 10 hi biki"*) extracts post-negation target quantities, adjusts net stock/amount atomically, and logs immutable `audit_trail`
- [ ] **Business Day Replay:** Multi-transaction end-of-day narration, missing-info prompts, relative dates (`aaj`, `kal`, `parso`), `transaction_date` vs `created_at` separation in `Asia/Kolkata`, and Daily Business Summary generation

---

## 6. Core Business Ledger & Future BI Foundation

- [ ] Required Database Tables: `businesses`, `products`, `product_aliases`, `inventory`, `inventory_movements`, `customers`, `sales`, `sale_items`, `expenses`, `conversations`, `voice_transactions`
- [ ] Additional Enterprise Tables: `business_members`, `product_unit_conversions`, `customer_payments`, `conversation_messages`, `pending_confirmations`, `subscription_plans`, `business_subscriptions`, `business_insights_events`
- [ ] Voice & UI Inventory: Receive, Deduct, Damage/Expiry, Adjustment, Low-stock alerts, Movement History
- [ ] Voice & UI Sales: Cash, Partial, and Credit (`Udhaar`) sales with itemized breakdown
- [ ] Voice & UI Customers: Customer credit ledger, payment collection, pending balance queries
- [ ] Voice & UI Expenses: Categorized daily shop expenses
- [ ] Natural Business Queries (*"Aaj kitni sale hui?"*, *"Ramesh ka kitna payment pending hai?"*)
- [ ] **Future BI Foundation (Section 10):** Clean time-series collection + `analytics_foundation.py` modular stub for future low-stock prediction, unusual sales detection & restocking insights

---

## 7. Speech Error Handling & Offline Connectivity Resilience

- [ ] Empty/silent/noisy recording rejection with instant retry prompt (no LLM waste or DB mutation)
- [ ] Partial clarification (ask user to repeat only unclear quantity or detail)
- [x] **Browser `IndexedDB` FIFO Offline Queue:** Stores audio/pending operations offline with `Pending Sync` badge, replays strictly in chronological order on reconnect with idempotency protection

---

## 8. Bespoke Minimal UI/UX ("Warm Ledger & Studio Voice")

- [x] Desktop-first, responsive enterprise light theme (`#F7F8FA` porcelain canvas, `#0F172A` obsidian ink, `#1D4ED8` precision cobalt voice accent, tabular monospace numerals)
- [x] **Voice Desk (Home):** Prominent **Living Mic Orb** (`Space` / `Ctrl+M` shortcut), live waveform, clear status states (`Listening`, `Transcribing`, `Validating`, `Saved`, `Needs Clarification`, `Confirm Required`, `Pending Sync`, `Error`)
- [x] Tactile **Paper-Slip Receipt Cards** in the conversation stream with quick `Undo` / `Edit` / `Confirm` controls
- [x] **30-Day Daily Chat Sidebar** (`Today`, `Yesterday`, ..., past 30 days)
- [x] Live **"Today's Ledger Pulse"** side strip updating smoothly on voice commits
- [x] Dedicated Dashboard Views: **Inventory**, **Sales**, **Customers (Udhaar)**, **Expenses**, and **Reports / Business Day Replay**

---

## 9. Automated Testing & Verification

- [ ] Security Tests: Destructive-intent blocking, prompt-injection defense, JWT/tenant isolation, idempotency conflict (`409`), `₹5,000` confirmation token gate, negative-stock block
- [ ] Unit & Domain Tests: Hinglish number/fraction parser, unit converter, `"Do you mean?"` + alias learning, `>30 days` boundary, correction audit trails
- [x] Frontend Verification: TypeScript strict check & Next.js production build
- [ ] End-to-End Live Voice Walkthrough against Supabase + Gemini + Groq Whisper
