# Regulift — Country Guide Reconciliation

An internal compliance operations platform that automatically detects, reviews, and publishes changes to Skuad's country employment guides — pulling from official government sources and reconciling them against the live guide via a human-in-the-loop review workflow.

---

## What It Does

Employment laws change. Ministry websites update silently. This system crawls official government sources for each country, extracts structured compliance data using Groq (LLaMA 3.3 70B), compares it against the current guide, and surfaces only the meaningful differences for a compliance reviewer to approve or reject — with full audit trail and source attribution.

```
Official Sources → Crawl4AI → LLM Extraction → Reconciliation → Review Queue → Approval → Live Guide
PDF Documents  → pdfplumber ↗
```

---

## Architecture

```
app/
├── api/              # Flask routes (ops dashboard + client guide) with rate limiting
├── drift/            # Compliance drift detection
├── extraction/       # Groq LLM extraction with key rotation
├── ingestion/        # Crawl4AI web crawler + PDF extractor + Notion importer
├── llm/              # Multi-provider LLM layer (Claude, Gemini, Groq)
├── reconciliation/   # Diff engine, severity scoring, change detection
├── repositories/     # PostgreSQL: country_guide, review_queue, audit_log
├── review/           # Approve / reject / escalate workflow
├── services/         # Source registry, sync engine, scheduler
└── utils/            # Config, logging, database abstraction

templates/
├── home.html              # Country selector (/)
├── ops_dashboard_v2.html  # Ops dashboard (/ops)
├── guide_list.html        # Client-facing country list (/guide)
└── guide_country.html     # Client-facing country detail (/guide/<country>)
```

**Database:** PostgreSQL (default) — key tables:
- `country_guide` / `country_guide_versions` — published live values per country x section, with temporal versioning
- `review_queue` — pending / approved / rejected changes with diff metadata
- `audit_log` — immutable decision history
- `source_endpoints` — crawlable government URLs with crawl tracking
- `provenance` — full source attribution for every rule value

SQLite is available as a lightweight fallback for local development (`DATABASE_BACKEND=sqlite`).

---

## Features

### Ops Dashboard (`/ops`)

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

**Sync Modal** — country-chip selector to target specific countries before crawling, conserving LLM quota

**Live Guide tab** — table of all currently published values with source links

**Audit Log tab** — immutable record of every approval and rejection

### Client Guide (`/guide`)

- `/guide` — card grid of all countries with rule counts and last-updated dates
- `/guide/<country>` — full employment guide for a country, grouped by category (Leave, Hours, Compensation, Benefits, Employment, Immigration, Safety) with sticky sidebar navigation

### PDF Intake (`/compliance/intake/pdf`)

Upload compliance PDFs (government gazettes, ministry circulars, labor act amendments) through a 5-step wizard. The system:
1. Extracts text and tables from the PDF using pdfplumber
2. Runs LLM extraction to identify employment rules
3. Reconciles against the live guide and queues changes for review

Supports structured tables, multi-page documents, and metadata tagging (jurisdiction, authority, effective date).

### Compliance Drift Detection (`/api/drift`)

Automated health checks that surface stalled reviews, missing provenance, escalation-worthy items, and stale rules.

---

## Data Sources

Official sources are configured in [`data/official-sources.json`](data/official-sources.json) (or fetched from a remote URL at startup). Each source endpoint maps to a country and one or more guide sections.

**Supported countries:** 87 countries across APAC, EMEA, and Americas — 349 active government source endpoints, 104 inactive (domain down or geo-restricted)

**Seeding:** Run `python3 notion_import.py` to import the baseline guide from the internal Skuad Notion page — no LLM required, uses direct pipe-separated table parsing.

---

## Setup

### Prerequisites
- Python 3.13+ (3.10 minimum)
- PostgreSQL 14+ (or set `DATABASE_BACKEND=sqlite` for local dev)
- Groq API key(s) — [console.groq.com](https://console.groq.com) (extraction)
- Anthropic API key(s) — [console.anthropic.com](https://console.anthropic.com) (change classification)
- Notion integration token (for initial seed only)

### Install

```bash
pip install -r requirements.txt
crawl4ai-setup  # install browser dependencies for Crawl4AI
```

### Environment

Create `.env` in the project root:

```env
# Database (PostgreSQL is default)
DATABASE_URL=postgresql://localhost/country_guides

# LLM providers (comma-separated for key rotation)
GROQ_API_KEYS=key1,key2
ANTHROPIC_API_KEYS=key1,key2

# Notion (for seeding baseline data)
NOTION_TOKEN=secret_...
NOTION_PAGE_ID=...

# Optional
SYNC_CRON_SCHEDULE=0 8 * * *      # daily sync at 08:00 UTC
SLACK_WEBHOOK_URL=https://...      # sync alerts
GEMINI_API_KEYS=key1               # alternative reconciliation provider
```

### Run

```bash
# Seed the database from Notion (one-time, or re-run to refresh baseline)
python3 notion_import.py

# Start the server
python3 app.py
```

Open `http://localhost:8080`.

### Docker

```bash
docker-compose up
```

This spins up Postgres 16 + the app on port 8080. Set `POSTGRES_PASSWORD` in your environment for non-default credentials.

---

## Sync Workflow

1. Click **Sync Now** on the ops dashboard
2. Select countries to crawl (conserves LLM quota)
3. For each source endpoint: Crawl4AI fetch → snapshot → LLM extract → reconcile against live guide
4. Changes appear in the **Review Queue** with severity, confidence score, and source evidence
5. Click **Preview** on any card to open the publication preview overlay
6. Toggle **Before / After** to compare the current guide against the post-publish state
7. Click **Publish This Change** → review the confirmation modal → change is written to the live guide and audit log

---

## API Rate Limiting

All API endpoints are rate-limited via Flask-Limiter (200 req/min default). Heavier endpoints have stricter limits:

| Endpoint | Limit |
|---|---|
| `POST /api/sync` | 5/min |
| `POST /api/intake/pdf` | 10/min |
| `POST /api/employee/ask` | 10/min |
| `POST /api/approve`, `/api/reject` | 30/min |
| `POST /api/bulk-approve` | 10/min |
| All other endpoints | 200/min |

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| PostgreSQL (default) | Production-grade, supports concurrent access, temporal queries, and JSONB |
| Crawl4AI for web ingestion | Headless browser handles JS-heavy government sites, built-in markdown extraction, more robust than raw HTTP + BeautifulSoup |
| pdfplumber for PDF intake | Extracts text and tables from uploaded compliance PDFs; feeds into the same LLM extraction pipeline as web sources |
| Groq (LLaMA 3.3 70B) for extraction | Fast inference, generous free tier, strong at structured extraction |
| Claude (claude-sonnet-4-6) for classification | Different vendor than extraction — a Groq outage doesn't block classification |
| Multi-key rotation | Rotates to the next key on `RateLimitError` — handles quota exhaustion per vendor |
| Flask-Limiter | Per-IP rate limiting on all API endpoints, stricter on mutation/LLM-consuming routes |
| Notion import without LLM | Pipe-separated table structure is deterministic; no tokens wasted on baseline data |
| Human-in-the-loop approval | LLM extraction is imperfect — every change requires explicit approval before going live |
| SQLite fallback | Available for quick local development without running Postgres |

---

## Status

Production-ready MVP. The end-to-end pipeline is functional across 87 countries (349 active source endpoints) with rate limiting, PostgreSQL, PDF ingestion, Crawl4AI headless browser for JS-heavy sites, and automated drift detection.
