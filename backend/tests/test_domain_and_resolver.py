from datetime import date

from app.core.policy import PolicyBlockedError, SecurityPolicyEngine
from app.core.time_utils import check_memory_window_days, detect_over_30_day_reference
from app.domain.indian_numbers import (
    extract_post_negation_number,
    extract_post_negation_quantity,
    parse_indian_number,
)
from app.domain.schemas.intents import IntentProposal, VoiceOperationItem
from app.domain.unit_converter import convert_to_base_quantity
from app.providers.llm.gemini import deterministic_fallback_parse
from app.services.entity_resolver import (
    resolve_customer,
    resolve_product,
    resolve_product_guarded,
    resolve_short_variant_reply,
)
from app.services.query_engine import QueryEngine

PRODUCTS = [
    {"id": "p1", "name": "Pepsi 500ml", "base_unit": "piece"},
    {"id": "p2", "name": "Pepsi 2L", "base_unit": "piece"},
    {"id": "p3", "name": "Coca-Cola 750ml", "base_unit": "piece"},
    {"id": "p4", "name": "Maggi Masala 70g", "base_unit": "packet"},
]

ALIASES = [
    {"product_id": "p1", "alias_text": "chotti pepsi", "is_verified": True},
    {"product_id": "p4", "alias_text": "maggi", "is_verified": True},
]

CUSTOMERS = [
    {"id": "c1", "name": "Ramesh Gupta", "area_note": "Sector 4", "phone": "+91 98110 44210"},
    {"id": "c2", "name": "Ramesh Yadav", "area_note": "Station Road", "phone": "+91 98712 90344"},
]


def test_indian_numbers_and_post_negation_correction():
    assert parse_indian_number("dedh kilo") == 1.5
    assert parse_indian_number("2 darjan") == 24.0
    assert parse_indian_number("paanch sau") == 500.0
    assert extract_post_negation_number("20 pepsi nahi 10 hi biki") == 10.0
    assert extract_post_negation_number("Actually 7 the") == 7.0


def test_unit_converter_and_incompatible_rejection():
    qty, err = convert_to_base_quantity(quantity=500, spoken_unit="gram", base_unit="kg")
    assert qty == 0.5 and err is None

    # Discrete countable units (packet <-> piece) are 1:1 compatible
    qty_p2p, err_p2p = convert_to_base_quantity(quantity=2, spoken_unit="packets", base_unit="piece")
    assert qty_p2p == 2 and err_p2p is None
    qty_p2pkt, err_p2pkt = convert_to_base_quantity(quantity=3, spoken_unit="pieces", base_unit="packet")
    assert qty_p2pkt == 3 and err_p2pkt is None

    qty2, err2 = convert_to_base_quantity(quantity=2, spoken_unit="litre", base_unit="packet")
    assert qty2 is None and err2 is not None


def test_30_day_memory_window_guard():
    today = date(2026, 11, 27)
    ok_29, _ = check_memory_window_days(date(2026, 10, 29), today, 30)
    too_old, _ = check_memory_window_days(date(2026, 10, 15), today, 30)
    assert ok_29 is True
    assert too_old is False

    assert detect_over_30_day_reference("Do mahine pehle kuch aisa hua tha") == 60
    assert detect_over_30_day_reference("45 days ago what happened?") == 45
    assert detect_over_30_day_reference("Kal jo Pepsi aayi thi, wo expired thi") is None


def test_zero_guessing_entity_resolver():
    # "Coke" not yet in verified aliases -> must ask "Do you mean Coca-Cola 750ml?"
    coke_res = resolve_product("Coke", PRODUCTS, ALIASES)
    assert coke_res.status == "verify_alias"
    assert coke_res.product["id"] == "p3"

    # "chotti pepsi" IS a verified alias -> exact!
    chotti_res = resolve_product("chotti pepsi", PRODUCTS, ALIASES)
    assert chotti_res.status == "exact"
    assert chotti_res.product["id"] == "p1"

    # "Pepsi" matches 500ml & 2L -> ambiguous!
    pepsi_res = resolve_product("Pepsi", PRODUCTS, ALIASES)
    assert pepsi_res.status == "ambiguous"
    assert len(pepsi_res.candidates) == 2

    # Short reply "500ml" resolves ambiguity without repeating full sentence!
    short_match = resolve_short_variant_reply("500ml", pepsi_res.candidates)
    assert short_match["id"] == "p1"

    # Unlisted item -> not_found (triggers pop-up)
    new_res = resolve_product("Nescafe Gold", PRODUCTS, ALIASES)
    assert new_res.status == "not_found"

    # Duplicate Ramesh -> ambiguous
    cust_res = resolve_customer("Ramesh", CUSTOMERS)
    assert cust_res.status == "ambiguous"
    assert len(cust_res.candidates) == 2


def test_multi_command_single_breath_parsing():
    proposal = deterministic_fallback_parse("20 Maggi aayi, 10 Pepsi ki bottle aayi, aur 5 Maggi biki", "hinglish")
    assert len(proposal.operations) == 3
    assert [op.intent for op in proposal.operations] == ["inventory_receive", "inventory_receive", "record_sale"]
    assert proposal.operations[0].quantity == 20
    assert proposal.operations[1].quantity == 10
    assert proposal.operations[2].quantity == 5


def test_intent_priority_noise_guard_and_crud_intents():
    noisy = IntentProposal(
        detected_language="hinglish",
        confidence=0.62,
        has_ambiguity_or_noise_conflict=True,
        clarification_question="Background mein doosri awaaz aayi — kya aap 20 Maggi bikne ki baat kar rahe hain?",
        operations=[VoiceOperationItem(intent="record_sale", product_query="Maggi", quantity=20)],
    )
    assert noisy.has_ambiguity_or_noise_conflict is True
    assert noisy.confidence < 0.85
    assert noisy.clarification_question is not None

    for intent in [
        "create_customer",
        "update_customer",
        "record_udhaar_credit",
        "update_product_settings",
        "archive_product",
    ]:
        SecurityPolicyEngine.assert_allowed_intent(intent)

    try:
        SecurityPolicyEngine.assert_allowed_intent("delete_database")
        assert False, "Expected PolicyBlockedError for destructive intent"
    except PolicyBlockedError:
        pass


def test_query_engine_stock_check():
    qe = QueryEngine(db=None)
    stock_products = [
        {"id": "p4", "name": "Maggi Masala 70g", "base_unit": "packet", "current_stock": 28, "low_stock_threshold": 15, "default_selling_price": 14},
    ]
    res = qe.answer_query(
        business_id="b1",
        topic="stock_check",
        product_query="maggi",
        products=stock_products,
        aliases=ALIASES,
    )
    assert "28 packet Maggi Masala 70g" in res["reply"]

    empty_res = qe.answer_query(business_id="b1", topic="stock_check", products=[])
    assert "khaali" in empty_res["reply"].lower()

    coca_res = qe.answer_query(
        business_id="b1",
        topic="stock_check",
        product_query="coca cola",
        products=[{"id": "p3", "name": "Coca-Cola 750ml", "base_unit": "piece", "current_stock": 18, "low_stock_threshold": 8, "default_selling_price": 40}],
        aliases=[],
    )
    assert "18 piece Coca-Cola 750ml" in coca_res["reply"]


def test_expenses_and_stock_query_parsing():
    exp_prop = deterministic_fallback_parse("Is there any expenses till now?", "en")
    assert len(exp_prop.operations) == 1
    assert exp_prop.operations[0].intent == "query_business"
    assert exp_prop.operations[0].query_topic == "expenses_summary"

    stk_prop = deterministic_fallback_parse("hamari inventory mein kitni coca cola hain?", "hinglish")
    assert len(stk_prop.operations) == 1
    assert stk_prop.operations[0].intent == "query_business"
    assert stk_prop.operations[0].query_topic == "stock_check"
    assert stk_prop.operations[0].product_query == "coca cola"

    # Packaging words like "packet" / "gram" must NOT falsely match Maggi Masala 70g
    surf_res = resolve_product(
        "surf excel 100 gram packet",
        PRODUCTS,
        [{"product_id": "p4", "alias_text": "maggi packet", "is_verified": True}],
    )
    assert surf_res.status == "not_found"

    # Payment method correction ("cash nahi, UBI se kia tha") must route to correction, not new expense
    corr_prop = deterministic_fallback_parse("cash nahi, UBI se kia tha.", "hinglish")
    assert len(corr_prop.operations) == 1
    assert corr_prop.operations[0].intent == "correct_last_operation"
    assert corr_prop.operations[0].payment_method == "upi"

    corr_sale_1 = deterministic_fallback_parse("Cash nahi online.", "hinglish")
    assert corr_sale_1.operations[0].intent == "correct_last_operation"
    assert corr_sale_1.operations[0].payment_method == "upi"

    corr_sale_2 = deterministic_fallback_parse("Last transaction cash se nahi online hua tha.", "hinglish")
    assert corr_sale_2.operations[0].intent == "correct_last_operation"
    assert corr_sale_2.operations[0].payment_method == "upi"

    # Single-variant catalog items resolve directly even without size suffix or minor spelling variance
    assert resolve_product("Coca-Cola", PRODUCTS, ALIASES).status == "exact"
    assert resolve_product("Maggie Masala", PRODUCTS, ALIASES).status == "exact"

    # Multi-variant catalog: "Coke" with 2 Coca-Cola variants & "Maggi masala" with 70g/100g -> ambiguous with all options
    multi_prods = [
        {"id": "c1", "name": "Coca-Cola 750ml", "base_unit": "piece"},
        {"id": "c2", "name": "Coca-Cola 2L", "base_unit": "piece"},
        {"id": "m1", "name": "Maggi Masala 70g", "base_unit": "packet"},
        {"id": "m2", "name": "Maggi Masala 100g", "base_unit": "packet"},
    ]
    coke_multi = resolve_product("Coke", multi_prods, [])
    assert coke_multi.status == "ambiguous"
    assert {c["name"] for c in coke_multi.candidates} == {"Coca-Cola 750ml", "Coca-Cola 2L"}

    maggi_multi = resolve_product("Maggi masala", multi_prods, [])
    assert maggi_multi.status == "ambiguous"
    assert {c["name"] for c in maggi_multi.candidates} == {"Maggi Masala 70g", "Maggi Masala 100g"}
    picked = resolve_short_variant_reply("Maggi masala 70 gram", maggi_multi.candidates)
    assert picked is not None and picked["name"] == "Maggi Masala 70g"

    # Different explicit weight/size (250g vs 70g) MUST NOT match 70g!
    assert resolve_product("Maggi masala 250 gram", PRODUCTS, ALIASES).status == "not_found"

    # VoiceOperationItem create_product schema supports both cost_price & selling_price cleanly
    new_item_op = VoiceOperationItem(
        intent="create_product",
        product_query="Maggi Masala 250g",
        quantity=10,
        unit="packet",
        cost_price=5.0,
        selling_price=50.0,
    )
    assert new_item_op.cost_price == 5.0 and new_item_op.selling_price == 50.0


def test_multivariant_disambiguation_with_existing_alias_and_llm_guard():
    catalog = [
        {"id": "m70", "name": "Maggi Masala 70g", "base_unit": "packet"},
        {"id": "m250", "name": "Maggi Masala 250 Gram", "base_unit": "packet"},
        {"id": "gm100", "name": "Garam Masala 100g", "base_unit": "packet"},
    ]
    existing_aliases = [
        {"product_id": "m70", "alias_text": "maggi masala", "is_verified": True},
        {"product_id": "m70", "alias_text": "maggi", "is_verified": True},
    ]

    # Even with an older verified alias pointing to Maggi Masala 70g, adding 250 Gram must show both!
    res = resolve_product("Maggi masala", catalog, existing_aliases)
    assert res.status == "ambiguous"
    assert {c["name"] for c in res.candidates} == {"Maggi Masala 70g", "Maggi Masala 250 Gram"}

    # Whisper spelling variance ("Maggie masala") must also show both Maggi SKUs and NOT Garam Masala
    res_typo = resolve_product("Maggie masala", catalog, existing_aliases)
    assert res_typo.status == "ambiguous"
    assert {c["name"] for c in res_typo.candidates} == {"Maggi Masala 70g", "Maggi Masala 250 Gram"}

    # Even if LLM mistakenly returned "Maggi Masala 70g" when user only said "One Maggi masala sold.",
    # transcript guard detects "70g" was not spoken and restores disambiguation!
    guarded = resolve_product_guarded("Maggi Masala 70g", "One Maggi masala sold.", catalog, existing_aliases)
    assert guarded.status == "ambiguous"
    assert {c["name"] for c in guarded.candidates} == {"Maggi Masala 70g", "Maggi Masala 250 Gram"}

    # When user actually speaks the size ("Maggi masala 250g"), unit normalization resolves cleanly!
    explicit = resolve_product_guarded("Maggi Masala 250 Gram", "One Maggi masala 250g sold.", catalog, existing_aliases)
    assert explicit.status == "exact" and explicit.product["id"] == "m250"

    # Variant size corrections like "70g nahi 250 gram" must NOT extract 250 as sale quantity!
    assert extract_post_negation_quantity("Maggi Masala 70g nahi 250 gram") is None
    assert extract_post_negation_quantity("20 pepsi nahi 10 hi biki") == 10.0


def test_udhaar_payment_settles_sales_and_includes_in_revenue():
    from app.services.transaction_engine import TransactionEngine

    class _FakeResp:
        def __init__(self, data):
            self.data = data

    class _FakeQuery:
        def __init__(self, store, name):
            self.store = store
            self.name = name
            self._action = "select"
            self._payload = None
            self._filters = []

        def select(self, *_a, **_k):
            self._action = "select"
            return self

        def update(self, payload):
            self._action = "update"
            self._payload = payload
            return self

        def insert(self, payload):
            self._action = "insert"
            self._payload = payload
            return self

        def eq(self, k, v):
            self._filters.append(("eq", k, v))
            return self

        def neq(self, k, v):
            self._filters.append(("neq", k, v))
            return self

        def in_(self, k, vals):
            self._filters.append(("in", k, set(vals)))
            return self

        def order(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        def execute(self):
            rows = self.store[self.name]
            if self._action == "insert":
                new_row = {"id": f"new-{len(rows) + 1}", **self._payload}
                rows.append(new_row)
                return _FakeResp([new_row])
            matched = []
            for r in rows:
                ok = True
                for kind, k, v in self._filters:
                    if kind == "eq" and r.get(k) != v:
                        ok = False
                    elif kind == "neq" and r.get(k) == v:
                        ok = False
                    elif kind == "in" and r.get(k) not in v:
                        ok = False
                if ok:
                    matched.append(r)
            if self._action == "update":
                for r in matched:
                    r.update(self._payload)
            return _FakeResp(matched)

    class _FakeRPC:
        def __init__(self, store, fn_name, params):
            self.store = store
            self.fn_name = fn_name
            self.params = params

        def execute(self):
            if self.fn_name == "rpc_record_customer_payment":
                cust = next(c for c in self.store["customers"] if c["id"] == self.params["p_customer_id"])
                before = float(cust["outstanding_balance"])
                after = max(0.0, before - float(self.params["p_amount"]))
                cust["outstanding_balance"] = after
                py = {
                    "id": "pay-1",
                    "business_id": self.params["p_business_id"],
                    "customer_id": cust["id"],
                    "amount": self.params["p_amount"],
                    "payment_method": self.params["p_payment_method"],
                    "transaction_date": self.params["p_transaction_date"],
                    "status": "active",
                    "operation_id": self.params["p_operation_id"],
                    "notes": self.params["p_notes"],
                }
                self.store["customer_payments"].append(py)
                return _FakeResp({"payment_id": "pay-1", "before_balance": before, "after_balance": after})
            return _FakeResp({})

    class _FakeDB:
        def __init__(self, store):
            self.store = store

        def table(self, name):
            return _FakeQuery(self.store, name)

        def rpc(self, fn_name, params):
            return _FakeRPC(self.store, fn_name, params)

    from app.core.time_utils import get_business_today

    today_ist = get_business_today("Asia/Kolkata").isoformat()
    store = {
        "customers": [{"id": "c1", "business_id": "b1", "outstanding_balance": 400.0}],
        "sales": [
            {
                "id": "s1",
                "business_id": "b1",
                "customer_id": "c1",
                "total_amount": 400.0,
                "paid_amount": 0.0,
                "payment_status": "credit",
                "transaction_date": today_ist,
                "status": "active",
                "operation_id": "op-sale-1",
                "notes": "[UDHAAR] Voice sale",
            }
        ],
        "customer_payments": [],
        "expenses": [],
        "inventory_movements": [],
        "voice_transactions": [],
    }
    engine = TransactionEngine(_FakeDB(store))
    res = engine.record_customer_payment(
        business_id="b1",
        user_id="u1",
        customer_id="c1",
        amount=400.0,
        payment_method="upi",
        transaction_date=today_ist,
        operation_id="op-pay-1",
    )
    assert res["after_balance"] == 0.0
    assert res["settled_sales_count"] == 1
    assert store["sales"][0]["paid_amount"] == 400.0
    assert store["sales"][0]["payment_status"] == "paid"
    assert "[ONLINE]" in store["sales"][0]["notes"]

    # QueryEngine immediately reflects collected revenue & zero remaining Udhaar
    qe = QueryEngine(_FakeDB(store))
    summary = qe.answer_query(business_id="b1", topic="sales_summary")
    assert summary["amount_inr"] == 400.0
    assert "Collected ₹400" in summary["reply"]

    # Reversing the payment restores outstanding balance & unpaid sale status cleanly
    engine.reverse_operation(
        business_id="b1",
        user_id="u1",
        operation_id="op-pay-1",
        reversal_operation_id="op-rev-1",
        transaction_date="2026-11-27",
    )
    assert store["customers"][0]["outstanding_balance"] == 400.0
    assert store["sales"][0]["paid_amount"] == 0.0
    assert store["sales"][0]["payment_status"] == "credit"


def test_devanagari_variant_reply_and_repeated_disambiguation():
    cands = [
        {"id": "m250", "name": "Maggie Masala 250 Gram", "base_unit": "packet"},
        {"id": "m70", "name": "Maggie Masala 70 Gram", "base_unit": "packet"},
    ]
    res = resolve_product_guarded("Maggie masala", "Two Maggie masala sold.", cands, [])
    assert res.status == "ambiguous"
    assert len(res.candidates) == 2

    picked = resolve_short_variant_reply("मेगी मसाला 70 gram", cands)
    assert picked is not None and picked["id"] == "m70"

    # Spelling variation ("Meggie Masala 500 Gram") when only 250g/70g exist surfaces existing variants for clarification
    size_miss = resolve_product("Meggie Masala 500 Gram", cands, [])
    assert size_miss.status == "not_found"
    assert size_miss.candidates and {c["id"] for c in size_miss.candidates} == {"m250", "m70"}

    # Spelling variation ("Meggie Masala 500 Gram") when "Maggi Masala 500g" exists asks clarification instead of not_found
    with_500 = resolve_product("Meggie Masala 500 Gram", [{"id": "m500", "name": "Maggi Masala 500g", "base_unit": "packet"}], [])
    assert with_500.status in {"exact", "verify_alias"} and with_500.product["id"] == "m500"


async def test_exact_product_sale_executes_without_hitting_not_found():
    from app.services.voice_pipeline import VoicePipelineService

    class _DummyDB:
        pass

    vp = VoicePipelineService(_DummyDB())
    vp.tx.record_sale = lambda **kw: {"sale_id": "sale-1", "before_qty": 27.0, "after_qty": 26.0, "total_amount": 12.0}
    vp._finalize_turn = lambda *a, **kw: None
    res = await vp._execute_operations_batch(
        operations=[VoiceOperationItem(intent="record_sale", product_query="Maggie Masala 70 Gram", quantity=1, unit="piece", payment_method="cash", payment_status="paid")],
        business_id="b1",
        user_id="u1",
        conv_id="conv-1",
        today_str="2026-11-27",
        tz_name="Asia/Kolkata",
        operation_id="11111111-1111-1111-1111-111111111111",
        payload_hash="hash-1",
        raw_transcript="ek maggi 70 gram bik gayi",
        language="hinglish",
        stt_provider="text",
        stt_confidence=1.0,
        products=[{"id": "p70", "name": "Maggie Masala 70 Gram", "base_unit": "piece", "current_stock": 27.0, "default_selling_price": 12.0, "default_cost_price": 10.0}],
        aliases=[],
        customers=[],
        context_state={},
    )
    assert res.status == "executed"
    assert "nahi mila" not in res.reply.lower()


def test_item_specific_sales_query_and_quantity_correction_revenue():
    from app.services.transaction_engine import TransactionEngine

    # 1. Fallback parser extracts product_query on item-specific sales queries
    q_prop = deterministic_fallback_parse("aaj Maggie ki kitne sales hui", "hinglish")
    assert q_prop.operations[0].intent == "query_business"
    assert q_prop.operations[0].query_topic == "sales_summary"
    assert q_prop.operations[0].product_query == "maggie"

    # 2. QueryEngine computes item-specific sales across matching variants
    class _FakeResp:
        def __init__(self, data):
            self.data = data

    class _FakeTable:
        def __init__(self, rows):
            self._rows = rows
            self._action = "select"
            self._payload = None
            self._filters = []

        def select(self, *_a, **_k):
            return self

        def update(self, payload):
            self._action = "update"
            self._payload = payload
            return self

        def eq(self, k, v):
            self._filters.append((k, v))
            return self

        def execute(self):
            matched = [r for r in self._rows if all(r.get(k) == v for k, v in self._filters)]
            if self._action == "update":
                for r in matched:
                    r.update(self._payload)
            return _FakeResp(matched)

    class _FakeRPC:
        def __init__(self, rows, new_qty):
            self._rows = rows
            self._new_qty = new_qty

        def execute(self):
            s = self._rows[0]
            s["total_amount"] = self._new_qty * 50.0
            s["paid_amount"] = self._new_qty * 50.0
            s["status"] = "corrected"  # simulates SQL RPC setting corrected
            s["sale_items"][0]["quantity"] = self._new_qty
            s["sale_items"][0]["line_total"] = self._new_qty * 50.0
            return _FakeResp({"old_quantity": 10.0, "new_quantity": self._new_qty, "new_total": self._new_qty * 50.0})

    class _FakeDB:
        def __init__(self, sales_rows):
            self.sales_rows = sales_rows

        def table(self, name):
            return _FakeTable(self.sales_rows if name == "sales" else [])

        def rpc(self, _fn, params):
            return _FakeRPC(self.sales_rows, float(params["p_new_quantity"]))

    today_str = date.today().isoformat()
    # Note: QueryEngine uses get_business_today("Asia/Kolkata"); match it dynamically
    from app.core.time_utils import get_business_today

    today_ist = get_business_today("Asia/Kolkata").isoformat()
    sales_rows = [
        {
            "id": "s-coke",
            "business_id": "b1",
            "transaction_date": today_ist,
            "status": "active",
            "total_amount": 500.0,
            "paid_amount": 500.0,
            "sale_items": [{"product_id": "p-coke", "quantity": 10.0, "unit": "piece", "line_total": 500.0}],
        }
    ]
    prods = [
        {"id": "p-coke", "name": "Coca-Cola 750 Ml", "base_unit": "piece"},
        {"id": "p-mag", "name": "Maggie Masala 70 Gram", "base_unit": "packet"},
    ]
    db = _FakeDB(sales_rows)
    tx = TransactionEngine(db)
    tx.correct_sale_quantity(
        business_id="b1",
        user_id="u1",
        sale_id="s-coke",
        new_quantity=7.0,
        operation_id="op-corr-7",
        transaction_date=today_ist,
    )
    # Must stay active so updated ₹350 revenue is counted!
    assert sales_rows[0]["status"] == "active"
    qe = QueryEngine(db)
    coke_res = qe.answer_query(business_id="b1", topic="sales_summary", product_query="Coke", products=prods, aliases=[])
    assert coke_res["amount_inr"] == 350.0
    assert "7 units" in coke_res["reply"] or "7 piece" in coke_res["lines"][0]["value"]


def test_hinglish_romanizer_and_english_reply_localization():
    from app.core.i18n_replies import localize_reply_sync, romanize_devanagari_to_hinglish

    # Devanagari Hinglish STT output converts cleanly into Romanized Hinglish for Hinglish mode
    rom = romanize_devanagari_to_hinglish("आज चीनी की कितनी सी एल हुई?")
    assert "aaj" in rom.lower()
    assert "chini" in rom.lower()
    assert "sale" in rom.lower()

    mag = romanize_devanagari_to_hinglish("एक मैगी मसाला 70 gram bik gayi")
    assert "maggie" in mag.lower()
    assert "70 gram" in mag.lower()

    # English localization converts canonical replies cleanly without changing numbers/names
    en_sales = localize_reply_sync(
        "Aaj abhi tak 10 sales hui hain, total ₹1,136 (Collected ₹1,136, Udhaar ₹0).",
        "en",
    )
    assert en_sales == "Today's total so far: 10 sales amounting to ₹1,136 (Collected ₹1,136, Udhaar ₹0)."

    en_item = localize_reply_sync("1 Maggie Masala 70 Gram ki Online sale (₹12) save ho gayi.", "en")
    assert en_item == "Saved Online sale for 1 Maggie Masala 70 Gram (₹12)."


def test_damage_correction_parsing_and_ledger_isolation():
    from app.core.i18n_replies import localize_reply_sync, romanize_devanagari_to_hinglish
    from app.services.transaction_engine import TransactionEngine

    # Devanagari damage terms ("डेमिस") + Hindi negation romanize cleanly
    rom = romanize_devanagari_to_hinglish("दो नहीं, बस एक ही डेमिस था.")
    assert "do nahi" in rom.lower()
    assert "ek" in rom.lower()
    assert "damaged" in rom.lower()

    # Post-negation extraction handles both trailing negation and lot context
    assert extract_post_negation_quantity("jo 14 Nescafe gold jars aaye the, unme se 2 damaged the, ek nahi.") == 2.0
    assert extract_post_negation_quantity("do nahi, bas ek hi demis tha.") == 1.0
    assert extract_post_negation_quantity("Sorry, 2 damage thay.") == 2.0

    # Fallback parser classifies damage corrections WITHOUT setting expense total_amount
    p1 = deterministic_fallback_parse("Sorry, 2 damage thay.", "hinglish")
    assert p1.operations[0].intent == "correct_last_operation"
    assert p1.operations[0].quantity == 2.0
    assert p1.operations[0].total_amount is None

    p2 = deterministic_fallback_parse("do nahi, bas ek hi demis tha.", "hinglish")
    assert p2.operations[0].intent == "correct_last_operation"
    assert p2.operations[0].quantity == 1.0
    assert p2.operations[0].total_amount is None

    # Legitimate credit wording with "paise nahi diye" must NOT falsely trigger correct_last_operation
    p_non_corr = deterministic_fallback_parse("10 coke udhaar di, paise nahi diye", "hinglish")
    assert p_non_corr.operations[0].intent != "correct_last_operation"

    # End-to-end TransactionEngine damage correction (1 -> 2 -> 1) without touching expenses
    class _Resp:
        def __init__(self, data):
            self.data = data

    class _Tbl:
        def __init__(self, store, name):
            self.store = store
            self.name = name
            self._act = "select"
            self._payload = None
            self._filters = []

        def select(self, *_a, **_k):
            self._act = "select"
            return self

        def update(self, payload):
            self._act = "update"
            self._payload = payload
            return self

        def insert(self, payload):
            self._act = "insert"
            self._payload = payload
            return self

        def eq(self, k, v):
            self._filters.append(("eq", k, v))
            return self

        def in_(self, k, vals):
            self._filters.append(("in", k, set(vals)))
            return self

        def order(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        def execute(self):
            rows = self.store[self.name]
            if self._act == "insert":
                row = {"id": f"m-{len(rows) + 1}", "created_at": f"2026-11-27T10:0{len(rows)}:00Z", **self._payload}
                rows.append(row)
                return _Resp([row])
            matched = []
            for r in rows:
                ok = True
                for kind, k, v in self._filters:
                    if kind == "eq" and r.get(k) != v:
                        ok = False
                    elif kind == "in" and r.get(k) not in v:
                        ok = False
                if ok:
                    matched.append(r)
            if self._act == "update":
                for r in matched:
                    r.update(self._payload)
            return _Resp(list(reversed(matched)))

    class _DB:
        def __init__(self, store):
            self.store = store

        def table(self, name):
            return _Tbl(self.store, name)

    store = {
        "products": [{"id": "p-nes", "business_id": "b1", "name": "Nescafe Gold Jars", "base_unit": "piece"}],
        "inventory": [{"business_id": "b1", "product_id": "p-nes", "current_quantity": 13.0}],
        "inventory_movements": [
            {
                "id": "m-dmg-1",
                "business_id": "b1",
                "product_id": "p-nes",
                "movement_type": "damage",
                "quantity_delta": -1.0,
                "unit": "piece",
                "operation_id": "op-dmg-1",
                "transaction_date": "2026-11-27",
                "created_at": "2026-11-27T10:00:00Z",
            }
        ],
        "expenses": [{"id": "exp-1", "business_id": "b1", "category": "Electricity", "amount": 1000.0, "status": "active"}],
        "voice_transactions": [{"business_id": "b1", "operation_id": "op-dmg-1", "validation_status": "executed"}],
    }
    tx = TransactionEngine(_DB(store))

    # Correct 1 -> 2 (stock: 13 -> 12)
    c1 = tx.correct_damage_or_expiry(
        business_id="b1",
        user_id="u1",
        new_quantity=2.0,
        operation_id="op-dmg-2",
        transaction_date="2026-11-27",
        old_operation_id="op-dmg-1",
        product_id="p-nes",
        movement_type="damage",
    )
    assert c1["old_quantity"] == 1.0 and c1["new_quantity"] == 2.0 and c1["after_stock"] == 12.0
    assert store["inventory"][0]["current_quantity"] == 12.0
    assert store["expenses"][0]["status"] == "active"  # Expenses completely untouched!

    # Correct 2 -> 1 (stock: 12 -> 13)
    c2 = tx.correct_damage_or_expiry(
        business_id="b1",
        user_id="u1",
        new_quantity=1.0,
        operation_id="op-dmg-3",
        transaction_date="2026-11-27",
        old_operation_id="op-dmg-2",
        product_id="p-nes",
        movement_type="damage",
    )
    assert c2["old_quantity"] == 2.0 and c2["new_quantity"] == 1.0 and c2["after_stock"] == 13.0
    assert store["inventory"][0]["current_quantity"] == 13.0

    # Active non-reversed loss movement is ONLY the final -1 entry
    active = tx.find_latest_active_loss_movement(business_id="b1", product_id="p-nes", movement_type="damage")
    assert active is not None and abs(active["quantity_delta"]) == 1.0 and active["operation_id"] == "op-dmg-3"

    # English reply rule for damage correction
    en_corr = localize_reply_sync(
        "Nescafe Gold Jars ka damage update ho gaya: 2 se 1. Remaining stock: 13.",
        "en",
    )
    assert en_corr == "Updated damage for Nescafe Gold Jars from 2 to 1. Remaining stock: 13."


def test_reverse_operation_updates_inventory_for_direct_and_corrected_sales():
    from app.services.transaction_engine import TransactionEngine

    class _Resp:
        def __init__(self, data):
            self.data = data

    class _Tbl:
        def __init__(self, store, name):
            self.store = store
            self.name = name
            self._act = "select"
            self._payload = None
            self._filters = []

        def select(self, *_a, **_k):
            self._act = "select"
            return self

        def update(self, payload):
            self._act = "update"
            self._payload = payload
            return self

        def insert(self, payload):
            self._act = "insert"
            self._payload = payload
            return self

        def eq(self, k, v):
            self._filters.append(("eq", k, v))
            return self

        def neq(self, k, v):
            self._filters.append(("neq", k, v))
            return self

        def limit(self, *_a, **_k):
            return self

        def execute(self):
            rows = self.store[self.name]
            if self._act == "insert":
                row = {"id": f"new-{len(rows) + 1}", **self._payload}
                rows.append(row)
                return _Resp([row])
            matched = []
            for r in rows:
                ok = True
                for kind, k, v in self._filters:
                    if kind == "eq" and r.get(k) != v:
                        ok = False
                    elif kind == "neq" and r.get(k) == v:
                        ok = False
                if ok:
                    matched.append(r)
            if self._act == "update":
                for r in matched:
                    r.update(self._payload)
            return _Resp(matched)

    class _DB:
        def __init__(self, store):
            self.store = store

        def table(self, name):
            return _Tbl(self.store, name)

    store = {
        "inventory": [{"business_id": "b1", "product_id": "p1", "current_quantity": 10.0}],
        "sales": [
            # Payment-corrected sale s2 (op2) whose parent s1 (op1) had the original movement
            {
                "id": "s1",
                "business_id": "b1",
                "status": "corrected",
                "total_amount": 150.0,
                "paid_amount": 150.0,
                "operation_id": "op1",
            },
            {
                "id": "s2",
                "business_id": "b1",
                "status": "active",
                "parent_sale_id": "s1",
                "total_amount": 150.0,
                "paid_amount": 150.0,
                "operation_id": "op2",
            },
            # Qty-corrected sale s3 (was 10, corrected to 7; movement on op3 still says -10)
            {
                "id": "s3",
                "business_id": "b1",
                "status": "active",
                "total_amount": 350.0,
                "paid_amount": 350.0,
                "operation_id": "op3",
            },
        ],
        "sale_items": [
            {"id": "si2", "business_id": "b1", "sale_id": "s2", "product_id": "p1", "quantity": 3.0, "unit": "piece"},
            {"id": "si3", "business_id": "b1", "sale_id": "s3", "product_id": "p1", "quantity": 7.0, "unit": "piece"},
        ],
        "inventory_movements": [
            {
                "id": "mv1",
                "business_id": "b1",
                "product_id": "p1",
                "movement_type": "sale",
                "quantity_delta": -3.0,
                "unit": "piece",
                "reference_id": "s1",
                "operation_id": "op1",
            },
            {
                "id": "mv3",
                "business_id": "b1",
                "product_id": "p1",
                "movement_type": "sale",
                "quantity_delta": -10.0,
                "unit": "piece",
                "reference_id": "s3",
                "operation_id": "op3",
            },
        ],
        "expenses": [],
        "customer_payments": [],
        "voice_transactions": [],
        "conversation_messages": [],
    }
    tx = TransactionEngine(_DB(store))

    # 1. Reversing payment-corrected sale (op2) MUST restore +3 to stock (10 -> 13)
    res1 = tx.reverse_operation(
        business_id="b1",
        user_id="u1",
        operation_id="op2",
        reversal_operation_id="rev-op2",
        transaction_date="2026-11-28",
    )
    assert res1["reversed"] is True
    assert store["inventory"][0]["current_quantity"] == 13.0
    assert store["sales"][1]["status"] == "voided"

    # 2. Reversing qty-corrected sale (op3) MUST restore +7 (not +10!) -> (13 -> 20)
    res2 = tx.reverse_operation(
        business_id="b1",
        user_id="u1",
        operation_id="op3",
        reversal_operation_id="rev-op3",
        transaction_date="2026-11-28",
    )
    assert res2["reversed"] is True
    assert store["inventory"][0]["current_quantity"] == 20.0
    assert store["sales"][2]["status"] == "voided"

    # 3. Calling reverse_operation again on op1 must NOT double-restore mv1!
    res3 = tx.reverse_operation(
        business_id="b1",
        user_id="u1",
        operation_id="op1",
        reversal_operation_id="rev-op1",
        transaction_date="2026-11-28",
    )
    assert store["inventory"][0]["current_quantity"] == 20.0


def _make_rich_db(store):
    class _Resp:
        def __init__(self, data):
            self.data = data

    class _Tbl:
        def __init__(self, st, name):
            self.st = st
            self.name = name
            self._act = "select"
            self._payload = None
            self._filters = []

        def select(self, *_a, **_k):
            self._act = "select"
            return self

        def update(self, payload):
            self._act = "update"
            self._payload = payload
            return self

        def insert(self, payload):
            self._act = "insert"
            self._payload = payload
            return self

        def eq(self, k, v):
            self._filters.append(("eq", k, v))
            return self

        def neq(self, k, v):
            self._filters.append(("neq", k, v))
            return self

        def in_(self, k, vals):
            self._filters.append(("in", k, set(vals)))
            return self

        def gte(self, k, v):
            self._filters.append(("gte", k, v))
            return self

        def lte(self, k, v):
            self._filters.append(("lte", k, v))
            return self

        def order(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        def execute(self):
            rows = self.st.setdefault(self.name, [])
            if self._act == "insert":
                row = {"id": f"{self.name}-{len(rows) + 1}", "created_at": "2026-11-28T10:00:00", **self._payload}
                rows.append(row)
                return _Resp([row])
            matched = []
            for r in rows:
                ok = True
                for kind, k, v in self._filters:
                    if kind == "eq" and r.get(k) != v:
                        ok = False
                    elif kind == "neq" and r.get(k) == v:
                        ok = False
                    elif kind == "in" and r.get(k) not in v:
                        ok = False
                    elif kind == "gte" and str(r.get(k) or "") < str(v):
                        ok = False
                    elif kind == "lte" and str(r.get(k) or "") > str(v):
                        ok = False
                if ok:
                    matched.append(r)
            if self._act == "update":
                for r in matched:
                    r.update(self._payload)
            return _Resp(matched)

    class _DB:
        def __init__(self, st):
            self.st = st

        def table(self, name):
            return _Tbl(self.st, name)

        def rpc(self, fn_name, params):
            if fn_name == "rpc_record_sale":
                pid = params["p_product_id"]
                qty = float(params["p_quantity"])
                inv = next(i for i in self.st["inventory"] if i["product_id"] == pid)
                before = float(inv["current_quantity"])
                inv["current_quantity"] = before - qty
                sale_id = f"sales-{len(self.st['sales']) + 1}"
                tot = round(qty * float(params["p_unit_price"]), 2)
                self.st["sales"].append(
                    {
                        "id": sale_id,
                        "business_id": params["p_business_id"],
                        "customer_id": params["p_customer_id"],
                        "total_amount": tot,
                        "paid_amount": float(params["p_paid_amount"]),
                        "payment_status": params["p_payment_status"],
                        "transaction_date": params["p_transaction_date"],
                        "status": "active",
                        "operation_id": params["p_operation_id"],
                        "notes": params["p_notes"],
                    }
                )
                self.st["sale_items"].append(
                    {
                        "id": f"si-{len(self.st['sale_items']) + 1}",
                        "business_id": params["p_business_id"],
                        "sale_id": sale_id,
                        "product_id": pid,
                        "quantity": qty,
                        "unit": params["p_unit"],
                        "unit_price": float(params["p_unit_price"]),
                        "line_total": tot,
                    }
                )
                self.st["inventory_movements"].append(
                    {
                        "id": f"mv-{len(self.st['inventory_movements']) + 1}",
                        "business_id": params["p_business_id"],
                        "product_id": pid,
                        "movement_type": "sale",
                        "quantity_delta": -qty,
                        "unit": params["p_unit"],
                        "reference_id": sale_id,
                        "operation_id": params["p_operation_id"],
                    }
                )
                class _RpcExec:
                    def __init__(self, d):
                        self._d = d

                    def execute(self):
                        return _Resp(self._d)

                return _RpcExec({"sale_id": sale_id, "before_qty": before, "after_qty": before - qty})
            raise NotImplementedError(fn_name)

    return _DB(store)


def test_multiday_queries_and_supplier_separation():
    from app.core.time_utils import resolve_date_range

    start_w, end_w, lbl_w = resolve_date_range(date_range="this_week", timezone_name="Asia/Kolkata")
    assert start_w <= end_w and lbl_w == "Is hafte"

    store = {
        "products": [{"id": "p-mag", "name": "Maggi Masala 70g", "base_unit": "packet"}],
        "sales": [
            {"id": "s1", "business_id": "b1", "status": "active", "transaction_date": start_w.isoformat(), "total_amount": 140.0, "paid_amount": 140.0},
            {"id": "s2", "business_id": "b1", "status": "active", "transaction_date": end_w.isoformat(), "total_amount": 60.0, "paid_amount": 0.0},
        ],
        "sale_items": [
            {"id": "si1", "business_id": "b1", "sale_id": "s1", "product_id": "p-mag", "quantity": 10.0, "line_total": 140.0},
        ],
        "expenses": [
            {"id": "e1", "business_id": "b1", "status": "active", "transaction_date": start_w.isoformat(), "amount": 250.0, "category": "Supplies"},
        ],
        "customers": [
            {"id": "c1", "business_id": "b1", "is_active": True, "name": "Rahul", "area_note": "", "outstanding_balance": 300.0},
            {"id": "sup1", "business_id": "b1", "is_active": True, "name": "Sharma ji", "area_note": "[SUPPLIER]", "outstanding_balance": 5000.0},
        ],
    }
    qe = QueryEngine(_make_rich_db(store))

    sales_w = qe.answer_query(
        business_id="b1",
        topic="sales_summary",
        product_query=None,
        customer_query=None,
        products=store["products"],
        aliases=[],
        date_range="this_week",
    )
    assert sales_w["amount_inr"] == 200.0
    assert "Is hafte" in sales_w["reply"]

    exp_w = qe.answer_query(
        business_id="b1",
        topic="expenses_summary",
        product_query=None,
        customer_query=None,
        products=store["products"],
        aliases=[],
        date_range="this_week",
    )
    assert exp_w["amount_inr"] == 250.0

    # Customer receivables exclude [SUPPLIER] rows; supplier_balance queries ONLY suppliers
    pend = qe.answer_query(
        business_id="b1",
        topic="pending_payments",
        product_query=None,
        customer_query=None,
        products=store["products"],
        aliases=[],
    )
    assert pend["amount_inr"] == 300.0
    sup_q = qe.answer_query(
        business_id="b1",
        topic="supplier_balance",
        product_query=None,
        customer_query=None,
        products=store["products"],
        aliases=[],
    )
    assert sup_q["amount_inr"] == 5000.0 and "Sharma ji" in sup_q["reply"]


def test_customer_return_variant_swap_and_combined_bill():
    from app.services.transaction_engine import TransactionEngine

    store = {
        "products": [
            {"id": "p70", "business_id": "b1", "name": "Maggi Masala 70g", "base_unit": "packet", "default_selling_price": 14.0},
            {"id": "p250", "business_id": "b1", "name": "Maggi Masala 250g", "base_unit": "packet", "default_selling_price": 50.0},
            {"id": "pcoke", "business_id": "b1", "name": "Coke 750ml", "base_unit": "piece", "default_selling_price": 45.0},
        ],
        "product_aliases": [],
        "inventory": [
            {"business_id": "b1", "product_id": "p70", "current_quantity": 20.0},
            {"business_id": "b1", "product_id": "p250", "current_quantity": 10.0},
            {"business_id": "b1", "product_id": "pcoke", "current_quantity": 12.0},
        ],
        "customers": [
            {"id": "c-ramesh", "business_id": "b1", "is_active": True, "name": "Ramesh", "area_note": "", "outstanding_balance": 0.0},
        ],
        "sales": [],
        "sale_items": [],
        "inventory_movements": [],
        "expenses": [],
        "customer_payments": [],
        "voice_transactions": [],
        "conversation_messages": [],
    }
    tx = TransactionEngine(_make_rich_db(store))

    # 1. Record sale on 70g -> Variant swap to 250g in one turn
    tx.record_sale(
        business_id="b1",
        user_id="u1",
        product_id="p70",
        product_name="Maggi Masala 70g",
        quantity=2,
        unit="packet",
        unit_price=14.0,
        payment_status="paid",
        paid_amount=28.0,
        customer_id=None,
        transaction_date="2026-11-28",
        operation_id="op-sale-1",
    )
    assert store["inventory"][0]["current_quantity"] == 18.0
    sw = tx.swap_last_sale_variant(
        business_id="b1",
        user_id="u1",
        old_operation_id="op-sale-1",
        new_product_id="p250",
        new_product_name="Maggi Masala 250g",
        new_unit="packet",
        new_unit_price=50.0,
        transaction_date="2026-11-28",
        operation_id="op-swap-1",
    )
    assert sw["new_total"] == 100.0
    assert store["inventory"][0]["current_quantity"] == 20.0  # 70g restored
    assert store["inventory"][1]["current_quantity"] == 8.0   # 250g deducted

    # 2. Customer return (wapsi): 2 Maggi 70g returned for 28 INR cash refund -> stock 20 -> 22, expense recorded & reversible
    ret = tx.record_customer_return(
        business_id="b1",
        user_id="u1",
        product_id="p70",
        product_name="Maggi Masala 70g",
        quantity=2,
        unit="packet",
        refund_amount=28.0,
        refund_method="cash",
        customer_id=None,
        transaction_date="2026-11-28",
        operation_id="op-ret-1",
    )
    assert ret["after_stock"] == 22.0
    assert store["expenses"][0]["category"] == "Customer Return"

    # 3. Combined multi-item bill with lump-sum 100 INR (catalog = 2*14 + 45 = 73 or say 2*50 + 45 = 145 -> 100)
    cb = tx.record_combined_bill(
        business_id="b1",
        user_id="u1",
        items=[
            {"product_id": "p250", "product_name": "Maggi Masala 250g", "quantity": 2, "unit": "packet", "unit_price": 50.0},
            {"product_id": "pcoke", "product_name": "Coke 750ml", "quantity": 1, "unit": "piece", "unit_price": 45.0},
        ],
        customer_id="c-ramesh",
        bill_total_amount=100.0,
        paid_amount=None,
        payment_status="paid",
        payment_method="cash",
        transaction_date="2026-11-28",
        operation_id="op-cb-1",
    )
    assert cb["total_amount"] == 100.0 and cb["discount_amount"] == 45.0
    assert len(cb["items"]) == 2
    assert store["inventory"][1]["current_quantity"] == 6.0
    assert store["inventory"][2]["current_quantity"] == 11.0


def test_supplier_credit_split_sale_and_voice_rename():
    from app.services.transaction_engine import TransactionEngine

    store = {
        "products": [{"id": "p1", "business_id": "b1", "name": "Coca-Cola", "normalized_name": "coca-cola"}],
        "product_aliases": [],
        "customers": [
            {"id": "c-nitin", "business_id": "b1", "is_active": True, "name": "Nitin", "phone": "", "area_note": "", "outstanding_balance": 0.0},
        ],
        "sales": [],
        "expenses": [],
        "voice_transactions": [],
        "conversation_messages": [],
        "inventory_movements": [],
        "customer_payments": [],
    }
    tx = TransactionEngine(_make_rich_db(store))

    # 1. Supplier credit & payment + reverse
    sup, created = tx.find_or_create_supplier(business_id="b1", name="Sharma ji")
    assert created is True and "[SUPPLIER]" in sup["area_note"]
    sc = tx.record_supplier_credit(business_id="b1", supplier_id=sup["id"], amount=5000.0)
    assert sc["after_balance"] == 5000.0
    sp = tx.record_supplier_payment(
        business_id="b1",
        user_id="u1",
        supplier_id=sup["id"],
        supplier_name="Sharma ji",
        amount=2000.0,
        payment_method="upi",
        transaction_date="2026-11-28",
        operation_id="op-sp-1",
    )
    assert sp["after_balance"] == 3000.0
    assert store["expenses"][0]["category"] == "Supplier Payment"

    # 2. Split partial customer sale (500 total: 200 cash + 300 udhaar)
    split_res = tx.record_split_customer_sale(
        business_id="b1",
        user_id="u1",
        customer_id="c-nitin",
        total_amount=500.0,
        paid_amount=200.0,
        payment_method="cash",
        transaction_date="2026-11-28",
        operation_id="op-split-1",
    )
    assert split_res["payment_status"] == "partial"
    assert split_res["credit_amount"] == 300.0
    assert split_res["after_balance"] == 300.0

    # 3. Product rename auto-saves old name as alias
    upd_p = tx.update_product_settings(business_id="b1", product_id="p1", new_name="Coke 750ml")
    assert upd_p["name"] == "Coke 750ml"
    assert len(store["product_aliases"]) == 1 and store["product_aliases"][0]["alias"] == "Coca-Cola"

    # 4. Deterministic fallback parser recognizes date range, return, supplier, split & rename
    p_week = deterministic_fallback_parse("Is hafte kitni sale hui?", "hinglish")
    assert p_week.operations[0].intent == "query_business" and p_week.operations[0].date_range == "this_week"
    p_ret = deterministic_fallback_parse("Customer 2 Maggi wapas kar gaya, 28 rupaye wapas diye", "hinglish")
    assert p_ret.operations[0].intent == "customer_return" and p_ret.operations[0].quantity == 2.0
    p_sup = deterministic_fallback_parse("Supplier Sharma ji se 5000 ka maal udhaar aaya", "hinglish")
    assert p_sup.operations[0].intent == "record_supplier_credit" and p_sup.operations[0].total_amount == 5000.0
    p_split = deterministic_fallback_parse("Nitin ne 500 ka saaman liya, 200 cash diye aur 300 udhaar", "hinglish")
    assert p_split.operations[0].payment_status == "partial" and p_split.operations[0].paid_amount == 200.0
    p_ren = deterministic_fallback_parse("Coca-Cola ka naam badal ke Coke 750ml kar do", "hinglish")
    assert p_ren.operations[0].intent == "update_product_settings" and p_ren.operations[0].new_name == "Coke 750ml"
