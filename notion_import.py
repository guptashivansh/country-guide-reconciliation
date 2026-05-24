"""
One-time CLI script to seed the country_guide table from the Skuad Notion guide.
Parses Notion content directly — no LLM needed.

Usage:
    python notion_import.py [--dry-run]
"""

import argparse
import logging
import re
import sys

from app.ingestion.notion_ingestion_service import NotionIngestionService
from app.repositories.country_guide_repository import CountryGuideRepository
from app.repositories.provenance_repository import ProvenanceRepository
from app.services.provenance_service import ProvenanceService
from app.utils.config import database_path, load_env_file, parser_version
from app.utils.logging_config import configure_logging

NOTION_PAGE_ID = "7ed6a2f53972448db2cb107a8d20b661"
NOTION_SOURCE_URL = "https://skuad.notion.site/Skuad-Country-Product-Guides-7ed6a2f53972448db2cb107a8d20b661"

# Title-derived names that should be canonicalised before writing to the DB.
COUNTRY_ALIASES = {
    "united arab emirates": "UAE",
}

# Maps Notion field labels (normalised) → section key in our schema.
# Keys are lowercase, parentheticals stripped, separators normalised to spaces.
FIELD_TO_SECTION = {
    "probation period": "probation",
    "notice period during probation": "probation",
    "notice period after probation": "termination_notice",
    "notice period": "termination_notice",
    "severance payable": "termination_notice",
    "working hours": "working_hours",
    "overtime hours": "overtime",
    "overtime": "overtime",
    "end of service benefit": "pension",
    "annual earned leaves": "annual_leave",
    "annual leave": "annual_leave",
    "sick leave": "sick_leave",
    "public holidays": "public_holidays",
    "maternity leave": "maternity_leave",
    "minimum wages": "minimum_wage",
    "minimum wage": "minimum_wage",
    "income tax": "income_tax",
    "social security": "social_security",
    "public health insurance": "health_insurance",
    "private health insurance": "health_insurance",
    "health insurance": "health_insurance",
    "payroll tax": "payroll_tax",
    "pension": "pension",
    "employee benefits": "employee_benefits",
    "employer obligations": "employer_obligations",
    "withholding tax": "withholding_tax",
    "tax filing": "tax_filing",
    "industrial relations": "industrial_relations",
    "workplace safety": "workplace_safety",
    "osh obligations": "osh_obligations",
    "work permit": "work_permit",
    "work visa": "work_visa",
    "expats": "expatriate_employment",
    "expatriate employment": "expatriate_employment",
}

def _canonical_country(name: str) -> str:
    return COUNTRY_ALIASES.get(name.lower(), name.strip())


def _normalise_label(text: str) -> str:
    text = re.sub(r"\(.*?\)", "", text)   # strip parentheticals e.g. (Individual)
    text = re.sub(r"[/,&]", " ", text)    # normalise separators
    return re.sub(r"\s+", " ", text.lower()).strip()


def _match_field(text: str):
    norm = _normalise_label(text)
    if norm in FIELD_TO_SECTION:
        return FIELD_TO_SECTION[norm]
    # Partial match only for short labels (≤30 chars) to avoid matching value text
    if len(norm) <= 30:
        for key, section in FIELD_TO_SECTION.items():
            if key in norm or norm in key:
                return section
    return None


def _parse_sections(text: str) -> dict:
    """
    Parse Notion page text (produced by NotionIngestionService._blocks_to_text)
    into {section_key: value} pairs.

    Notion tables render as lines of the form:
      value | FieldLabel         (most sections — check right side first)
      FieldLabel | value         (Benefits, Termination sections)

    Lines without ' | ' are continuation rows that belong to the next labelled line.
    When the same section key appears twice (e.g. health_insurance from both public
    and private insurance rows), values are merged with a newline.
    """
    sections: dict = {}
    pending: list = []  # unlabelled lines accumulated before a labelled row

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Section header lines (### ...) just reset the pending buffer
        if re.match(r"^#{2,4}\s", line):
            pending = []
            continue

        if " | " in line:
            left, right = line.split(" | ", 1)
            left, right = left.strip(), right.strip()

            # Check right first — most rows are "value | FieldLabel"
            section_key = _match_field(right)
            if section_key:
                value_parts = pending + [left]
                pending = []
            else:
                # Fall back to left — for "FieldLabel | value" rows (Benefits, Termination)
                section_key = _match_field(left)
                if section_key:
                    value_parts = pending + [right]
                    pending = []
                else:
                    pending.append(line)
                    continue

            value = "\n".join(p for p in value_parts if p).strip()
            if value:
                if section_key in sections:
                    sections[section_key] += "\n" + value
                else:
                    sections[section_key] = value
        else:
            pending.append(line)

    return sections


def main():
    parser = argparse.ArgumentParser(description="Import Skuad country guides from Notion")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and parse but do not write to DB")
    args = parser.parse_args()

    load_env_file()
    configure_logging()

    db = database_path()
    repo = CountryGuideRepository(db)
    repo.initialize_schema()

    provenance_repo = ProvenanceRepository(db)
    provenance_repo.initialize_schema()
    provenance_service = ProvenanceService(provenance_repo, parser_version=parser_version())

    notion_service = NotionIngestionService(page_id=NOTION_PAGE_ID)

    print("Auto-discovering all country guides on the Notion page (this takes ~15–20 min due to rate limits)...")
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
