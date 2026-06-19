# Platform Architecture

## Governance Architecture Overview

This system implements a provenance-first compliance governance pipeline. Its architecture reflects a specific set of engineering commitments about what the system guarantees, where human authority is mandatory, and what failure modes are acceptable versus unacceptable.

The central architectural concern is not performance or developer ergonomics — it is **auditability under adversarial scrutiny**. Every design decision is evaluated against the question: "If an external auditor or regulator examined this system's behavior, would they find it defensible?"

---

## System Invariants

These properties hold regardless of configuration, load, or operational context. They are enforced at the code level and cannot be disabled:

1. **No rule is published without human approval.** The `country_guide` table is only updated through `approve_pending_review_item()`. No API endpoint, background job, or migration script writes to `country_guide.value` directly.

2. **No approval occurs without an audit record.** Approval and audit log insertion are executed within the same database transaction. A failure in audit log insertion rolls back the entire approval.

3. **Audit records are never modified.** The `audit_log` table has no UPDATE or DELETE repository methods. The API exposes only GET endpoints against it.

4. **Critical changes require individual review.** The `bulk_approve_non_critical()` operation enforces `severity != 'critical'` at the SQL level. This filter is in the repository, not in the API layer, ensuring it cannot be bypassed by API callers.

5. **Every version of every rule is retained permanently.** `country_guide_versions` rows are never deleted. `superseded_at` is set when a new version is created; the row is not removed.

6. **Provenance is recorded atomically with publication.** Provenance insertion and `current_provenance_id` update happen in the same transaction as rule publication. A rule without provenance is a system bug, not an expected state.

---

## Trust Boundary Model

The system defines three trust zones with explicit boundary enforcement:

```
┌────────────────────────────────────────────────────────────────────┐
│  UNTRUSTED ZONE: External Sources                                   │
│                                                                     │
│  Government websites, gazettes, immigration portals                │
│  • Content is treated as adversarial input                         │
│  • HTML is sanitized before processing                             │
│  • LLM extraction does not execute any code                        │
│  • Content is archived verbatim; processing is downstream          │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ Sanitized text only crosses this boundary
┌──────────────────────────────▼─────────────────────────────────────┐
│  AI PROCESSING ZONE: Extraction & Classification                   │
│                                                                     │
│  LLM extraction (Groq LLaMA 3.3 70B, temperature=0.1)             │
│  LLM change classification (Groq LLaMA 3.3 70B, temperature=0.0)   │
│  • AI output is NEVER published directly                           │
│  • Every AI output carries a confidence score                      │
│  • Classification decisions have documented reasoning              │
│  • Extraction failures are explicit, not silent                    │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ Proposed changes only — not published rules
┌──────────────────────────────▼─────────────────────────────────────┐
│  GOVERNANCE ZONE: Human Review & Authorization                     │
│                                                                     │
│  Review queue, approval workflow, escalation                       │
│  • Mandatory human gate for all publication                        │
│  • Reviewer identity and rationale recorded immutably              │
│  • Critical changes require individual review                      │
│  • Audit log is append-only                                        │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ Approved, provenance-linked rules only
┌──────────────────────────────▼─────────────────────────────────────┐
│  AUTHORITATIVE ZONE: Published Rules & History                     │
│                                                                     │
│  country_guide, country_guide_versions, rule_provenance            │
│  • Immutable version history                                       │
│  • Complete provenance chains                                      │
│  • Temporal queries with legal defensibility                       │
│  • Audit log covering all transitions                              │
└────────────────────────────────────────────────────────────────────┘
```

---

## High-Level Architecture

```
                    ┌─────────────────────────────────────────────────────┐
                    │          Official Government Sources                 │
                    │  Ministry of Labor · Immigration Portal · Gazette   │
                    └──────────┬──────────────────────┬───────────────────┘
                               │                      │
                    ┌──────────▼──────────────────────▼───────────────────┐
                    │              INGESTION LAYER                        │
                    │  HTML Fetcher  │  Snapshot Archival  │  Content Hash│
                    │  Ingestion Job State Machine                        │
                    └──────────┬──────────────────────────────────────────┘
                               │  Raw text (sanitized) + MD5 hash
                    ┌──────────▼──────────────────────────────────────────┐
                    │            EXTRACTION LAYER                         │
                    │  Content Chunker → Groq LLM → Pydantic Validator   │
                    │  Multi-key rotation  │  Chunk aggregation           │
                    │  Confidence scoring  │  Extraction failure logging  │
                    └──────────┬──────────────────────────────────────────┘
                               │  EmploymentRule[] with confidence scores
                    ┌──────────▼──────────────────────────────────────────┐
                    │          RECONCILIATION LAYER                       │
                    │  LLM Change Classifier (Groq, temperature=0.0)      │
                    │  Change Type Classification · Materiality Scoring   │
                    │  Duplicate Suppression · Null-change Filtering      │
                    └──────────┬──────────────────────────────────────────┘
                               │  Proposed changes (not yet published)
                    ┌──────────▼──────────────────────────────────────────┐
                    │       GOVERNANCE GATE (Mandatory Human Review)      │
                    │  Review Queue  │  Approve/Reject/Escalate           │
                    │  Provenance Recording  │  Audit Log                 │
                    └──────────┬──────────────────────────────────────────┘
                               │  Approved, provenance-linked rules
              ┌────────────────┼────────────────────────┐
              │                │                        │
    ┌─────────▼────────┐ ┌────▼──────────────┐ ┌───────▼────────────┐
    │  PUBLICATION      │ │  DRIFT DETECTION  │ │  ALERTING          │
    │  Active Guide     │ │  SLA Monitoring   │ │  Region-Routed     │
    │  Version History  │ │  Coverage Gaps    │ │  APAC/EMEA/Americas│
    │  Temporal Queries │ │  Escalation Queue │ │  Post-Sync Summary │
    └──────────────────┘ └───────────────────┘ └────────────────────┘
```

---

## End-to-End Data Flow

```mermaid
flowchart LR
    A[Official Source URL] --> B[HTML Fetcher]
    B --> C[Sanitize & Hash]
    C --> D[source_snapshots]
    D --> E[Content Chunker]
    E --> F[Groq LLM — temperature=0.1]
    F --> G[Pydantic Validator]
    G --> H[Confidence Aggregator]
    H --> I[LLM Change Classifier]
    I --> J{Semantic Change?}
    J -- No change detected --> K[Suppress — no queue item]
    J -- Change detected --> L[review_queue — status=pending]
    L --> M{Reviewer Decision}
    M -- Approve --> N[country_guide UPSERT]
    N --> O[country_guide_versions INSERT]
    N --> P[rule_provenance INSERT]
    N --> Q[audit_log INSERT]
    M -- Reject --> R[audit_log INSERT — no publication]
    M -- Escalate --> S[review_queue status=escalated]
```

---

## Architectural Decisions & Rationale

### Decision 1: LLM-Based Change Classification (Superseded Regex Engine)

**What the decision is:** Change classification calls the LLM (Groq LLaMA 3.3 70B, temperature=0.0) with a fixed rubric and a closed label set, rather than a hand-written regex pattern library. `LLMReconciliationEngine` (`app/reconciliation/llm_reconciliation_service.py`) replaced `SemanticReconciliationEngine` (removed).

**Why the regex engine was replaced:** The pattern library only recognized English compliance keywords (`must`, `shall`, `eligible`, `minimum wage`...) compiled in advance. Any change phrased outside that vocabulary — including any non-English source, or simply unanticipated wording — fell through to a generic low-priority classification regardless of actual materiality. A fixed vocabulary cannot keep pace with new compliance domains or new source languages without a code change and a deploy. The LLM-based classifier generalizes the same way the extraction layer already does.

**How non-determinism is managed, not eliminated:** Classification is not perfectly reproducible the way regex matching was — this is a real tradeoff, not a solved problem. It is mitigated, not removed: `temperature=0.0` minimizes (but does not guarantee zero) run-to-run variance; the prompt encodes the same materiality rubric the regex engine used (high-impact domains, eligibility/visa escalation, requirement-removal asymmetry) so classification stays anchored to a documented standard rather than free-form judgment; every classification's `reasoning` is logged at call time for traceability; and — as before — the classification is advisory. It never gates whether a change reaches the review queue, only how it's prioritized within it. A misclassification is a prioritization error a human reviewer can catch from the before/after diff, not a publication error.

**Acknowledged limitation:** An LLM call can fail to return valid JSON, time out, or hit a rate limit. `LLMReconciliationEngine` retries internally; if classification still fails, `ReconciliationService` logs a warning and enqueues the review item without a materiality/change-type label rather than dropping it — the same fail-open behavior the regex engine used for unmatched patterns. Every detected change still reaches a reviewer.

**Cost and latency tradeoff:** This adds one Groq call per detected change, on top of the existing extraction calls — both classification and extraction now depend on Groq availability and quota, where reconciliation previously had zero LLM dependency. This is a deliberate tradeoff being made explicitly, not a side effect: the previous "no LLM in reconciliation" design existed in part *because* of this cost/availability concern, and the team chose generalization over that isolation.

---

### Decision 2: LLM Scoped to Extraction and Classification Only

**What the decision is:** The LLM (Groq LLaMA 3.3 70B) is used for two pipeline stages: extracting structured rules from source text, and classifying the materiality/type of a detected change (see Decision 1). It is not used for approval decisions or any operation that writes to `country_guide` directly.

**Why this matters for governance:** Both LLM call sites sit strictly upstream of the governance gate. Confidence scores quantify extraction reliability; classification reasoning is logged for every reconciliation call; human reviewers evaluate both before anything is approved. The governance gate ensures LLM output — extracted or classified — never directly modifies authoritative data. If Groq is deprecated, rate-limited, or replaced, it affects extraction and classification only; all historical provenance, version history, and audit records remain valid.

**Widened blast radius, acknowledged:** Decision 1 previously argued for keeping reconciliation LLM-free specifically to bound this risk to one stage. That argument no longer holds: a full Groq outage or rate-limit exhaustion now degrades two pipeline stages instead of one. Both stages fail open (extraction failure halts that source's sync cycle; classification failure enqueues the change unclassified) rather than failing closed, so an outage produces missing or unprioritized review items, not silent data loss or incorrect publication.

---

### Decision 3: Append-Only Audit Infrastructure

**What the decision is:** `audit_log`, `country_guide_versions`, `rule_provenance`, and `source_snapshots` are append-only at the application level. No repository methods, migration scripts, or API endpoints issue UPDATE or DELETE against these tables.

**Why this matters for governance:** Regulators and auditors must be able to trust that the audit record reflects what actually happened, not what the organization wishes had happened. A mutable audit log is not an audit log — it is a liability. Append-only design makes post-hoc modification structurally difficult; it is not just a policy but an architectural constraint.

---

### Decision 4: Governed Source Registry in a Separate Repository

**What the decision is:** Official source URLs and their governance metadata are maintained in a dedicated data repository ([`compliance-data`](https://github.com/guptashivansh/compliance-data)), not in the application database.

**What the registry provides beyond URLs:** Each authority entry carries `trust_level`, `precedence_rank`, `escalation_required`, `supports_replay`, and `owner_team`. This means the registry is not a flat URL list — it is a structured, governed catalogue of the organisation's regulatory intelligence sources. The `escalation_required` flag, for example, causes any change from designated high-sensitivity authorities to automatically enter the review queue as escalated, regardless of the semantic engine's materiality assessment.

**Why this matters for governance:** Source changes are configuration changes with compliance implications. A separate git-tracked repository provides:
- Change history with author attribution for every source addition, URL update, trust level change, or deactivation
- The ability to revert a source set to a prior state independently of application deployments
- A clear ownership model: the `owner_team` field in the registry assigns accountability for each source

**Acknowledged tradeoff:** Updating sources requires a commit to the registry repository rather than a database update. This is an intentional friction point — source changes should be deliberate and traceable, not ad-hoc edits.

---

### Decision 5: PostgreSQL / SQLite Dual Backend

**What the decision is:** The `app/utils/db.py` adapter transparently handles syntax differences between SQLite and PostgreSQL, so the same repository code runs on both backends.

**Why this matters operationally:** SQLite provides zero-ops local development and single-instance deployments with full ACID compliance. The adapter ensures that a move to PostgreSQL for production scale does not require rewriting repository logic. The migration path is `set DATABASE_URL` — no schema changes, no query rewrites.

---

### Decision 6: APScheduler as In-Process Scheduler

**What the decision is:** Automated sync runs are scheduled via APScheduler embedded in the Flask process, not an external job scheduler (Celery, Airflow, Kubernetes CronJob).

**Why this matters operationally:** An in-process scheduler eliminates infrastructure dependencies for single-instance deployments. The acknowledged risk is that a Flask process restart cancels an in-progress sync. This is mitigated by idempotent sync design: each source is processed independently, failed jobs record their state, and the next scheduled run reprocesses failed sources.

**Scale path:** For multi-instance or high-availability deployments, APScheduler should be replaced with an external job scheduler (Celery + Beat, Kubernetes CronJob) with a distributed lock to prevent concurrent runs for the same source.

---

## Failure Handling Framework

The system distinguishes between three categories of failure, each with a different handling strategy:

### Category 1: Recoverable Pipeline Failures

Failures that do not corrupt data and will resolve on the next sync cycle:

| Failure | Detection | Impact | Recovery |
|---------|-----------|--------|----------|
| Source website 5xx / timeout | HTTP response code | No new snapshot; previous published rule unchanged | Automatic retry (max 2); job marked `failed` with reason; next sync re-attempts |
| Groq API rate limit | 429 response | Extraction paused for current key | Automatic key rotation to next configured key; transparent retry |
| Groq API outage | Connection error / all keys exhausted | Extraction fails for affected sources | Job marked `failed`; source snapshot preserved; extraction retried on next sync |
| Scheduler process restart | Process death | In-progress sync cancelled | Next scheduled run starts fresh; idempotent design means no data corruption |

### Category 2: Quality Degradation (Detectable)

Failures that produce data, but data of degraded quality, requiring heightened human review:

| Failure | Detection | Impact | Response |
|---------|-----------|--------|----------|
| Government website restructured | Confidence scores drop significantly | Extractions propose incorrect rules | Low-confidence items are flagged; reviewers examine source paragraph against source URL |
| LLM extracts a hallucinated rule | Confidence score < 0.7; source paragraph doesn't support value | Incorrect change proposed in review queue | Human reviewer rejects; audit log records rejection; next sync re-extracts |
| LLM misclassifies change type or materiality | Wrong change type or materiality assigned | Change may be under-prioritized | Human reviewer sees before/after diff regardless; classification guides but does not gate review |
| LLM classification call fails (rate limit, malformed JSON, outage) | Exception after retry exhaustion in `LLMReconciliationEngine` | Review item enqueued with no materiality/change_type label | `ReconciliationService` catches the failure and enqueues unclassified rather than dropping the change |

### Category 3: Unacceptable Failures (Data Integrity)

These failures represent corruption of the governance record and trigger immediate investigation:

| Failure | Detection | Response |
|---------|-----------|----------|
| Approval recorded without audit log entry | Provenance without corresponding audit_log row | Immediately investigate transaction boundary; do not proceed with further approvals until root cause identified |
| Published rule without provenance | `current_provenance_id IS NULL` on active rule | Flag rule as requiring provenance reconstruction; do not serve to clients without provenance |
| Version history gap | Period with no version covering a date range | Reconstruct from audit log; create corrective version record with appropriate effective dates |

---

## Scalability Strategy

Scalability decisions are made with governance as the primary constraint. Performance optimizations that undermine auditability or compromise the review gate are not acceptable.

| Dimension | Current Approach | Scale Path |
|-----------|-----------------|------------|
| Source coverage | 87 countries × N sources per country | Source registry is additive; no code changes required |
| Sync throughput | Sequential per source endpoint | Worker pool with per-country distributed locking; requires external scheduler |
| LLM throughput | N-key rotation (one key per Groq account), shared quota pool across extraction and classification | Add keys to `GROQ_API_KEYS` comma-separated; rotation is automatic. Classification now competes with extraction for the same quota — see Decision 2 |
| Database concurrency | SQLite (single-writer) | PostgreSQL adapter in `db.py`; `set DATABASE_URL` activates it |
| Audit record volume | ~1 record per review action | Append-only; archive partitions for historical records beyond N years |
| Temporal query performance | `(country, section, effective_date)` composite index | Adequate for 87 countries × 7 sections × N versions; no optimization needed at current scale |

---

## Security Architecture

| Threat | Control |
|--------|---------|
| Groq API key exposure | Environment variables only; multi-key rotation reduces per-key blast radius |
| SQL injection via user input | All database queries use parameterized statements throughout the repository layer |
| Prompt injection via government source content | BeautifulSoup strips executable tags before text enters the LLM context; LLM is instruction-prompted to extract only |
| Audit log tampering | Append-only table design; no UPDATE/DELETE methods in `ProvenanceRepository` or `audit_log` handlers |
| Snapshot content integrity | MD5 hash stored with every snapshot; hash is recorded in provenance chain; hash mismatch detectable |
| Slack webhook secret exposure | Webhook URL in environment variables; never logged or returned by API |
| Unauthorized approval | Review actions are POST-only; GET requests produce no state change; reviewer identity is recorded (SSO enforcement is an integration requirement) |
