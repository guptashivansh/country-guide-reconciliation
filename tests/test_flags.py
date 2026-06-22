from app.utils.flags import build_flags_map, country_flag


def test_country_flag_from_iso():
    assert country_flag("India", "IN") == "\U0001F1EE\U0001F1F3"
    assert country_flag("Australia", "AU") == "\U0001F1E6\U0001F1FA"


def test_country_flag_override():
    assert country_flag("Taiwan") == "\U0001F1F9\U0001F1FC"
    assert country_flag("Hong Kong") == "\U0001F1ED\U0001F1F0"
    assert country_flag("Puerto Rico") == "\U0001F1F5\U0001F1F7"
    assert country_flag("Congo (Republic of Congo)") == "\U0001F1E8\U0001F1EC"


def test_country_flag_unknown():
    assert country_flag("Atlantis") == "\U0001F310"


def test_country_flag_iso_takes_precedence_over_override():
    flag = country_flag("Taiwan", "TW")
    assert flag == "\U0001F1F9\U0001F1FC"


def test_country_flag_bad_iso_falls_to_override():
    assert country_flag("Hong Kong", "") == "\U0001F1ED\U0001F1F0"
    assert country_flag("Hong Kong", "XYZ") == "\U0001F1ED\U0001F1F0"


def test_build_flags_map():
    iso_map = {"India": "IN", "Germany": "DE", "Unknown Country": ""}
    result = build_flags_map(iso_map)
    assert result["India"] == "\U0001F1EE\U0001F1F3"
    assert result["Germany"] == "\U0001F1E9\U0001F1EA"
    assert result["Unknown Country"] == "\U0001F310"
