"""
One-time CLI script to seed the country_guide table from the Skuad Notion guide.
Parses Notion content directly — no LLM needed.

Usage:
    python notion_import.py [--dry-run]
"""

import argparse
import logging
import sys

from app.ingestion.notion_ingestion_service import NotionIngestionService
from app.ingestion.notion_section_parser import (
    COUNTRY_ALIASES,
    FIELD_TO_SECTION,
    canonical_country as _canonical_country,
    parse_sections as _parse_sections,
)
from app.repositories.country_guide_repository import CountryGuideRepository
from app.repositories.provenance_repository import ProvenanceRepository
from app.services.provenance_service import ProvenanceService
from app.utils.config import load_env_file, notion_api_key, parser_version
from app.utils.db import Database
from app.utils.logging_config import configure_logging

NOTION_PAGE_ID = "7ed6a2f53972448db2cb107a8d20b661"
NOTION_SOURCE_URL = "https://skuad.notion.site/Skuad-Country-Product-Guides-7ed6a2f53972448db2cb107a8d20b661"


def main():
    parser = argparse.ArgumentParser(description="Import Skuad country guides from Notion")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and parse but do not write to DB")
    args = parser.parse_args()

    load_env_file()
    configure_logging()

    db = Database()
    repo = CountryGuideRepository(db)
    repo.initialize_schema()

    provenance_repo = ProvenanceRepository(db)
    provenance_repo.initialize_schema()
    provenance_service = ProvenanceService(provenance_repo, parser_version=parser_version())

    api_key = notion_api_key()
    notion_service = NotionIngestionService(page_id=NOTION_PAGE_ID, api_key=api_key)

    print("Auto-discovering all country guides on the Notion page...")
    country_texts = notion_service.fetch_all_employment_guides()

    if not country_texts:
        print("ERROR: No matching country pages found. Check the Notion page structure.", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(country_texts)} country page(s): {', '.join(sorted(country_texts))}\n")

    total_rules = 0
    total_countries = 0

    for raw_country, content in sorted(country_texts.items()):
        country = _canonical_country(raw_country)
        sections = _parse_sections(content)

        if not sections:
            print(f"[{country}] SKIP — could not parse any sections from {len(content):,} chars")
            continue

        print(f"[{country}] Parsed {len(sections)} section(s) from {len(content):,} chars")
        if args.dry_run:
            for section, value in sorted(sections.items()):
                print(f"    [{section}] {value[:80].replace(chr(10), ' ')}")
        else:
            for section, value in sections.items():
                repo.upsert_guide_entry(
                    country=country,
                    section=section,
                    value=value,
                    source_url=NOTION_SOURCE_URL,
                )
                provenance_service.record_seed(country, section, value, NOTION_SOURCE_URL)
            print(f"  Written to DB.")

        total_rules += len(sections)
        total_countries += 1

    suffix = " (dry run — nothing written)" if args.dry_run else ""
    print(f"\nDone: {total_rules} rule(s) across {total_countries} country/countries{suffix}.")


if __name__ == "__main__":
    main()
