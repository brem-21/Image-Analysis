import pytest

from app.services import normalize as N


@pytest.mark.parametrize(
    "raw,value,unit",
    [
        ("250 g", 250.0, "g"),
        ("1.5L", 1.5, "l"),
        ("500ml", 500.0, "ml"),
        ("2,5 kg", 2.5, "kg"),
        ("12 pcs", 12.0, "unit"),
        ("", None, None),
        (None, None, None),
    ],
)
def test_parse_weight(raw, value, unit):
    assert N.parse_weight(raw) == (value, unit)


@pytest.mark.parametrize(
    "value,unit,expected",
    [(250, "g", "250G"), (1.5, "l", "1.5L"), (None, "g", None), (70.0, "g", "70G")],
)
def test_format_weight(value, unit, expected):
    assert N.format_weight(value, unit) == expected


def test_normalize_country_aliases():
    assert N.normalize_country("Made in PRC") == "China"
    assert N.normalize_country("made in ghana") == "Ghana"
    assert N.normalize_country("usa") == "United States"
    assert N.normalize_country(None) is None


def test_canonicalize_collapses_variants():
    # Case-insensitive variants map onto the canonical label.
    assert N.canonicalize("brand", "pepsi") == "Pepsi"
    assert N.canonicalize("brand", "blue band") == "Blue Band"
    # Unknown values fall back to title case, not dropped.
    assert N.canonicalize("brand", "totally unknown brand") == "Totally Unknown Brand"


def test_build_item_name_is_ordered_and_deduped():
    values = {
        "brand": "Kivo",
        "weight_value": 70,
        "weight_unit": "g",
        "packaging_type": "Sachet",
        "fragrance_flavor": "Tomato",
        "category_type": "Condiments",
    }
    name = N.build_item_name(values)
    assert name.startswith("KIVO 70G SACHET")
    assert "TOMATO" in name and "CONDIMENTS" in name
    # No duplicate tokens.
    tokens = name.split()
    assert len(tokens) == len(set(tokens))


def test_build_item_name_empty_when_no_fields():
    assert N.build_item_name({}) is None
