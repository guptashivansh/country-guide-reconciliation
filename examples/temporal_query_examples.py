from app.repositories.country_guide_repository import CountryGuideRepository
from app.services.temporal_rule_service import TemporalRuleService


def rule_at_date(db_path, country, section, as_of_date):
    service = TemporalRuleService(CountryGuideRepository(db_path))
    return service.get_rule_at_date(country, section, as_of_date)


def rule_version_history(db_path, country, section):
    service = TemporalRuleService(CountryGuideRepository(db_path))
    return service.list_version_history(country, section)


def active_rule_with_history(db_path, country, section):
    service = TemporalRuleService(CountryGuideRepository(db_path))
    return service.build_timeline(country, section)
