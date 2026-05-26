from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceEndpoint:
    country: str
    authority: str
    url: str
    sections: tuple[str, ...]
    endpoint_id: str = ""
    authority_id: str = ""
    country_id: str = ""
    iso_code: str = ""
    authority_type: str = ""
    authority_url: str = ""
    trust_level: str = "official"
    precedence_rank: int = 1
    escalation_required: bool = False
    supports_replay: bool = True
    source_type: str = "html"
    content_language: str = "en"
    authority_category: str = ""
    extraction_strategy: str = "html_readability"
    parser_key: str = "html_readability_v1"
    crawl_frequency: str = "monthly"
    change_detection_strategy: str = "semantic"
    requires_authentication: bool = False
    is_javascript_heavy: bool = False
    owner_team: str = ""
    notes: str = ""
    status: str = "active"
