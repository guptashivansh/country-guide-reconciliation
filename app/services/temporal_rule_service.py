from datetime import date, datetime


class TemporalRuleService:
    def __init__(self, country_guide_repository):
        self.country_guide_repository = country_guide_repository

    def get_current_rule(self, country, section):
        return self.country_guide_repository.get_current_rule(country, section)

    def get_rule_at_date(self, country, section, as_of_date):
        return self.country_guide_repository.get_rule_at_date(
            country,
            section,
            self._normalize_as_of_date(as_of_date),
        )

    def list_version_history(self, country, section):
        return self.country_guide_repository.list_rule_versions(country, section)

    def build_timeline(self, country, section):
        versions = self.list_version_history(country, section)
        return {
            "country": country,
            "section": section,
            "current": self.get_current_rule(country, section),
            "history": versions,
        }

    def _normalize_as_of_date(self, as_of_date):
        if isinstance(as_of_date, datetime):
            return as_of_date.date().isoformat()
        if isinstance(as_of_date, date):
            return as_of_date.isoformat()
        if not as_of_date:
            raise ValueError("as_of_date is required")
        value = str(as_of_date).strip()
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            try:
                return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
            except ValueError as exc:
                raise ValueError("as_of_date must be an ISO date or datetime") from exc
