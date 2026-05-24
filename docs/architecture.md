# Architecture

## System Overview

```
Official Sources → Ingestion → Extraction → Reconciliation → Review Queue → Approval → Live Guide
```

The platform follows a pipeline architecture where each stage is independently testable and observable.

## Project Structure

```
app/
├── api/                    # Flask routes (home, ops dashboard, client guides)
├── extraction/             # Groq LLM extraction with key rotation + content chunking
├── ingestion/              # HTML fetcher + Notion importer + snapshot tracking
├── reconciliation/         # Semantic diff engine, severity scoring, change detection
├── repositories/           # SQLite abstraction layer (6 repositories)
├── review/                 # Approval/rejection workflow
├── drift/                  # Compliance drift detection
├── models/                 # Domain models (EmploymentRule, SourceEndpoint, WorkflowResults)
├── services/               # Core orchestration (sync, registry, provenance, scheduler, slack)
└── utils/                  # Config loading, logging
```

## Database Schema

SQLite with the following tables:

| Table | Purpose |
|-------|---------|
| `country_guide` | Active published rules (country × section) |
| `country_guide_versions` | Immutable version history for temporal queries |
| `review_queue` | Pending/approved/rejected changes with diffs |
| `audit_log` | Immutable decision history |
| `source_snapshots` | Ingested HTML snapshots |
| `provenance` | Source metadata (URL, confidence, parser version) |
| `ingestion_jobs` | Sync job tracking |
| `drift_reports` | Compliance drift records |

## Key Design Decisions

**SQLite** — Zero-ops, simple schema, appropriate for current data volumes.

**Groq (LLaMA 3.3 70B)** — Fast inference, generous free tier, strong at structured extraction from HTML.

**Multi-key rotation** — Gracefully handles Groq rate limits by cycling through API keys.

**Human-in-the-loop** — LLM extraction is imperfect; every change requires explicit reviewer sign-off before publication.

**Temporal versioning** — Immutable version history enables compliance audit trail and point-in-time rule lookups.

**External source registry** — Source URLs are maintained in a separate config, allowing URL updates without redeployment.
