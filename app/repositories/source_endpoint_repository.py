import json
import logging
import urllib.request
from app.models.source_endpoint import SourceEndpoint

logger = logging.getLogger(__name__)


class TrustedSourceEndpointRepository:
    def __init__(
        self,
        json_url: str = "https://raw.githubusercontent.com/guptashivansh/compliance-data/main/data/official-sources.json",
    ):
        self.json_url = json_url
        self._cache = None

    def list_active_source_endpoints(self) -> list[SourceEndpoint]:
        if self._cache is None:
            self._load()
        return self._cache

    def _load(self) -> None:
        data = self._fetch_json()

        country_map = {c["id"]: c["name"] for c in data.get("countries", [])}
        authority_map = {a["id"]: a for a in data.get("authorities", [])}

        endpoints = []
        for se in data.get("source_endpoints", []):
            if se.get("status") != "active":
                continue
            authority = authority_map.get(se.get("authority_id"))
            if authority is None or not authority.get("is_active", False):
                continue

            country_id = authority.get("country_id", "")
            country_name = country_map.get(country_id, "")
            authority_name = authority.get("name", "")
            sections = tuple(se.get("sections_covered", []))

            endpoints.append(
                SourceEndpoint(
                    country=country_name,
                    authority=authority_name,
                    url=se.get("url", ""),
                    sections=sections,
                )
            )

        logger.info("Official sources loaded", extra={"endpoint_count": len(endpoints)})
        self._cache = endpoints

    def _fetch_json(self) -> dict:
        logger.debug("Fetching source endpoints JSON from %s", self.json_url)
        try:
            with urllib.request.urlopen(self.json_url, timeout=10) as response:
                raw = response.read()
            return json.loads(raw)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to fetch source endpoints from {self.json_url}: {exc}"
            ) from exc
