from typing import Literal

BaseUnit = Literal["piece", "packet", "kg", "litre", "box"]

_UNIT_ALIASES: dict[str, str] = {
    "piece": "piece",
    "pieces": "piece",
    "pc": "piece",
    "pcs": "piece",
    "nag": "piece",
    "bottle": "piece",
    "bottles": "piece",
    "jar": "piece",
    "jars": "piece",
    "can": "piece",
    "cans": "piece",
    "unit": "piece",
    "units": "piece",
    "packet": "packet",
    "packets": "packet",
    "pkt": "packet",
    "pkts": "packet",
    "pouch": "packet",
    "pouches": "packet",
    "bag": "packet",
    "bags": "packet",
    "kg": "kg",
    "kilo": "kg",
    "kilos": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "g": "gram",
    "gm": "gram",
    "gms": "gram",
    "gram": "gram",
    "grams": "gram",
    "l": "litre",
    "litre": "litre",
    "litres": "litre",
    "liter": "litre",
    "liters": "litre",
    "ml": "ml",
    "millilitre": "ml",
    "milliliter": "ml",
    "box": "box",
    "boxes": "box",
    "peti": "box",
    "petis": "box",
    "carton": "box",
    "cartons": "box",
    "crate": "box",
    "crates": "box",
    "darjan": "darjan",
    "dozen": "darjan",
}


def normalize_spoken_unit(raw_unit: str | None, fallback: BaseUnit = "piece") -> str:
    if not raw_unit:
        return fallback
    clean = raw_unit.strip().lower()
    return _UNIT_ALIASES.get(clean, clean)


def convert_to_base_quantity(
    *,
    quantity: float,
    spoken_unit: str | None,
    base_unit: BaseUnit,
    custom_conversions: dict[str, float] | None = None,
) -> tuple[float | None, str | None]:
    """
    Convert spoken quantity+unit to product's base_unit.
    Returns (converted_qty, error_message). Rejects incompatible units cleanly.
    """
    norm = normalize_spoken_unit(spoken_unit, fallback=base_unit)

    if norm == base_unit:
        return quantity, None

    if custom_conversions and norm in custom_conversions:
        return round(quantity * custom_conversions[norm], 4), None

    # Discrete countable units (piece/pcs/bottle/jar <-> packet/pkt/pouch) map 1:1 unless custom-overridden
    if {norm, base_unit} <= {"piece", "packet"}:
        return quantity, None

    # Metric mass & volume conversions
    if norm == "gram" and base_unit == "kg":
        return round(quantity / 1000.0, 4), None
    if norm == "kg" and base_unit == "gram":  # pragma: no cover
        return round(quantity * 1000.0, 4), None
    if norm == "ml" and base_unit == "litre":
        return round(quantity / 1000.0, 4), None
    if norm == "darjan" and base_unit in {"piece", "packet"}:
        return round(quantity * 12.0, 4), None

    return None, (
        f"Unit mismatch: '{spoken_unit}' ko '{base_unit}' mein automatically convert nahi kar sakte. "
        f"Kripya {base_unit} mein batayein ya conversion set karein."
    )
