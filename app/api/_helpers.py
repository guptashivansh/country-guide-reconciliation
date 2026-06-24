"""Shared helpers that depend on config_service, used across route modules."""

from app.utils.flags import build_flags_map, country_flag


def make_config_helpers(config_service):
    """Return a dict of helper closures bound to the given config_service."""

    def _flags():
        if config_service:
            return build_flags_map(config_service.get_country_iso_codes())
        return {}

    def _flag(country_name):
        return _flags().get(country_name, country_flag(country_name))

    def _section_groups():
        if config_service:
            return config_service.get_section_groups()
        return []

    def _sections_for_view(view_name):
        if config_service:
            return config_service.get_sections_for_view(view_name)
        return set()

    return {
        "flags": _flags,
        "flag": _flag,
        "section_groups": _section_groups,
        "sections_for_view": _sections_for_view,
    }
