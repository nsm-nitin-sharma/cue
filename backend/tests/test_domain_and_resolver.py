from datetime import date

from app.core.time_utils import check_memory_window_days, detect_over_30_day_reference
from app.domain.indian_numbers import extract_post_negation_number, parse_indian_number
from app.domain.unit_converter import convert_to_base_quantity
from app.providers.llm.gemini import deterministic_fallback_parse
from app.services.entity_resolver import (
    resolve_customer,
    resolve_product,
    resolve_short_variant_reply,
)

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
