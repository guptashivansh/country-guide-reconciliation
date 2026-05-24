# Provenance & Audit Trail

## Chain of Custody Architecture

In regulated compliance environments, the question "where did this rule come from?" must be answerable with documentary evidence, not verbal assurance. The provenance system provides a complete, immutable chain of custody for every published employment rule: from the government document that was its origin, through the extraction that interpreted it, through the human decision that authorized its publication.

This chain cannot be retroactively modified. Every link in it is written at the time the corresponding event occurs, linked by foreign key to adjacent links, and accessible via a single chain resolution query.

---

## The Five-Link Provenance Chain

```
┌──────────────────────────────────────────────────────────┐
│  LINK 1: Government Source                               │
│  source_url — the official government page               │
│  Answers: "What is the authoritative source?"            │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│  LINK 2: Crawl Event (ingestion_jobs)                    │
│  ingestion_job_id — timestamps for every pipeline stage  │
│  Answers: "When was the source fetched and processed?"   │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│  LINK 3: Source Snapshot (source_snapshots)              │
│  snapshot_id, content_hash — archived raw content        │
│  Answers: "What did the source say when it was crawled?" │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│  LINK 4: Extraction (rule_provenance.extraction_*)       │
│  extraction_confidence, parser_version, source_fragment  │
│  Answers: "How did the AI interpret the source? How      │
│            confident was it? Which model version?"       │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│  LINK 5: Review Decision (rule_provenance.reviewer_*)    │
│  reviewer_action, reviewer_assignee, reviewer_rationale  │
│  Answers: "Who authorized this rule? Why? When?"         │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│  PUBLISHED RULE (country_guide)                          │
│  current_provenance_id — FK to most recent provenance    │
│  Answers: "What is the current authoritative rule?"      │
└──────────────────────────────────────────────────────────┘
```

The `country_guide.current_provenance_id` column is the entry point for chain resolution. One query following this FK through LEFT JOINs to all linked tables reconstructs the complete chain.

---

## Provenance Record Schema

```sql
CREATE TABLE rule_provenance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    country TEXT NOT NULL,
    section TEXT NOT NULL,
    rule_value TEXT,

    -- Chain links
    review_queue_id INTEGER,       -- The review item that was approved
    source_snapshot_id INTEGER,    -- The snapshot that was the evidence basis
    ingestion_job_id INTEGER,      -- The crawl job that produced the snapshot

    -- Source evidence (denormalized for chain immutability)
    source_url TEXT,               -- Preserved at chain creation time
    source_hash TEXT,              -- MD5 of snapshot content at chain creation time
    source_fragment TEXT,          -- The exact text excerpt that produced the extraction

    -- Extraction metadata
    extraction_confidence REAL,    -- LLM confidence at time of extraction
    parser_version TEXT,           -- Model version string (e.g., "groq/llama-3.3-70b-versatile/v1")

    -- Reviewer decision
    reviewer_action TEXT,          -- 'approved' | 'bulk_approved' | 'seeded'
    reviewer_assignee TEXT,        -- Who authorized the publication
    reviewer_rationale TEXT,       -- Why they approved it
    reviewer_comment TEXT,         -- Optional additional context

    -- Timestamps
    crawled_at TEXT,               -- When the source was fetched
    extracted_at TEXT,             -- When extraction completed
    reviewed_at TEXT,              -- When the human decision was made
    created_at TEXT NOT NULL       -- When this provenance record was created
)
```

**Denormalization is intentional.** Fields like `source_url`, `source_hash`, and `source_fragment` are also stored in `source_snapshots` and `review_queue`. They are duplicated into `rule_provenance` because the provenance chain must be a self-contained record — even if the original `review_queue` item or `source_snapshot` row were hypothetically altered (which the system prevents), the provenance record preserves the state at the time of publication.

---

## Provenance Creation Points

Provenance records are created in exactly three circumstances:

### 1. Individual Approval

`ReviewService.approve_review_item()` → `ProvenanceService.record_approval()`

The provenance record is written in the same transaction as the rule publication. If provenance recording fails, the entire transaction rolls back and the rule is not published. A published rule always has a provenance record.

### 2. Bulk Approval

`ReviewService.bulk_approve_non_critical()` → `ProvenanceService.record_bulk_approval()`

Each item approved in a bulk operation receives its own individual provenance record with `reviewer_action = 'bulk_approved'`. Bulk approval is not a single record covering multiple items — it generates N records for N items. An auditor examining a bulk-approved item sees the same chain detail as an individually approved item.

### 3. Seed Import

`notion_import.py` → `ProvenanceService.record_seed()`

Rules imported from the initial Notion baseline carry `reviewer_action = 'seeded'`. These records have no extraction confidence, no source snapshot, and no individual reviewer. They represent the organization's pre-pipeline state. Auditors should understand that seeded rules have reduced traceability and should be treated as a starting baseline that will be superseded by pipeline-detected changes over time.

---

## Chain Resolution

The `ProvenanceRepository.get_current_chain()` method resolves the complete chain for any (country, section) pair in a single query with LEFT JOINs:

```json
{
    "canonical_rule": {
        "country": "India",
        "section": "minimum_wage",
        "value": "INR 23,500/month for scheduled employment",
        "last_updated": "2025-04-01T00:00:00"
    },
    "reviewer_action": {
        "action": "approved",
        "assignee": "divya@compliance.team",
        "rationale": "Confirmed in Budget 2025 gazette notification",
        "comment": "Rate effective from April 1, 2025",
        "reviewed_at": "2025-03-15T14:30:00"
    },
    "extraction": {
        "confidence": 0.92,
        "parser_version": "groq/llama-3.3-70b-versatile/v1",
        "source_fragment": "The minimum wage for scheduled employment in central sphere...",
        "source_hash": "a1b2c3d4e5f6..."
    },
    "source_snapshot": {
        "snapshot_id": 142,
        "content_hash": "md5:abcdef1234567890",
        "captured_at": "2025-03-14T08:00:00",
        "extraction_status": "succeeded"
    },
    "crawl_event": {
        "ingestion_job_id": 89,
        "source_url": "https://labour.gov.in/...",
        "state": "reconciled",
        "queued_at": "2025-03-14T07:59:00",
        "fetched_at": "2025-03-14T08:00:02",
        "reconciled_at": "2025-03-14T08:01:30"
    }
}
```

If any link in the chain is absent (for example, an ingestion job was deleted, or a seeded rule has no snapshot), the LEFT JOIN returns null for the missing link. The chain resolution does not fail — it returns a partially-linked chain. This is the correct behavior: a missing link is a finding that should be investigated, not a reason to return an error to the auditor querying the chain.

---

## Historical Chain Access

For rules that have been superseded, the full history of provenance records is accessible via `ProvenanceRepository.get_history()`. This returns all provenance records for a (country, section) pair, ordered chronologically, covering every rule version that has ever been published.

An auditor can use this to reconstruct the full regulatory history of any section:
- When did the first rule get published?
- Who approved each subsequent change?
- What was the evidence for each version?
- Which model version extracted each rule?

---

## Compliance Defensibility Scenarios

**Scenario 1: External audit question — "How do you know India's minimum wage is INR 23,500?"**

Response chain using the provenance API:
1. `GET /api/provenance/India/minimum_wage` returns the current chain
2. The rule was approved on 2025-03-15 by Divya with rationale "Confirmed in Budget 2025 gazette notification"
3. The AI extracted it with 92% confidence from the Ministry of Labour website
4. The source page was captured on 2025-03-14; content hash `md5:abcdef...` confirms integrity
5. The extraction used model `groq/llama-3.3-70b-versatile/v1`

Each of these facts is in the database, not in someone's recollection.

**Scenario 2: Employment dispute — "What leave entitlement applied in Singapore during Q3 2024?"**

1. `GET /api/guide/Singapore/annual_leave/at?date=2024-09-15` returns the rule effective on that date
2. The temporal query returns version 2 of the Singapore annual leave rule, effective 2024-07-01, superseded 2025-01-01
3. `GET /api/provenance/Singapore/annual_leave` retrieves the full chain for the current version
4. `GET /api/guide/Singapore/annual_leave/history` provides the complete version timeline showing when this version was published and by whom

**Scenario 3: Internal investigation — "A rule was published with an incorrect value. Who approved it?"**

1. `GET /api/audit?country=India&section=minimum_wage` returns all audit log entries for this rule
2. The approval event shows the reviewer, their rationale, and the before/after values
3. The provenance chain for the version shows which source snapshot was the evidence basis
4. The correction was published on [date] with correction rationale — also visible in the audit log

---

## Parser Version Governance

Every provenance record includes `parser_version` (currently `"groq/llama-3.3-70b-versatile/v1"`). This enables:

**Quality regression detection:** If Groq changes the underlying model behavior or a new model version is deployed, the `parser_version` change is recorded in all provenance records created after the change. If extraction quality degrades, affected rules can be identified by their `parser_version`.

**Model lineage audit:** Organizations with AI governance requirements can demonstrate that they track which AI model version produced each extracted value.

**Migration traceability:** When the extraction model is upgraded, all historical provenance records retain their original `parser_version`. The record of which model produced a given rule is permanent.

---

## Append-Only Guarantees

The provenance system provides the following write-access guarantees:

- `ProvenanceRepository.write()` — INSERT only. No UPDATE method exists.
- `ProvenanceRepository.set_current()` — UPDATE on `country_guide.current_provenance_id` only. This is the only update operation that relates to provenance, and it sets a pointer, not provenance content.
- No API endpoint accepts PUT or DELETE requests against provenance data.
- Database-level: no application code path issues UPDATE or DELETE against `rule_provenance`.

---

## API Reference

| Endpoint | Purpose |
|----------|---------|
| `GET /api/provenance/<country>` | Current provenance chains for all sections in a country |
| `GET /api/provenance/<country>/<section>` | Full chain for a single rule |
| `GET /api/provenance/<country>/<section>/history` | All historical provenance records (all versions) |

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Broken chain — snapshot or job record missing | LEFT JOINs return null for missing links; chain is partially resolved, not errored; incomplete chains are visible and investigable |
| Provenance written without corresponding approval | Transaction atomicity — provenance and approval are in the same transaction; one cannot exist without the other |
| Seeded rules have no reviewer | `reviewer_action = 'seeded'` explicitly marks pre-pipeline rules; auditors understand these are baseline imports, not reviewed changes |
| Model version not recorded | `parser_version` defaults to the constructor parameter on `GroqExtractionService`; new deployments must update this string |
| Source fragment modified post-hoc | Source fragments are stored in the provenance record, not fetched live; they reflect the state at extraction time; snapshot content hash provides integrity verification |
