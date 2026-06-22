def country_flag(country_name: str, iso_code: str = None) -> str:
    if iso_code:
        code = iso_code.upper()
        if len(code) == 2 and code.isalpha():
            return chr(0x1F1E6 + ord(code[0]) - ord("A")) + chr(0x1F1E6 + ord(code[1]) - ord("A"))
    return _OVERRIDES.get(country_name, "\U0001F310")


def build_flags_map(country_iso_map: dict[str, str]) -> dict[str, str]:
    return {name: country_flag(name, iso) for name, iso in country_iso_map.items()}


_OVERRIDES = {
    "Congo (Republic of Congo)": "\U0001F1E8\U0001F1EC",
    "Hong Kong": "\U0001F1ED\U0001F1F0",
    "Puerto Rico": "\U0001F1F5\U0001F1F7",
    "Taiwan": "\U0001F1F9\U0001F1FC",
}
