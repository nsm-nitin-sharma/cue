# Cue – Master Product Feature Tracker

> **Purpose:** Living source of truth for every discussed feature, UI/UX enhancement, security control, bug fix, and upcoming capability in **Cue**.  
> **Legend:** `[x]` Implemented & Verified | `[~]` Foundation / Schema Ready (UI or Integration Pending) | `[ ]` Not Implemented Yet  
> **Last Updated:** 2026-11-27 (Branch `AI`)

---

## 1. Project Foundation, GitHub & Hardcore Security

- [x] Git workflow on branch `AI` (never commit secrets/`.env` files; strict `.gitignore`)
- [x] Enterprise architecture & engineering blueprint ([IMPLEMENTATION_PLAN.md](file:///c:/Users/nitin/OneDrive/Documents/cue/IMPLEMENTATION_PLAN.md))
- [x] Verify Supabase JWT (`auth.uid()`) on every API route (`deps.py` + `security.py`); never trust client/LLM-supplied `user_id` or `business_id`
- [x] Enforce Supabase Row Level Security (RLS) across all business tables (`002_rls_and_security.sql` live in Supabase)
- [x] Lightweight PostgREST Supabase client supporting `sb_secret` keys & Windows `tzdata` `Asia/Kolkata` timezone safety
- [x] **AI-as-Untrusted-Parser Sandboxing:** LLM has zero DB, SQL, shell, or task-execution authority; outputs strict JSON only
- [x] **Pydantic v2 Schema Firewall (`extra="forbid"`):** Strict enum-locked intents, regex-checked IDs/dates, bounded quantities, `cost_price`/`selling_price` support, & array limits
- [x] **Zero Destructive Intents (`SecurityPolicyEngine`):** No AI/voice intents for delete, wipe, drop, or bulk reset (`POLICY_BLOCKED`)
- [x] **Append-Only Immutable Ledger:** Corrections/reversals insert compensating entries + `status="corrected"` / `status="voided"` + immutable `audit_trail` (no hard deletes)
- [x] **3-Tier Execution Gate:** Auto-execute safe actions, clarify on doubt, confirm Tier-3 actions via cryptographic `pending_confirmations` token
- [x] **`₹5,000` High-Value Confirmation Threshold:** Single transactions `>= ₹5,000` or cross-day reversals require explicit Voice or UI confirmation
- [x] **Negative Stock Blocking:** Prevent silent negative stock by default; catch `INSUFFICIENT_STOCK` cleanly and prompt owner in Hinglish instead of server crashes
- [x] **Atomic PostgreSQL RPCs + `SELECT ... FOR UPDATE`:** Applied in Supabase (`003_atomic_rpcs.sql`)
- [x] **Strict Idempotency:** Client UUID `operation_id` + `payload_hash` enforced via `UNIQUE (business_id, operation_id)` and `409 Conflict` check
- [x] **API, CORS & ASGI Error Shield (`main.py`):** `SecurityAndErrorShieldMiddleware` wrapped *inside* `CORSMiddleware` (allowing `GET`, `POST`, `PATCH`, `DELETE`, `OPTIONS`), audio MIME/magic-byte validation, rate limiting, security headers, and PII-redacted logs

---

## 2. Authentication, Onboarding & Subscription SaaS

- [x] **Email + Password** signup & login via Supabase Auth (with duplicate signup protection)
- [x] **Google OAuth** login via Supabase Auth (UI + callback wired; existing-store users bypass onboarding cleanly)
- [x] **Auth Route Guarding:** Signed-in users visiting `/login` automatically redirect to the Voice Desk
- [x] **Store-First Identity Popover (Top-Right Header):** Prioritizes **Store Name** in a crisp dropdown pill revealing signed-in owner details (`email`) and **Sign Out** cleanly inside the menu
- [x] **Store Onboarding (`/onboarding`):** Clean empty store by default (zero preloaded fake items unless the owner explicitly opts in to sample kirana data)
- [x] **Subscription Tiers (`Starter/Free`, `Growth`, `Pro`):**
  - [x] `Free` tier active out-of-the-box (`250/mo` voice quota, no payment required)
  - [x] DB-driven tier entitlements & quota enforcement (`entitlements.py` + `004_seed_plans.sql`)
- [x] **Account Deletion & Store Reset (`DELETE /api/v1/account`):** Owner-confirmed (`Type DELETE`) account & store reset
- [~] Multi-staff RBAC (`business_members` table & RLS ready; staff invitation & role management UI pending — see Section 10)
- [ ] Paid Billing Checkout (Razorpay / Stripe upgrade flow for `Growth` & `Pro` — see Section 10)

---

## 3. Voice Pipeline & Modular AI/Speech Stack (100% Free)

- [x] Browser `MediaRecorder` capture with cross-browser codec negotiation (`webm/opus` → `webm` → `mp4`)
- [x] **Hardware Noise Cancellation + Acoustic Filtering:** `echoCancellation`, `noiseSuppression`, `autoGainControl` + Web Audio waveform
- [x] **Live Real-Time Voice Captions:** Shows spoken words live via Web Speech `interimResults` while recording (`Space` hold/toggle or mic button click)
- [x] **Cancel Recording Mid-Speech:** Cancel button + `Escape` shortcut discards unwanted/mistaken recordings immediately without queueing or sending to AI
- [x] **Background Shop Chatter & Conflict Guard:** Isolates owner intent from bystander chatter; triggers `needs_clarification` on ambiguity or low confidence (`< 0.85`)
- [x] **Natural Neural Voice (`edge-tts` Indian Neural Voices) + Browser Fallback:** Streams Indian English (`en-IN-NeerjaExpressiveNeural`) & Hindi (`hi-IN-SwaraNeural`) speech with instant mute & replay controls
- [x] **Voice Barge-In / Auto-Stop TTS:** Cue immediately stops speaking whenever the user starts speaking or triggers the mic
- [x] **Audio Fetch Resilience:** Transient network retry in `apiFetch` + automatic live `fallbackTranscript` execution in `submitAudioTurn` if audio upload encounters network errors
- [x] **Modular `STTProvider` Interface:**
  - [x] Default: **Groq Free Tier Whisper (`whisper-large-v3-turbo`)** (zero PC load)
  - [x] Optional adapters: `faster-whisper` (local CPU), Google Gemini Audio, AI4Bharat `IndicConformer`
- [x] **Modular `LLMProvider` Interface:**
  - [x] Primary: **Google Gemini API (Free Tier)** with model fallback & deterministic Hinglish/English fallback parser (`deterministic_fallback_parse`)
  - [x] Optional local adapter: Ollama (disabled by default)
- [x] **Strict Selected-Language Pipeline (STT + Reply + TTS):** Locking Settings to **English**, **Hindi**, or **Hinglish** enforces matching speech recognition (`Groq Whisper` tailored prompts + deterministic Devanagari→Latin Romanizer `romanize_devanagari_to_hinglish` for Hinglish), strict reply localization (`i18n_replies.py`), and matching neural voice output (`en-IN-NeerjaExpressiveNeural` vs `hi-IN-SwaraNeural`)
- [x] **Scoped Corrections & Damage/Expiry/Receive Amendments:** Every committed action (`record_sale`, `record_expense`, `inventory_damage`, `inventory_expiry`, `inventory_receive`, `record_udhaar_credit`, `record_customer_payment`) updates `last_operation_kind` so follow-up fixes (`"Sorry, 2 damage thay"`, `"2 damaged the, ek nahi"`, `"do nahi, bas ek hi demis tha"`) never misroute into older expenses or sales; uses append-only reversal+replacement entries and excludes reversed movements from Damaged/Expired loss totals.
- [x] **Interactive Cue Mascot Voice Core (`CueMascot.tsx`, `LivingAcousticOrb.tsx`):** Clean monochrome voice orb with an animated Cue character across four states — **Idle** (peeking from bottom rim while hanging on with paws), **Typing** (looking upward into the command bar with real-time text-caret pixel coordinate eye & head tracking), **Listening** (springing up and cupping both hands on its ears with audio-reactive ripples), and **Thinking** (paw-on-chin head tilt + floating thought dots until results arrive), replacing the older red/blue gradient halo animations.
- [x] Hindi, English, and Hinglish code-switching + Indian kirana vocabulary support

---

## 4. Strict "Do You Mean This?" Clarification, Multi-Variant Disambiguation & Slot-Filling

- [x] **Multi-Variant Product Disambiguation (`entity_resolver.py`):**
  - [x] When speaking a generic/shared product name (e.g., `"Coke"` or `"Maggi masala"`) matches multiple SKUs (e.g., `Maggi Masala 70g` vs `Maggi Masala 250 Gram`), Cue pauses, displays all matching variants with stock & price pills in chat, and lets the user **tap a chip or speak the exact variant/size** while preserving `payment_method` (`Online` / `GPay` / `Cash`) & `Udhaar` customer context across the clarification
  - [x] **Alias-Safe Multi-Variant Check:** Multi-variant ambiguity is checked *before* older single-SKU verified aliases so adding a 2nd variant later (`Maggi Masala 250 Gram`) always restores disambiguation
  - [x] **LLM Over-Normalization & Repeated-Turn Disambiguation Guard:** Prevents AI from silently injecting an unspoken size (`70g`) or falling back to `Yes/No` confirmation chips when multiple variants exist across consecutive turns, ensuring product chips and Devanagari size replies (`"मेगी मसाला 70 gram"`) always resolve cleanly
  - [x] **Strict Size-Token Mismatch Guard & Packaging Stopword Isolation:** Explicit sizes (`250g` vs `70g`) never cross-match; unit-equivalent exact matching (`250g` == `250 gram`) works automatically; generic words (`packet`, `gram`, `bottle`) never falsely match unrelated products
  - [x] **Whisper Typo Tolerance & Size-Mismatch Clarification:** Handles common speech-to-text spelling variants (`"Maggie"` / `"Meggie"` / `"Maigi"` → matches Maggi SKUs without matching `"Garam Masala"`), and if a spoken size (`500g`) isn't in stock while similar-named variants exist (`250g`, `70g`), asks which existing variant you meant alongside an option to add the new SKU
- [x] **Verified Alias Learning (`product_aliases`):** Single fuzzy matches (`"Coke"` → `"Coca-Cola 750ml"`) ask *"Do you mean Coca-Cola 750ml?"*; confirming saves the alias in Supabase
- [x] **Duplicate Customer Disambiguation:** Disambiguates multiple customers with the same name using phone last-4 digits, area note, or outstanding balance (via voice or tap)
- [x] **Multi-Command Batch Execution (Single-Breath Operations):** Executes unambiguous commands in chronological order and holds any ambiguous/missing-slot item in `pending_batch_items`
- [x] **Brand-New Product Creation (Voice + Interactive Pop-up):** Missing products trigger `"Kya naya product add karun?"` + interactive `NewEntityPopup` (name, unit, qty, cost/selling price, threshold); confirmable via **either voice or screen button**, persisting the `New SKU Added` receipt to chat history
- [x] **Schema-Driven Multi-Turn Slot-Filling & Stale-Flow Abandonment:**
  - [x] Holds partial drafts cleanly when required fields (`purchase_price`, `selling_price`, `quantity`, `payment_method`) are missing
  - [x] **Weight-Never-Price Guard:** Size/weight specs (`70g`, `250 gram`) are never parsed as rupee prices or sale quantities
  - [x] **Abandon Stale Clarification on New Command:** Speaking a brand-new command or payment correction cleanly cancels stale `pending_flow` instead of hijacking the new intent
- [x] Hinglish numbers & fractions (`pav = 0.25`, `aadha = 0.5`, `dedh = 1.5`, `dhai = 2.5`, `darjan = 12`) + unit conversion (`piece/bottle` ↔ `packet/pouch` 1:1 countable compatibility, `500g → 0.5 kg`, incompatible cross-dimension rejection like `litre` ↔ `packet`)

---

## 5. Conversational Memory, Corrections, Reversals & Replay

- [x] **One Chat = One Business Day:** Continuous daily thread (`UNIQUE (business_id, conversation_date)` in `Asia/Kolkata`) synced across reloads
- [x] **Persistent Chat Receipts (`conversation_messages.ui_payload`):** Executed slips, `New SKU Added`, `Tier-3` confirmations, `Query Results`, and `Reversal` cards remain permanently visible in chat (never vanish on refresh or workspace re-sync)
- [x] **Cash ↔ Online ↔ Udhaar Payment Corrections (`correct_sale_payment` & expense corrections):**
  - [x] Phrases like `"Cash nahi online"`, `"Online nahi cash"`, `"cash nahi UBI se kia tha"`, and `"Last transaction cash se nahi online hua tha"` immediately update `last_sale_id` / `last_expense_id` via append-only audit trail (`status="corrected"`, `parent_sale_id` / `parent_expense_id`) without double-counting totals
  - [x] Clear payment-correction rescue ensures stale clarification prompts never block payment switches
- [x] **Quantity Corrections (`correct_sale_quantity` / expense amount edits):** Handles post-negation targets (*"20 pepsi nahi 10 hi biki"*, *"Actually 7 the"*) while ignoring product weight specs (`250 gram`) and keeping corrected sales `status="active"` so Today & Sales Ledger revenue immediately reflects the updated amount
- [x] **One-Tap Receipt Reversal (`POST /api/v1/operations/{operation_id}/reverse`):** Reverses active sales, expenses, payments, and stock movements cleanly while logging audit history
- [x] **30-Day Cross-Day Memory & `> 30 Days` Boundary Guard:** Queries last 30 days of chat + ledger; politely redirects `> 30 days` references to permanent Reports views
- [x] **Business Day Replay:** Daily narration, relative dates (`aaj`, `kal`, `parso`), `transaction_date` vs `created_at` separation

---

## 6. Core Business Ledger, Full CRUD UI & Reports

- [x] **Supabase Core Schema (`001_schema.sql`):** `businesses`, `business_members`, `products`, `product_aliases`, `product_unit_conversions`, `inventory`, `inventory_movements`, `customers`, `sales`, `sale_items`, `customer_payments`, `expenses`, `conversations`, `conversation_messages`, `voice_transactions`, `pending_confirmations`, `subscription_plans`, `business_subscriptions`, `business_insights_events`
- [x] **Voice & UI Inventory (`/inventory`):**
  - [x] Receive, Sale deduction, Damage/Expiry, Adjustment, Low-stock watch, Movement History, **Dedicated `Damaged / Expired` Loss Tab**, **Stock Queries** (*"Inventory mein kitni Coca-Cola hain?"*), & Soft-Archive
  - [x] **Add Product, Edit Product Modal (`PATCH /api/v1/inventory/products/{id}`), & Clear Unused Items**
- [x] **Voice & UI Sales (`/sales`):**
  - [x] Cash, Online (stored as `"upi"` in DB, displayed everywhere as `"Online"`), Partial, and Udhaar sales
  - [x] Sales Ledger filters (period / payment type), real-time profit & revenue summary (filtering strictly on `status === "active"`), **Item-Specific Sales Queries** (*"Aaj Maggie ki kitni sales hui?"*), and clear `"Cash"` / `"Online"` / `"Udhaar"` pills
- [x] **Voice & UI Khata (`/customers`):**
  - [x] Create customer, query balances, add direct Udhaar (*"Ramesh ke khate mein 500 likh do"*), collect repayments (`POST /api/v1/customers/payments`), per-customer Khata history view, & **Edit Customer Modal (`PATCH /api/v1/customers/{id}`)**
  - [x] **Udhaar Repayment → Sales & Revenue Inclusion (`record_customer_payment`):** Paying any Udhaar (via Voice or Khata UI) automatically FIFO-settles unpaid/partial `sales` rows (`Udhaar` → `Cash`/`Online`/`Partial`), converts prior-day/opening-balance repayments cleanly into Today's Collected Revenue & Sales totals without double-counting, and supports clean Reversal rollback
- [x] **Voice & UI Expenses (`/expenses`):**
  - [x] Categorized daily shop expenses, Voice & Manual expense entry (`POST /api/v1/expenses`), period filters, & **Edit Expense Modal (`PATCH /api/v1/expenses/{id}`)**
- [x] **Reports & Daily Replay (`/reports`):** Daily net revenue, collected cash/online, udhaar, expenses, stock velocity, & replay summaries

---

## 7. Bespoke Minimal UI/UX ("Warm Ledger & Studio Voice")

- [x] Warm light aesthetic (`Plus Jakarta Sans` + `Noto Sans Devanagari` + tabular monospace numerals)
- [x] **Separated Header Controls:** Distinct **Live Status** badge, **Today's Sales** ticker pill, **Store-First Account Popover**, and **Settings** toggle
- [x] **Pinned Floating Living Acoustic Orb:** Stays cleanly anchored at the bottom above scrolling chat history; features organic breathing/speaking rings, smooth vermilion hover cross-fade (`300ms`), live voice captions, cancel control, and an icon-only circular **`Keyboard`** button (`/` shortcut) right beside the orb (with Test Scenarios chip removed for a cleaner console)
- [x] **Tactile Paper-Slip Receipt Cards:** Instant `Reverse`, confirmation, and status badges directly in chat
- [x] **Smooth Directional Tab Transitions:** Clicking tabs or using two-finger horizontal swipes (`Voice ↔ Inventory ↔ Sales ↔ Khata ↔ Expenses ↔ Reports`) slides smoothly in the tab's direction (`420ms`), alongside smooth chat history & settings drawer transitions
- [x] **Two-Finger Horizontal Swipe Tab Navigation:** Swiping left/right with two fingers (on both laptop trackpads and touchscreens) smoothly slides between `Voice ↔ Inventory ↔ Sales ↔ Khata ↔ Expenses ↔ Reports`, with a directional preview badge and table horizontal-scroll protection
- [x] **Instant Bottom-Anchored Voice Desk:** Switching back to the Voice tab or changing conversation dates opens directly at the latest bottom messages via pre-paint positioning (smooth-scrolling only when new live messages arrive)
- [x] **Offline Connectivity Resilience:** Empty/silent audio rejection + Browser `IndexedDB` FIFO Offline Queue with automatic chronological sync on reconnect

---

## 8. Automated Testing & Verification

- [x] Security Tests (`test_security_and_policy.py`): Destructive-intent blocking, prompt-injection defense, Pydantic firewall, `₹5,000` confirmation gate, audio magic-byte validation, PII redaction (**6 tests passing**)
- [x] Domain & Resolver Tests (`test_domain_and_resolver.py`): Hinglish numbers/fractions, unit converter, 30-day memory guard, multi-variant disambiguation with existing aliases & LLM transcript guard, `70g nahi 250 gram` quantity exclusion, Cash ↔ Online corrections, batch parsing, expense/stock queries (**9 tests passing**)
- [x] Frontend Build & Typecheck: `npx tsc --noEmit` & `npm run build` clean (11/11 routes)

---

## 9. Pending / Not Implemented Yet (Roadmap)

- [ ] **End-to-End Live User Walkthrough:** Complete live verification by store owner across signup, email/OAuth login, onboarding, multi-variant voice sales, Cash ↔ Online corrections, edit modals, reversals, and account reset
- [ ] **Multi-Staff Team Management UI:** Invite staff/managers, assign roles (`owner`/`manager`/`staff`), and view per-staff audit attribution (`business_members` table already live)
- [ ] **Per-Product Unit Conversion Editor UI:** Manage custom pack-to-base multipliers (e.g., `1 peti = 24 pieces`) from `/inventory` (`product_unit_conversions` table & backend converter already live)
- [ ] **Section 10 Predictive Analytics & BI Dashboard:** Velocity spike detection, automated reorder suggestions, margin trend charts, and `business_insights_events` surfacing in `/reports` (beyond `analytics_foundation.py` stub)
- [ ] **Paid Subscription Checkout & Billing Webhooks:** Payment gateway integration (Razorpay/Stripe) for upgrading from `Free` to `Growth` / `Pro` tiers
- [ ] **Regional Language Packs (Phase 2):** Full prompt/UI/TTS support for Marathi, Gujarati, Tamil, Telugu, and Bengali alongside Hinglish/Hindi/English
- [ ] **WhatsApp Udhaar Reminders & Thermal/PDF Receipt Export:** One-tap WhatsApp payment reminder links and printable/PDF thermal bills
- [ ] **Direct Variant-Swap Reversal Shortcut:** Voice shortcut like `"Maggi 70g nahi 250g wali thi"` auto-reversing the prior sale and re-recording on the new SKU in one turn (currently safely guides owner to tap Reverse & re-speak)
