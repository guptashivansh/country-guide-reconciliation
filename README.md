# Country Guide Reconciliation

An internal compliance operations platform that automatically detects, reviews, and publishes changes to Skuad's country employment guides — pulling from official government sources and reconciling them against the live guide via a human-in-the-loop review workflow.

---

## What It Does

Employment laws change. Ministry websites update silently. This system crawls official government sources for each country, extracts structured compliance data using Groq (LLaMA 3.3 70B), compares it against the current guide, and surfaces only the meaningful differences for a compliance reviewer to approve or reject — with full audit trail and source attribution.

```
Official Sources → Ingestion → Extraction → Reconciliation → Review Queue → Approval → Live Guide
```

---

## Architecture

```
app/
├── api/              # Flask routes (ops dashboard + client guide)
├── extraction/       # Groq LLM extraction with key rotation
├── ingestion/        # HTML fetcher + Notion importer
├── reconciliation/   # Diff engine, severity scoring, change detection
├── repositories/     # SQLite: country_guide, review_queue, audit_log
├── review/           # Approve / reject / escalate workflow
├── services/         # Source registry (official-sources.json)
└── utils/            # Config, logging

templates/
├── index.html         # Ops dashboard (/)
├── guide_list.html    # Client-facing country list (/guide)
└── guide_country.html # Client-facing country detail (/guide/<country>)
```

**Database:** SQLite (`country_guides.db`) — three tables:
- `country_guide` — published live values per country × section
- `review_queue` — pending / approved / rejected changes with diff metadata
- `audit_log` — immutable decision history

---

## Features

### Ops Dashboard (`/`)

**Compliance Metrics Header** — 7 real-time cards:
Sources Monitored · Pending Reviews · Critical Changes · Avg Confidence · Crawl Failures · Last Successful Sync · Trusted Sources

**Review Queue** — per-change review cards with:
- Semantic word-level diff (current value vs. proposed)
- AI impact assessment (Critical / Moderate / Low / Informational)
- Source evidence excerpt with attribution
- Provenance drawer (source URL, trust level, parser confidence, model version)
- Severity + change-type classification (Added / Modified / Clarification / Deprecated / Unverified / Removed)
- Filterable by severity, confidence, country, source type, change type, status

**Publication Preview Mode** — before publishing any change:
- Full-screen Notion-style document preview of the country guide
- Before / After toggle to compare current vs. proposed state
- Newly inserted sections highlighted with badges and coloured borders
- Controlled confirmation modal — the DB write only happens on explicit confirm

**Sync Modal** — country-chip selector to target specific countries before crawling, conserving Groq quota

**Live Guide tab** — table of all currently published values with source links

**Audit Log tab** — immutable record of every approval and rejection

### Client Guide (`/guide`)

- `/guide` — card grid of all countries with rule counts and last-updated dates
- `/guide/<country>` — full employment guide for a country, grouped by category (Leave, Hours, Compensation, Benefits, Employment, Immigration, Safety) with sticky sidebar navigation

---

## Data Sources

Official sources are configured in a separate repo ([compliance-data](https://github.com/guptashivansh/compliance-data)) as a JSON file fetched at startup. Each source endpoint maps to a country and one or more guide sections.

**Supported countries:** India, Australia, Singapore, South Africa, UAE, New Zealand, Philippines, Pakistan

**Seeding:** Run `notion_import.py` to import the baseline guide from the internal Skuad Notion page — no LLM required, uses direct pipe-separated table parsing.

---

## Setup

### Prerequisites
- Python 3.9+
- Groq API key(s) — [console.groq.com](https://console.groq.com) (extraction)
- Anthropic API key(s) — [console.anthropic.com](https://console.anthropic.com) (change classification)
- Notion integration token (for initial seed only)

### Install

```bash
pip install -r requirements.txt
```

### Environment

Create `.env` in the project root:

```env
GROQ_API_KEYS=key1,key2           # comma-separated, no quotes around individual keys — used for extraction
ANTHROPIC_API_KEYS=key1,key2      # comma-separated, no quotes around individual keys — used for change classification
NOTION_TOKEN=secret_...
NOTION_PAGE_ID=...                # root Skuad country guides Notion page ID
COUNTRY_GUIDE_DB=country_guides.db
OFFICIAL_SOURCES_JSON_URL=https://raw.githubusercontent.com/guptashivansh/compliance-data/main/data/official-sources.json
```

### Run

```bash
# Seed the database from Notion (one-time, or re-run to refresh baseline)
python3 notion_import.py

# Start the server
python3 app.py
```

Open `http://localhost:8080`.

> **macOS note:** Port 5000 is reserved by AirPlay Receiver on macOS Ventura+. The app defaults to 8080.

---

## Sync Workflow

1. Click **Sync Now** on the ops dashboard
2. Select countries to crawl (conserves Groq quota)
3. For each source endpoint: fetch HTML → snapshot → LLM extract → reconcile against live guide
4. Changes appear in the **Review Queue** with severity, confidence score, and source evidence
5. Click **👁 Preview** on any card to open the publication preview overlay
6. Toggle **Before / After** to compare the current guide against the post-publish state
7. Click **Publish This Change** → review the confirmation modal → change is written to the live guide and audit log

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| SQLite | Zero-ops for a hackathon; the data model is simple and volumes are small |
| Groq (LLaMA 3.3 70B) for extraction | Fast inference, generous free tier, strong at structured extraction |
| Claude (claude-sonnet-4-6) for change classification | Different vendor than extraction, so a Groq outage or quota exhaustion doesn't also block classification, and vice versa |
| Multi-key rotation | Rotates to the next key on `RateLimitError` — handles quota exhaustion gracefully, per vendor |
| Notion import without LLM | Pipe-separated table structure is deterministic; no tokens wasted on baseline data |
| Human-in-the-loop approval | LLM extraction is imperfect — every change requires explicit approval before going live |
| Official sources as external JSON | Separate lifecycle from the app; update source URLs without redeploying |

---

## Status

Built as a hackathon prototype. The end-to-end pipeline is functional for 8 countries. Not production-hardened.
