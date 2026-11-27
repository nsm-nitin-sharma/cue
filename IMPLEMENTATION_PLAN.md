# Cue – Enterprise Architecture, Hardcore Security & Master Implementation Plan

> **Document Purpose:** Authoritative, session-persistent engineering specification for **Cue (Voice-First Business Operating System)**.  
> **Mandate:** 100% free tooling, enterprise-grade reliability, zero-agency AI security, exhaustive edge-case foresight, day-grouped 30-day conversational memory, and a bespoke, minimal, non-AI-generic UI/UX.

---

## 1. Confirmed Decisions & Non-Negotiable Principles

1. **100% Free Stack — Zero Paid Dependencies**
   - Every library, model, database, auth provider, and runtime must work on free tiers or open-source software with no paid tools required.
2. **Database & Auth — Supabase Free Tier**
   - Uses **Supabase PostgreSQL + Supabase Auth (Email/Password + Google OAuth) + Row Level Security (RLS)** (credentials provided via `.env`, kept strictly server-side for privileged operations).
3. **PC-Safe Compute — Two-Provider Free Cloud Split (Zero PC Load)**
   - **STT Default:** **Groq Free Tier Whisper (`whisper-large-v3-turbo`)** — preserves Gemini quota solely for reasoning/NLU and avoids PC CPU/RAM load. Modular `STTProvider` also supports `faster_whisper`, `gemini_audio`, and `indic_conformer`.
   - **LLM Default:** **Google Gemini API (Free Tier)** (`gemini-2.5-flash`) runs in the cloud with zero local PC load. **Ollama** remains an optional, disabled-by-default modular adapter.
4. **Strict "Do You Mean This?" Zero-Guessing Rule & Verified Alias Learning**
   - Whenever there is **any** doubt—unverified alias/fuzzy match (e.g., user says *"Coke"* when DB has *"Coca-Cola"* without a verified alias), multiple matches (*"Pepsi"* → *"Pepsi 500ml"* vs *"Pepsi 2L"*), unclear quantity, missing customer, or ambiguous intent—Cue **never executes or guesses**.
   - Cue asks explicitly: *"Do you mean Coca-Cola?"* (in the user's selected language) and holds the proposed action in `pending_clarification`:
     - **If Yes:** Executes the exact action atomically **and saves `"Coke"` as a verified alias** in `product_aliases` for future commands.
     - **If No:** Aborts the candidate and asks for further clarification without touching inventory/ledger data.
   - **Brand-New Product / Customer Flow:** If a spoken item/customer does not exist in DB, Cue asks (*"Kya naya product add karun?"*) **and displays an interactive confirmation pop-up on screen**. Confirming either **by voice** or **by clicking Confirm** closes the pop-up and atomically creates the item + records the transaction.
   - **Schema-Driven Multi-Turn Slot-Filling (Required Field Prompting):** Speaking only partial details (e.g., *"Coke ki inventory mein 5 aur add ho gaye"* without purchase price) never saves an incomplete record or silent default. Cue checks the target operation's required database/business fields (`purchase_price` for stock receive, `selling_price` / `payment_status` / `customer` for sales, `amount` / `payment_method` / `category` for expenses, `amount` / `payment_method` for payments, `base_unit` / `cost_price` / `selling_price` for new products), holds the partial draft in `conversations.context_state.pending_slot_fill`, and asks back specifically for the missing fields (e.g., *"5 Coca-Cola kis purchase price par aayi?"*) before executing atomically.
   - **Multi-Command Batch Parsing (Single-Utterance Execution):** Owners can speak multiple mixed actions in one sentence (*"20 Maggi aayi, 10 Pepsi ki bottle aayi, 5 Maggi biki"*). The parser emits an ordered list of typed operations (`max_items = 25`), executes unambiguous items sequentially in order (so stock received earlier in the same sentence is available for a sale later in the sentence), and prompts only for any ambiguous or missing-slot items in the batch.
   - **Safety Guardrails:** Negative stock is **blocked by default** (asks clarification), and single transactions **`>= ₹5,000`** require explicit final confirmation.
5. **Subscription-Based SaaS Model (`Free`, `Growth`, `Pro` Tiers)**
   - **Free Tier:** Immediately usable out-of-the-box without payment so any owner can test Cue within tier quotas.
   - **Growth & Pro Tiers:** Unlock expanded limits (staff seats, monthly voice transactions, multi-store support) with configurable DB flags and no fixed prices hardcoded yet.
6. **Day-Grouped Chat History & 30-Day Rolling Memory Window**
   - **One Chat = One Business Day:** Every voice/text turn on a calendar day (`Asia/Kolkata`) belongs to **one continuous daily thread** (`UNIQUE (business_id, conversation_date)`), synced across reloads/devices.
   - **30-Day Retrieval Window:** Cue retrieves conversation turns and ledger records across the **past 30 days (1 month)** (e.g., *"Kal jo Pepsi aayi thi, wo expired thi"* resolves yesterday's chat + Pepsi receipt and executes an accurate linked expiry deduction).
   - **> 30 Days Boundary:** Referencing conversational context older than 30 days triggers a clear, polite boundary explanation directing the user to permanent **Reports / Ledger** views.

---

## 2. Hardcore Security Model: "AI as Untrusted Parser, Never Executor"

**Core Security Law:** The AI model has **zero execution authority**. It never runs tasks, never touches the database, never generates SQL, and never accesses system/network tools.

### 2.1 Four-Layer Security Architecture

1. **Layer 1 — Transport, Auth & Tenant Isolation**
   - **Verified JWT Auth:** Every API route validates the Supabase JWT (`sub` = `auth.uid()`, signature, `exp`, `aud`).
   - **Never Trust Client/LLM IDs:** `user_id` and `business_id` are resolved strictly from the verified JWT + `business_members` membership check on the server—never accepted from LLM output or spoofable payload fields.
   - **Supabase RLS Everywhere:** Every table enforces Row Level Security (`business_id IN (SELECT business_id FROM business_members WHERE user_id = auth.uid())`).
   - **Rate Limiting & Upload Hardening:** Sliding-window rate limits per user/IP, strict audio MIME + magic-byte inspection (`webm`, `ogg`, `wav`, `mp4`), max audio size (`10 MB` / `90s`), strict CORS origin allowlist, security headers (`CSP`, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`), and **PII-redacted structured logs** (never log JWTs, API keys, or customer phone numbers).

2. **Layer 2 — Untrusted AI Sandboxing & Prompt-Injection Defense**
   - **Strict Separation:** Transcript text is wrapped inside explicit untrusted delimiters (`<user_utterance>...</user_utterance>`) and the AI only receives **minimal read-only context** (matched catalog candidate names/IDs + 30-day relevant summary), never raw secrets or unrelated tenant data.
   - **Strict Pydantic v2 Schema Firewall (`extra="forbid"`):** LLM output is parsed into an allowlisted `IntentProposal` schema with strict enums, regex-checked IDs/dates, bounded array lengths (e.g., max 25 items in Business Day Replay), and numeric bounds. Invalid or malformed outputs are rejected immediately.

3. **Layer 3 — Capability Firewall (`SecurityPolicyEngine`)**
   - **Zero Destructive Intents:** The voice/AI intent registry **does not contain** any delete, wipe, drop, bulk-reset, schema, user-management, or export intents. Requests like *"Saara data delete kar do"* are deterministically blocked with `POLICY_BLOCKED`.
   - **Append-Only Immutable Financial & Stock Ledger:** No transaction row (`sales`, `inventory_movements`, `expenses`, `customer_payments`) is ever hard-deleted. Corrections and undo actions execute **compensating reversal entries** linked via `parent_id` / `reference_id` and record an immutable JSON `audit_trail`.
   - **Risk-Tiered Execution Gate:**
     - **Tier 1 (Auto-Execute):** Clear, unambiguous, within normal quantity/rupee bounds (e.g., `+20 Pepsi`, `-3 damaged`, `₹120 sale`).
     - **Tier 2 (Clarify — Zero Mutation):** Ambiguous product/customer, unit mismatch, missing quantity/price, or `> 30 days` memory reference.
     - **Tier 3 (Explicit Confirmation Required):** High-value thresholds (configurable, e.g., `> ₹10,000` or `> 5x` item average), cross-day reversals/corrections, negative-stock overrides, or customer overpayments. Generates a short-lived, server-signed/DB-persisted **`confirmation_token`** bound to `(business_id, user_id, operation_id, payload_sha256)` so the confirmed action cannot be tampered with.

4. **Layer 4 — Database Atomicity, Concurrency & Idempotency**
   - **Atomic PostgreSQL RPC Functions:** Multi-table mutations (e.g., `sale` + `sale_items` + `inventory_movements` + `inventory` update + `customers.outstanding_balance` + `voice_transactions`) run inside a single ACID database transaction.
   - **Row-Level Locking (`SELECT ... FOR UPDATE`):** Prevents concurrent stock corruption when two commands or two devices update the same SKU simultaneously.
   - **Strict Idempotency (`operation_id` + `payload_hash`):** Client generates UUID `operation_id` per voice command. DB enforces `UNIQUE (business_id, operation_id)`. Identical retries return the cached result; mismatched payloads for an existing `operation_id` return `409 Conflict`.

---

## 3. Comprehensive Edge-Case & Real-World Foresight Matrix

| Domain | Scenario / Failure Mode | Planned System Handling |
| :--- | :--- | :--- |
| **Speech & Audio** | Background kirana noise, horn, mic cut-off, <0.4s tap, silence | Web Audio RMS check on client + Whisper `no_speech_prob` / min-length check on backend → immediate retry prompt without wasting LLM quota or touching DB. |
| **Speech & Audio** | Unclear quantity (*"Kuch Pepsi aayi"*) or partial speech | Ask **only** for the unclear portion (*"Kitni Pepsi bottles aayi hain?"*) while keeping the resolved product in `pending_clarification`. |
| **Language & Numbers** | Hinglish fractions & local units (*"pav kilo"*, *"dedh litre"*, *"aadha peti"*, *"2 darjan"*) | Deterministic `indian_numbers` + `unit_converter` normalizes `pav=0.25`, `aadha=0.5`, `dedh=1.5`, `dhai=2.5`, `darjan=12`, and maps `nag/bottle/pcs→piece`, `pkt→packet`, `peti/carton→box`. |
| **Unit Conversion** | Product tracked in `kg`, user says *"500 gram cheeni bechi"* | `unit_converter` converts `500g → 0.5 kg`. If units are incompatible (e.g., *"2 litre Maggi"*), rejects mutation and asks for unit clarification. |
| **Catalog Disambiguation** | *"Pepsi"* matches `"Pepsi 500ml"` & `"Pepsi 2L"` | Never guesses; returns `needs_clarification` with selectable chips and asks verbally. |
| **Unlisted Product / Customer** | Owner mentions a brand-new item or new customer | Offers a safe one-tap / voice-confirmed **Create New Product / Customer** proposal rather than failing or silently creating bad records. |
| **Stock & Credit Invariants** | Selling 15 units when only 8 are in stock | Blocks silent negative stock; informs owner (*"Stock mein sirf 8 bachi hain"*) and asks to confirm adjustment or correct quantity. |
| **Duplicate Customer Names** | Multiple customers named `"Ramesh"` | Disambiguates using phone last-4 digits, area tag, or current `outstanding_balance`. |
| **Midnight & Timezone** | Entry made at 12:15 AM IST referring to *"aaj"* or *"kal"* | All business dates use `businesses.timezone` (`Asia/Kolkata`), strictly separating `transaction_date` (business date) from `created_at` (UTC audit timestamp). |
| **Offline / Weak 4G** | Internet drops mid-shift or while syncing | Audio blob + `operation_id` + `conversation_date` stored in browser `IndexedDB`; UI shows `Pending Sync`; FIFO sync replays sequentially on reconnect (preserving `"20 Pepsi"` before `"Unmein se 3 damaged"`). |
| **Multi-Device / Staff** | Owner + staff open Cue on two devices on the same day | Both load the same daily conversation (`conversation_date`), protected by RLS and `SELECT ... FOR UPDATE` stock locks. |
| **30-Day Memory vs Older** | *"Kal..."* (Day -1) vs *"Do mahine pehle..."* (Day -60) | Day -1 to -30 retrieved from `conversation_messages` + ledger tables; >30 days triggers graceful boundary message pointing to Reports/Ledger. |
| **Browser Differences** | Safari/iOS vs Chrome/Edge codecs & missing TTS voices | `MediaRecorder` codec negotiation (`audio/webm;codecs=opus` → `audio/webm` → `audio/mp4`); `SpeechSynthesis` picks `hi-IN` / `en-IN` with graceful silent text fallback + full text input fallback if mic is blocked. |

---

## 4. Enterprise Database Architecture (Supabase PostgreSQL + RLS)

All migrations live in `backend/app/db/migrations/` (numbered `001_schema.sql`, `002_rls_and_security.sql`, `003_atomic_rpcs.sql`, `004_seed_kirana.sql`):

1. **`businesses`** — `id`, `owner_id`, `name`, `timezone` (`'Asia/Kolkata'`), `preferred_language` (`'hinglish'|'hi'|'en'`), `currency` (`'INR'`), `settings` (`jsonb`: `allow_negative_stock`, `high_value_confirm_inr`), `created_at`.
2. **`business_members`** — `id`, `business_id`, `user_id`, `role` (`'owner'|'manager'|'staff'`), `is_active`, `created_at` *(enables safe multi-staff access without future schema rewrites)*.
3. **`products`** — `id`, `business_id`, `sku_code`, `name`, `normalized_name`, `category`, `base_unit` (`piece|packet|kg|litre|box`), `default_cost_price`, `default_selling_price`, `low_stock_threshold`, `is_active`, `created_at`, `updated_at`.
4. **`product_aliases`** — `id`, `business_id`, `product_id`, `alias_text`, `normalized_alias`, `language`, `created_at` *(unique per business + normalized_alias)*.
5. **`product_unit_conversions`** — `id`, `business_id`, `product_id`, `from_unit` (e.g. `box`/`peti`), `to_base_multiplier` (e.g. `24`) *(supports *"1 peti Pepsi"* → `+24 pieces`)*.
6. **`inventory`** — `id`, `business_id`, `product_id`, `current_quantity`, `updated_at` (`UNIQUE(business_id, product_id)`).
7. **`inventory_movements`** — Immutable ledger: `id`, `business_id`, `product_id`, `movement_type` (`receive|sale|damage|expiry|adjustment|reversal`), `quantity_delta`, `unit`, `unit_cost`, `reference_type`, `reference_id`, `operation_id`, `transaction_date`, `notes`, `created_by`, `created_at`.
8. **`customers`** — `id`, `business_id`, `name`, `normalized_name`, `phone`, `area_note`, `outstanding_balance`, `is_active`, `created_at`, `updated_at`.
9. **`sales`** — `id`, `business_id`, `customer_id`, `total_amount`, `paid_amount`, `payment_status` (`paid|partial|credit`), `transaction_date`, `status` (`active|corrected|voided`), `parent_sale_id`, `operation_id`, `notes`, `created_by`, `created_at`.
10. **`sale_items`** — `id`, `sale_id`, `product_id`, `quantity`, `unit`, `unit_price`, `line_total`.
11. **`customer_payments`** — `id`, `business_id`, `customer_id`, `amount`, `payment_method`, `transaction_date`, `status`, `parent_payment_id`, `operation_id`, `notes`, `created_by`, `created_at`.
12. **`expenses`** — `id`, `business_id`, `category`, `description`, `amount`, `payment_method`, `transaction_date`, `status` (`active|corrected|voided`), `parent_expense_id`, `operation_id`, `created_by`, `created_at`.
13. **`conversations`** *(Day-Grouped Threads)* — `id`, `business_id`, `conversation_date` (`date`), `title`, `daily_summary`, `context_state` (`jsonb`), `created_at`, `updated_at` — **`UNIQUE (business_id, conversation_date)`**.
14. **`conversation_messages`** — `id`, `conversation_id`, `business_id`, `conversation_date`, `role` (`user|assistant|system_card`), `content`, `language`, `linked_operation_id`, `ui_payload` (`jsonb`), `created_at` *(indexed on `(business_id, conversation_date DESC, created_at ASC)` for fast 30-day lookup)*.
15. **`voice_transactions`** — `id`, `business_id`, `conversation_id`, `operation_id`, `payload_hash`, `transaction_date`, `raw_transcript`, `detected_language`, `stt_provider`, `stt_confidence`, `parsed_intent` (`jsonb`), `validation_status`, `risk_tier`, `affected_records` (`jsonb`), `audit_trail` (`jsonb`), `created_by`, `created_at` — **`UNIQUE (business_id, operation_id)`**.
16. **`pending_confirmations`** — `id`, `business_id`, `user_id`, `operation_id`, `token_hash`, `proposed_action` (`jsonb`), `expires_at`, `consumed_at`, `created_at` *(hardcore security gate for Tier-3 actions)*.
17. **`business_insights_events`** *(Section 10 BI Foundation)* — `id`, `business_id`, `product_id`, `event_type` (`low_stock_crossed|velocity_spike|unusual_sale`), `metric_date`, `payload` (`jsonb`), `created_at`.
18. **`subscription_plans`** — `id`, `code` (`starter|growth|pro`), `display_name`, `description`, `price_display` (nullable / placeholder until pricing is finalized), `limits` (`jsonb`: `max_staff`, `monthly_voice_turns`, `max_stores`, `replay_enabled`), `is_active`, `created_at`.
19. **`business_subscriptions`** — `id`, `business_id`, `plan_id`, `status` (`trialing|active|past_due|canceled`), `current_period_start`, `current_period_end`, `provider_ref`, `created_at`, `updated_at`.

---

## 5. Bespoke UI/UX Design Language (Non-AI-Generic, Alive & Minimal)

Instead of generic SaaS templates, purple gradients, or cluttered dashboard grids, Cue uses a **"Warm Ledger & Studio Voice"** aesthetic crafted for Indian shopkeepers:

- **Color System (High-Contrast Warm Light Theme):**
  - Canvas: Warm Alabaster / Paper (`#FAF8F5`)
  - Elevated Surface: Crisp White (`#FFFFFF`) with hairline warm stone borders (`#E7E2DA`)
  - Primary Ink: Deep Charcoal (`#171614`), Muted Ink (`#6B655E`)
  - Living Voice Accent: **Terracotta / Ledger Vermilion (`#D95D39`)** — inspired by traditional Indian *bahi-khata* ink; glows and pulses *only* around active voice states.
  - Semantic Statuses: Forest Sage (`#1E6B52`) for verified stock/revenue, Warm Amber (`#B7791F`) for clarification/pending sync, Crimson (`#C53030`) for errors/blocked policies.
- **Typography:**
  - `Plus Jakarta Sans` + `Noto Sans Devanagari` for razor-sharp Hinglish/Hindi readability.
  - `JetBrains Mono` / `tabular-nums` on every rupee amount, stock count, and invoice/movement delta so figures read like a precision ledger.
- **Spatial Layout & Alive Voice-First Interaction:**
  1. **Left Rail (Calm Navigation + 30-Day Daily Ledger Strip):**
     - Business switcher/header, clean views (**Voice Desk**, **Stock**, **Sales**, **Udhaar**, **Expenses**, **Replay & Reports**), and the **30-Day Daily Chat List** (`Today`, `Yesterday`, ..., `30d window`).
  2. **Center Stage — The Voice Desk (Default Home):**
     - **Conversational Ledger Stream:** Spoken turns + Cue’s responses rendered alongside **tactile Paper-Slip Receipt Cards** showing exact diffs (`Pepsi 500ml  +20 → -3 = +17 net`, `₹1,240 Cash`, `Audit #op-8f2a`) with instant **Undo**, **Edit**, or **Tap-to-Clarify** pills.
     - **Living Tactile Mic Dock (Bottom Anchor):** A sculptural, minimal voice bar with a live Web Audio frequency ring/waveform (`AnalyserNode`), keyboard shortcut (`Space` / `Ctrl+M`), explicit state indicator (`Listening` → `Transcribing` → `Validating` → `Saved` / `Needs Clarification` / `Confirm Required` / `Pending Sync`), language switcher (`Hinglish` | `Hindi` | `English`), TTS voice toggle, and discreet text fallback.
  3. **Right Pulse Strip (Desktop-First Live Feedback):**
     - Unobtrusive live **"Today's Ledger Pulse"** (Today's Sales ₹, Udhaar Given/Collected, Movements Count, Low-Stock Watch) that animates subtly the instant a voice command commits to Supabase.

---

## 6. Enterprise Folder Architecture

```text
cue/
├── IMPLEMENTATION_PLAN.md
├── FEATURES.md                            # Master living feature checklist (Done vs Pending)
├── README.md
├── .gitignore                             # Strict secret, .env, key & media exclusion
├── backend/
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── .env.example
│   ├── app/
│   │   ├── main.py                        # FastAPI app, CORS, security headers, middleware
│   │   ├── api/
│   │   │   ├── deps.py                    # Verified JWT user + business_id resolution
│   │   │   └── v1/
│   │   │       ├── router.py
│   │   │       ├── voice.py               # /voice/turn, /voice/confirm, /voice/clarify, /voice/sync-batch
│   │   │       ├── conversations.py       # 30-day day-grouped chat endpoints
│   │   │       ├── subscriptions.py       # Free / Growth / Pro plan catalog & store onboarding
│   │   │       ├── inventory.py           # Products, aliases, unit conversions, movements
│   │   │       ├── sales.py               # Sales, corrections, returns
│   │   │       ├── customers.py           # Udhaar ledger & repayments
│   │   │       ├── expenses.py            # Daily shop expenses
│   │   │       ├── reports.py             # Daily summary, replay history, audit trail, BI hooks
│   │   │       └── health.py              # Readiness & provider health
│   │   ├── core/
│   │   │   ├── config.py                  # Strict Pydantic Settings
│   │   │   ├── security.py                # Supabase JWT verification, rate limiter, payload hashing
│   │   │   ├── policy.py                  # SecurityPolicyEngine (zero destructive intents, ₹5,000 threshold, confirmation tokens)
│   │   │   ├── entitlements.py            # Subscription tier quota & feature checks
│   │   │   ├── time_utils.py              # Business timezone (Asia/Kolkata) & relative date parser + >30d check
│   │   │   ├── logging.py                 # Structured PII-safe logging
│   │   │   └── exceptions.py              # Typed domain & security error codes
│   │   ├── db/
│   │   │   ├── supabase.py                # Scoped Supabase & PostgreSQL connection manager
│   │   │   ├── migrations/
│   │   │   │   ├── 001_schema.sql
│   │   │   │   ├── 002_rls_and_security.sql
│   │   │   │   ├── 003_atomic_rpcs.sql
│   │   │   │   ├── 004_seed_kirana.sql
│   │   │   │   └── 005_subscriptions_seed.sql
│   │   │   └── repositories/              # Pure parameterized data access per entity
│   │   ├── domain/
│   │   │   ├── schemas/                   # Strict Pydantic v2 IntentProposal, Replay, API DTOs (extra='forbid')
│   │   │   ├── indian_numbers.py          # Hinglish/Hindi numeric & fraction parser (pav, aadha, dedh, darjan)
│   │   │   ├── unit_converter.py          # Standard & per-product unit conversions
│   │   │   └── invariants.py              # Stock, credit, & monetary validation rules
│   │   ├── providers/
│   │   │   ├── stt/
│   │   │   │   ├── base.py
│   │   │   │   ├── groq_whisper.py        # Zero-PC-load free cloud Whisper
│   │   │   │   ├── faster_whisper.py      # Optional self-hosted local Whisper
│   │   │   │   ├── gemini_audio.py        # Free Gemini audio fallback
│   │   │   │   └── indic_conformer.py     # Modular AI4Bharat adapter
│   │   │   └── llm/
│   │   │       ├── base.py
│   │   │       ├── gemini.py              # Primary Gemini Free Tier parser (read-only JSON output)
│   │   │       └── ollama.py              # Optional local Ollama parser
│   │   └── services/
│   │       ├── voice_pipeline.py          # End-to-end orchestrator
│   │       ├── memory_30d.py              # Day-chat + 30-day historical retrieval + >30d guard
│   │       ├── entity_resolver.py         # Alias + fuzzy matching + ambiguity detection
│   │       ├── transaction_engine.py      # Atomic execution, corrections, undo, audit trail
│   │       ├── replay_engine.py           # Business Day Replay batch extraction & summary
│   │       ├── query_engine.py            # Read-only business analytics queries
│   │       └── analytics_foundation.py    # Section 10 BI event collector & predictive stubs
│   └── tests/
│       ├── unit/
│       ├── security/                      # Prompt injection, destructive blocking, idempotency, tenant isolation
│       └── integration/
└── frontend/
    ├── package.json
    ├── .env.local.example
    └── src/
        ├── app/
        │   ├── layout.tsx                 # Fonts, Warm Ledger theme, Auth & Sync providers
        │   ├── page.tsx                   # Voice Desk (Conversational Home)
        │   ├── login/page.tsx             # Supabase Auth (Email/Password + Google OAuth)
        │   ├── onboarding/page.tsx        # Subscription tier selection (Free/Growth/Pro) + Store setup
        │   ├── inventory/page.tsx
        │   ├── sales/page.tsx
        │   ├── customers/page.tsx
        │   ├── expenses/page.tsx
        │   └── reports/page.tsx           # Business Day Replay, Summaries & Audit Trail
        ├── components/
        │   ├── layout/                    # AppShell, DayChatSidebar, TodayPulsePanel
        │   └── ui/                        # LedgerTable, Amount, StatusPill, ConfirmDrawer
        ├── features/
        │   ├── voice/                     # LivingMicOrb, AudioWaveform, TranscriptStream, ReceiptSlipCard, ClarificationChips, NewEntityPopup
        │   ├── offline/                   # OfflineSyncBanner, SyncEngine
        │   └── ledger/                    # Inventory, Sales, Customers, Expenses, Replay components
        └── lib/
            ├── api.ts                     # Typed API client with operation_id & retry logic
            ├── supabase.ts                # Supabase browser auth client
            ├── offlineQueue.ts            # IndexedDB FIFO queue
            └── tts.ts                     # SpeechSynthesis hi-IN / en-IN engine
```

---

## 7. GitHub Workflow & Phased Build Checklist

- **Milestone Commits:** Every major completed milestone is verified (tests/build + secret-scan via `git status` & `git diff --cached` ensuring zero `.env` or secret exposure), updated in `FEATURES.md`, and committed + pushed to GitHub.
- **Step-by-Step Secret Onboarding:** Credentials are collected one-by-one (1. GitHub remote → 2. Supabase Free Tier → 3. Google Gemini Free Tier → 4. Groq Free Whisper) and placed strictly in git-ignored `.env` files.

1. **Phase 1 — Foundation & Database (Hardcore Security First):**
   - Initialize `backend/` & `frontend/` workspaces, `.env.example` files, and SQL migrations (`001_schema.sql` → `005_subscriptions_seed.sql`) with RLS, `SELECT ... FOR UPDATE` atomic RPCs, subscription tiers, and kirana seed data.
2. **Phase 2 — Secure Backend Pipeline & 30-Day Memory Engine:**
   - Implement `SecurityPolicyEngine`, `STTProvider` (`groq_whisper` default + adapters) + `LLMProvider` (`gemini` primary + `ollama` optional), `memory_30d`, `entity_resolver` (`"Do you mean?"` + verified alias learning + new-entity pop-up payload), `transaction_engine`, `replay_engine`, and `analytics_foundation`.
   - Write automated unit + security test suite (destructive-intent blocking, prompt-injection resilience, idempotency, negative-stock block, ₹5,000 threshold, 30-day window boundaries).
3. **Phase 3 — Bespoke Voice-First Frontend:**
   - Implement the "Warm Ledger & Studio Voice" UI, Supabase Email/Password + Google OAuth login, subscription tier onboarding, `LivingMicOrb` (`MediaRecorder` + Web Audio waveform), `SpeechSynthesis` replies, 30-day daily chat rail, tactile `ReceiptSlipCard`s, voice/tap-confirmable `NewEntityPopup`, `IndexedDB` FIFO offline queue, and all ledger/report sections.
4. **Phase 4 — End-to-End Live Verification:**
   - Run backend security/unit tests, Next.js TypeScript/production build check, and live end-to-end voice workflows against Supabase + Gemini + Groq Whisper.
