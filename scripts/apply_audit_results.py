#!/usr/bin/env python3
"""Apply audit results to update official-sources.json and reseed the DB.

Reads data/audit-results.json (produced by audit_endpoint_links.py) and:
1. Generates data/official-sources-updated.json with landing pages deactivated
   and sub-page endpoints created
2. Optionally reseeds the DB from the updated JSON

Usage:
    python3 scripts/apply_audit_results.py              # generate updated JSON
    python3 scripts/apply_audit_results.py --reseed      # also reseed DB
    python3 scripts/apply_audit_results.py --replace      # overwrite original JSON
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

SOURCES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "official-sources.json")
RESULTS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "audit-results.json")
UPDATED_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "official-sources-updated.json")


def load_json(path):
    with open(path) as f:
        return json.load(f)


def get_all_sections(data):
    sections = set()
    for ep in data["source_endpoints"]:
        for s in ep.get("sections_covered", []):
            sections.add(s)
    return sections


def apply_audit(data, results):
    all_sections = get_all_sections(data)
    results_by_id = {r["endpoint_id"]: r for r in results if r.get("status") == "ok"}

    new_endpoints = []
    stats = {"kept": 0, "deactivated": 0, "sub_pages_created": 0, "skipped": 0}

    for ep in data["source_endpoints"]:
        result = results_by_id.get(ep["id"])

        if not result:
            new_endpoints.append(ep)
            stats["kept"] += 1
            continue

        if result["page_type"] == "content":
            new_endpoints.append(ep)
            stats["kept"] += 1
            continue

        sub_pages = result.get("sub_pages", [])
        valid_subs = []
        for sp in sub_pages:
            sp_sections = [s for s in sp.get("sections", []) if s in all_sections]
            if sp_sections and sp.get("url"):
                valid_subs.append({"url": sp["url"], "sections": sp_sections, "description": sp.get("description", "")})

        if not valid_subs:
            new_endpoints.append(ep)
            stats["kept"] += 1
            continue

        landing_ep = dict(ep)
        landing_ep["status"] = "landing_page"
        landing_ep["notes"] = f"Landing page — {len(valid_subs)} sub-pages resolved by audit"
        new_endpoints.append(landing_ep)
        stats["deactivated"] += 1

        for j, sp in enumerate(valid_subs):
            sub_id = f"{ep['id']}_sub{j+1}"
            sub_ep = {
                "id": sub_id,
                "authority_id": ep["authority_id"],
                "name": f"{ep.get('name', '')} — {sp['description'][:60]}" if sp.get("description") else f"{ep.get('name', '')} — sub-page {j+1}",
                "url": sp["url"],
                "source_type": ep.get("source_type", "html"),
                "content_language": ep.get("content_language", "en"),
                "sections_covered": sp["sections"],
                "authority_category": ep.get("authority_category", ""),
                "extraction_strategy": ep.get("extraction_strategy", "html_readability"),
                "parser_key": ep.get("parser_key", "html_readability_v1"),
                "crawl_frequency": ep.get("crawl_frequency", "monthly"),
                "change_detection_strategy": ep.get("change_detection_strategy", "semantic"),
                "requires_authentication": ep.get("requires_authentication", False),
                "is_javascript_heavy": ep.get("is_javascript_heavy", False),
                "supports_incremental_diffs": True,
                "is_human_curated": False,
                "status": "active",
                "last_crawled_at": None,
                "last_successful_crawl_at": None,
                "last_change_detected_at": None,
                "owner_team": ep.get("owner_team", ""),
                "owner_user_id": None,
                "reviewer_group": None,
                "escalation_required": False,
                "supports_replay": True,
                "parent_endpoint_id": ep["id"],
                "created_at": "2026-07-02T00:00:00Z",
                "updated_at": "2026-07-02T00:00:00Z",
            }
            new_endpoints.append(sub_ep)
            stats["sub_pages_created"] += 1

    updated = json.loads(json.dumps(data))
    updated["source_endpoints"] = new_endpoints
    return updated, stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reseed", action="store_true", help="Reseed DB after generating updated JSON")
    parser.add_argument("--replace", action="store_true", help="Overwrite original official-sources.json")
    args = parser.parse_args()

    data = load_json(SOURCES_PATH)
    results = load_json(RESULTS_PATH)

    print(f"Loaded {len(data['source_endpoints'])} endpoints and {len(results)} audit results")

    updated, stats = apply_audit(data, results)

    print(f"\nResults:")
    print(f"  Kept as-is:         {stats['kept']}")
    print(f"  Landing → inactive: {stats['deactivated']}")
    print(f"  Sub-pages created:  {stats['sub_pages_created']}")
    print(f"  Total endpoints:    {len(updated['source_endpoints'])}")

    out_path = SOURCES_PATH if args.replace else UPDATED_PATH
    with open(out_path, "w") as f:
        json.dump(updated, f, indent=2)
    print(f"\nWritten to: {out_path}")

    if args.reseed:
        from app.utils.config import load_env_file, official_sources_json_url
        from app.repositories.source_endpoint_repository import TrustedSourceEndpointRepository
        from app.utils.db import Database

        load_env_file()
        db = Database()
        repo = TrustedSourceEndpointRepository(db, json_url=official_sources_json_url())
        repo.initialize_schema()
        repo.reseed_from_file(out_path)
        s = repo.get_registry_stats()
        print(f"\nReseeded DB: {s['countries']} countries, {s['authorities']} authorities, {s['endpoints']} endpoints")


if __name__ == "__main__":
    main()
