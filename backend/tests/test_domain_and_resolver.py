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
                "transaction_date": "2026-11-27",
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
        transaction_date="2026-11-27",
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
