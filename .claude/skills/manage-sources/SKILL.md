---
name: manage-sources
description: >
  Official government source registry — look up, list, add, update, fix, and remove source
  endpoints in data/official-sources.json and sync changes to the live database.

  Trigger on ANY of these:
  - Lookup queries: "What is the official website for employment law in Singapore?",
    "Where can I find UAE work permit rules?", "Which authority handles tax in India?",
    "Give me official sources for labour law in Australia", "What government site covers
    social security in the Philippines?"
  - Source management: view sources, list endpoints, check which government sites are monitored,
    see source coverage, add a new country or endpoint, fix a broken URL, remove a stale source,
    update source metadata, reseed/resync the source registry
  - Country + domain compliance source questions for any of the 87 covered countries
  - Questions about which government authority or portal covers a compliance matter
  - Any question asking for an official government URL for employment, tax, immigration,
    legislation, or workplace safety
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

## Domains covered

| Domain Key | Covers |
|---|---|
| `labour_employment` | Employment law, minimum wage, termination, leave entitlements, disputes |
| `legislative` | National Acts, statutes, official gazettes, legislation databases |
| `tax_social_security` | Income tax, payroll, VAT/GST, pension, social insurance contributions |
| `immigration_work_permits` | Work visas, work permits, residency, employer obligations |
| `workplace_safety` | OSH legislation, regulators, incident reporting, codes of practice |

## Step 0 — Understand the request

Classify the user's intent:

| Intent | Action |
|---|---|
| **Look up** a source for a country + domain | Read the JSON → answer (Step 1a) |
| **List / inspect** sources | Read the DB via the API or the JSON file (Step 1b) |
| **Add** a country, authority, or endpoint | Edit the JSON, then reseed |
| **Update** a URL, metadata, or sections | Edit the JSON, then reseed |
| **Remove** an entry | Edit the JSON, then reseed |
| **Fix** a broken URL | Edit the JSON, then reseed |
| **Reseed** the DB from JSON | Run the reseed script only |

For any mutation: **always edit `data/official-sources.json` first, then reseed.** Never
edit the database directly — the JSON is the source of truth.

## Step 1a — Answer a lookup query

When the user asks "What is the official source for X in country Y?" or similar:

1. Read `data/official-sources.json`
2. Find the authority for that country + domain; present its **name**, **website_url**, and **notes**
3. List the most relevant `source_endpoints` with their `url` and `sections_covered`
4. Always include the direct URL — never paraphrase it away

### Presentation rules

- **Single country**: Bold the authority name, show URL on its own line, then list 1-3 relevant endpoints
- **Multiple countries**: Present as a comparison table: Country | Authority | URL | Key Notes
- **`escalation_required: true`**: Add a warning — "Verify this URL before use — this portal restructures without notice."
- **`precedence_rank`**: When multiple authorities cover the same domain, show rank 1 first. Rank 2+ are secondary — mention but don't lead with them.
- **`supports_replay: false`**: Flag — "Content may not be available online; check directly or contact the authority."
- **Country not in database**: State clearly that it is not yet covered. Suggest the general government portal as a starting point. Do NOT fabricate URLs.

### Example queries this handles

- "What is the official website for employment law in Singapore?"
- "Where can I find the UAE work permit rules for foreign employees?"
- "What government site covers tax and social security for employers in the Philippines?"
- "Give me the official sources for labour law and immigration in India and Australia"
- "What authority handles work visas in New Zealand?"

## Step 1b — Read current state (for list/inspect/management)

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
