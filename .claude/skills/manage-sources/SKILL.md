---
name: manage-sources
description: >
  List, inspect, add, update, fix, and remove official government source endpoints in
  data/official-sources.json and sync changes to the live database.
  Use when the user asks to: view sources, list endpoints, check which government sites are
  monitored, see source coverage, add a new country or endpoint, fix a broken URL, remove a
  stale source, update source metadata, or reseed/resync the source registry from the JSON file.
---

# Manage Sources — Agentic Skill

This skill manages the **official government source registry** used by the compliance sync
pipeline. Sources are defined in `data/official-sources.json` (the single source of truth) and
loaded into the database at startup.

## Architecture

```
data/official-sources.json   ← canonical file, checked into this repo
        ↓ (reseed script)
source_countries / source_authorities / source_endpoints / parser_registry   ← DB tables
        ↓
sync pipeline crawls endpoints → extraction → reconciliation → review queue
```

## Step 0 — Understand the request

Classify the user's intent:

| Intent | Action |
|---|---|
| **List / inspect** sources | Read the DB via the API or the JSON file |
| **Add** a country, authority, or endpoint | Edit the JSON, then reseed |
| **Update** a URL, metadata, or sections | Edit the JSON, then reseed |
| **Remove** an entry | Edit the JSON, then reseed |
| **Fix** a broken URL | Edit the JSON, then reseed |
| **Reseed** the DB from JSON | Run the reseed script only |
| **Look up** what authority covers a domain for a country | Read the JSON |

For any mutation: **always edit `data/official-sources.json` first, then reseed.** Never
edit the database directly — the JSON is the source of truth.

## Step 1 — Read current state

For listing / inspecting, use the running API if the server is up:

```bash
# Stats
curl -s http://localhost:8080/api/sources/stats

# All endpoints for a country
curl -s "http://localhost:8080/api/sources/endpoints?country=India"

# All countries
curl -s http://localhost:8080/api/sources/countries
```

Or read the JSON directly:

```bash
python3 -c "
import json
with open('data/official-sources.json') as f:
    data = json.load(f)
print(f\"{len(data['countries'])} countries, {len(data['authorities'])} authorities, {len(data['source_endpoints'])} endpoints\")
"
```

## Step 2 — Mutate the JSON (when adding, updating, removing, or fixing)

Open `data/official-sources.json` with the Read tool, locate the relevant section, and edit it
using the Edit tool. Follow the schema rules below.

### ID conventions

| Array | ID format | Example |
|---|---|---|
| `countries` | `country_{ISO}` | `country_MY` |
| `authorities` | `auth_{ISO}_{domain_slug}` | `auth_MY_labour` |
| `source_endpoints` | `ep_{ISO}_{short_descriptor}` | `ep_MY_mohr_employment_act` |
| `parser_registry` | `parser_{parser_key}` | `parser_html_readability_v1` |

### Required fields per array

**countries**: `id`, `iso_code`, `name`, `is_active`, `created_at`, `updated_at`

**authorities**: `id`, `country_id`, `name`, `authority_type`, `website_url`, `trust_level`,
`precedence_rank`, `is_active`, `notes`, `owner_team`, `owner_user_id`, `reviewer_group`,
`escalation_required`, `supports_replay`, `created_at`, `updated_at`

Valid `authority_type`: `labor_ministry`, `tax_authority`, `social_security`,
`immigration_authority`, `official_gazette`, `other`

**source_endpoints**: `id`, `authority_id`, `name`, `url`, `source_type`, `content_language`,
`sections_covered`, `authority_category`, `extraction_strategy`, `parser_key`,
`crawl_frequency`, `change_detection_strategy`, `requires_authentication`,
`is_javascript_heavy`, `supports_incremental_diffs`, `is_human_curated`, `status`,
`last_crawled_at`, `last_successful_crawl_at`, `last_change_detected_at`, `owner_team`,
`owner_user_id`, `reviewer_group`, `escalation_required`, `supports_replay`, `notes`,
`created_at`, `updated_at`

Valid `sections_covered` values: `working_hours`, `overtime`, `minimum_wage`,
`termination_notice`, `probation`, `social_security`, `employee_benefits`, `maternity_leave`,
`annual_leave`, `payroll_tax`, `visa_types`, `work_permit_process`, `osh_legislation`,
`incident_reporting`, `ppe_obligations`

Valid `extraction_strategy` / `parser_key` pairs:
- `html_readability` / `html_readability_v1` — standard HTML pages
- `ocr_pdf` / `pdf_ocr_v1` — scanned PDFs
- `playwright` / `playwright_spa_v1` — JavaScript-heavy SPAs
- `css_selector` / `css_selector_v1` — well-structured HTML with stable DOM

### When adding a new country

You **must** add entries to all three arrays: one `countries` entry, one `authorities` entry per
domain (5 domains: `labour_employment`, `legislative`, `tax_social_security`,
`immigration_work_permits`, `workplace_safety`), and at least one `source_endpoints` entry per
authority.

Use WebSearch or WebFetch to find correct official government URLs — **never guess URLs**.
After finding a URL, verify it resolves:

```bash
curl -sI "https://example.gov.xx" | head -5
```

### When fixing a URL

1. Find the broken entry in the JSON (search by country ISO or old URL)
2. WebSearch for the correct replacement URL
3. Verify the new URL resolves
4. Edit the JSON with the corrected URL
5. Update `updated_at` to today's ISO date

### Updating metadata.last_updated

After any mutation, update the `metadata.last_updated` field at the top of the JSON to today's
ISO date.

## Step 3 — Reseed the database

After editing the JSON, always run the reseed script to push changes to the live DB:

```bash
python3 scripts/reseed_sources.py
```

This clears all four registry tables and re-imports from `data/official-sources.json`.

Verify the change took effect:

```bash
# Check a specific country
curl -s "http://localhost:8080/api/sources/endpoints?country=<Country Name>"

# Or check stats
curl -s http://localhost:8080/api/sources/stats
```

## Step 4 — Report results

Tell the user:
- What was changed in the JSON (added/updated/removed entries)
- The reseed result (country/authority/endpoint counts)
- Verification that the change is live in the API
- Suggest "Run **sync** to crawl the new/updated sources now" if endpoints were added or URLs changed
