# Compliance Drift Detection

## Operational Purpose

Compliance drift is the condition in which the system's governance posture has degraded below an acceptable threshold — where review items have aged beyond their SLA, escalations have stalled, or published rules have not been re-verified against their official sources for an unacceptable period.

The drift detection system continuously evaluates these conditions and produces per-country severity assessments. It does not resolve drift — that is a human responsibility. It makes drift visible, quantified, and actionable.

The drift detector is a monitoring control, not a remediation mechanism. Its output is always a finding with recommended human action, never an automated correction.

---

## Compliance Posture Model

The system models compliance posture across three dimensions:

**Review Queue Health** — Are pending changes being reviewed within acceptable SLAs?

A review queue that is growing without resolution is not a backlog — it is a governance gap. Changes that are detected but not reviewed are effectively invisible to clients and advisors, which is worse than no detection at all because the organization is aware of the gap and has not acted.

**Escalation Resolution Health** — Are escalated items being resolved?

An escalated item represents a change that a reviewer considered too significant or ambiguous to approve alone. If escalated items sit unresolved, they indicate either a decision bottleneck, a shortage of senior reviewer capacity, or a genuinely ambiguous regulatory situation that requires external input. In all cases, the risk is real and quantifiable.

**Coverage Completeness** — Are all monitored regulatory sections covered by published rules?

A section appearing in the review queue but having no corresponding published rule in `country_guide` indicates a coverage gap: the system is detecting regulatory content for a category that has never been formally published. This gap may expose the organization to liability for a jurisdiction it nominally covers.

---

## SLA Framework

The following SLAs define acceptable review latency by severity. These thresholds are configurable constants in `app/drift/rules.py` and should be calibrated to the organization's regulatory risk appetite and reviewer capacity.

### Review Queue SLAs

| Condition | Severity | Operational Meaning |
|-----------|----------|---------------------|
| Critical item pending > 14 days | CRITICAL | A high-impact regulatory change has been unreviewed for two full weeks. Immediate escalation to compliance leadership. |
| Critical item pending > 7 days | WARNING | A high-impact change is approaching the CRITICAL threshold. Reviewer assignment required within 24 hours. |
| Major item pending > 14 days | WARNING | Moderate-impact change has exceeded reasonable review time. Schedule reviewer attention. |
| Any item pending > 7 days | INFO | General queue aging. Review workload may need rebalancing. |

### Escalation Resolution SLAs

| Condition | Severity | Operational Meaning |
|-----------|----------|---------------------|
| Escalated item unresolved > 7 days | CRITICAL | Escalation has been sitting without resolution for a week. The senior reviewer or compliance lead must act. This item will block the country's drift clearance until resolved. |
| Any escalated item (< 7 days) | WARNING | Escalation requires tracking. Assign a resolution owner and target date. |

### Coverage Gap

| Condition | Severity | Operational Meaning |
|-----------|----------|---------------------|
| Review queue section has no published rule | WARNING | Detected regulatory content exists for a category that has no authoritative published rule. The organization is operating without published guidance for this area. |

---

## Drift Record Structure

Each drift finding produces a `DriftRecord` with the following fields:

```python
@dataclass
class DriftRecord:
    country: str
    section: str
    drift_type: str        # "pending_review_aging" | "escalation_bottleneck" | "coverage_gap"
    severity: str          # "CRITICAL" | "WARNING" | "INFO"
    current_value: Optional[str]   # The currently published rule (if any)
    proposed_value: Optional[str]  # The proposed change awaiting review (if any)
    pending_item_id: Optional[int]
    days_pending: Optional[int]    # How long the item has been in the queue
    last_verified_at: Optional[str]
    evidence: str          # Human-readable explanation of why this drift was detected
    recommended_action: str  # Specific action for the compliance team
```

The `recommended_action` field is operationally significant — it is not a generic suggestion but a specific action derived from the drift type and severity:

| Drift Type | CRITICAL Action | WARNING Action |
|------------|-----------------|----------------|
| `pending_review_aging` | "Review critical pending item for [section] immediately — [N] days overdue" | "Schedule review for major pending item for [section]" |
| `escalation_bottleneck` | "Resolve escalated [section] item — unresolved for [N] days" | "Assign resolution owner for escalated [section] item" |
| `coverage_gap` | N/A (only WARNING) | "Publish a rule for [section] — detected content has no published guide entry" |

---

## Drift Report Aggregation

The `DriftReport` for a country aggregates all `DriftRecord` findings:

```python
@dataclass
class DriftReport:
    country: str
    generated_at: str           # ISO timestamp of report generation
    drift_detected: bool
    severity: str               # Maximum severity across all records
    affected_sections: list[str]
    summary: str                # E.g., "2 CRITICAL, 1 WARNING drift items for India"
    recommended_action: str     # Highest-priority recommended action
```

**Severity aggregation is conservative:** The report's overall severity is the maximum across all individual records. A country with one CRITICAL and five INFO findings is a CRITICAL country. This conservatism is intentional — a single unresolved critical item represents real compliance risk regardless of how many low-severity findings exist.

**Deduplication:** If multiple drift rules fire for the same `(section, drift_type)` pair — for example, both the 7-day and 14-day pending thresholds fire for the same item — only the highest-severity record is retained. The compliance team receives one clear signal per section, not duplicate findings.

---

## Read-Only Architecture

The drift detector has no write path. It reads from `country_guide`, `review_queue`, and `rule_provenance` but never inserts, updates, or deletes records. This is a deliberate architectural constraint with two implications:

**Drift is always computed on current state.** There is no cached drift result that could become stale. Every call to `/api/drift` computes drift fresh from the current database state. A reviewer who resolves a critical pending item will see the CRITICAL finding disappear on the next drift API call.

**Drift computation cannot corrupt governance data.** A buggy drift rule cannot accidentally modify the review queue or country guide. The worst-case outcome of a drift computation bug is an incorrect finding — a finding that is visible to reviewers and inspectable.

---

## Integration with Alerting

Post-sync Slack notifications include aggregate drift status. If any country has a CRITICAL drift finding at the time of the sync, the alert includes the country name, affected sections, and recommended action.

This ensures that drift does not accumulate silently between dashboard sessions. Regional owners receive proactive notification when their countries' compliance posture degrades.

---

## Operational Procedures

### Daily Drift Review (Recommended)

1. Call `GET /api/drift` or open the Drift tab in the ops dashboard.
2. For each CRITICAL finding: assign a named reviewer with a resolution deadline.
3. For each WARNING finding: assess whether it is tracking toward CRITICAL and schedule action.
4. For coverage gaps: determine whether the missing section is an active monitoring gap or a deliberate exclusion.

### Drift Clearance

A CRITICAL drift finding clears when the underlying condition resolves:
- `pending_review_aging` clears when the pending item is approved, rejected, or escalated
- `escalation_bottleneck` clears when the escalated item is approved or rejected
- `coverage_gap` clears when a rule for the affected section is published in `country_guide`

The drift report does not require manual acknowledgment. Resolution of the underlying condition is the only clearance mechanism.

### Threshold Calibration

The drift thresholds in `app/drift/rules.py` are operational parameters, not fixed constants. They should be reviewed periodically and calibrated based on:

- Actual reviewer capacity (if reviewers consistently clear items in 5 days, a 14-day CRITICAL threshold is too lenient)
- Regulatory risk profile (high-risk jurisdictions warrant tighter thresholds)
- Organizational SLA commitments to clients (if the organization has committed to 48-hour update publication, thresholds must reflect that)

Threshold changes should be documented, reviewed by compliance leadership, and tracked in the source control history of `rules.py`.

---

## Backend Components

| Component | File | Lines | Responsibility |
|-----------|------|-------|----------------|
| `DriftDetector` | `app/drift/detector.py` | 110 | Orchestrates rule evaluation, deduplication, report generation |
| `DriftRepository` | `app/drift/repository.py` | 150 | Read-only queries across guide, queue, and provenance tables |
| `DriftRecord` | `app/drift/report.py` | — | Individual drift finding with evidence and recommended action |
| `DriftReport` | `app/drift/report.py` | — | Country-level aggregated report |
| Drift rules | `app/drift/rules.py` | 150+ | Predicate functions implementing SLA thresholds |

---

## API Surface

| Endpoint | Response |
|----------|---------|
| `GET /api/drift` | `DriftReport[]` for all countries — only countries with drift findings are returned |
| `GET /api/drift/<country>` | Single `DriftReport` for the specified country |

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Thresholds too aggressive — noisy alerts | Thresholds are tunable; calibrate based on actual reviewer cadence and organizational risk appetite |
| Thresholds too lenient — drift undetected | Default CRITICAL thresholds (14 days pending, 7 days escalated) reflect a conservative baseline; review during deployment |
| Coverage gap for deliberately excluded section | The coverage gap rule fires for any section in the review queue without a published rule; intentionally excluded sections should either not be monitored at source level or have a placeholder rule in `country_guide` |
| Drift report is stale between checks | Drift is computed on-demand; there is no cache to become stale |
| Drift computation fails (database error) | API returns error; no partial drift data is surfaced; previous state of the dashboard is unaffected |
