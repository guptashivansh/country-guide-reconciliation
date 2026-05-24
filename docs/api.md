# API Reference

All API endpoints return JSON. Page routes return rendered HTML templates.

---

## Country Guide

### `GET /api/guide`

List all active country guide rules.

**Response** `200`:
```json
[
    {
        "country": "India",
        "section": "annual_leave",
        "value": "12 days per year",
        "source_url": "https://labour.gov.in/...",
        "last_updated": "2025-04-01T00:00:00"
    }
]
```

### `GET /api/guide/<country>/<section>/at`

Temporal query — retrieve the rule that was effective at a specific point in time.

**Query Parameters**:

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `date` | string | Yes | ISO date (YYYY-MM-DD) |

**Example**: `GET /api/guide/India/minimum_wage/at?date=2024-09-15`

**Response** `200`:
```json
{
    "country": "India",
    "section": "minimum_wage",
    "value": "INR 21,000/month",
    "effective_date": "2024-07-01",
    "superseded_at": "2025-04-01",
    "version_number": 2
}
```

### `GET /api/guide/<country>/<section>/history`

Full version timeline for a rule.

**Response** `200`:
```json
{
    "current": { "value": "...", "effective_date": "...", "version_number": 3 },
    "versions": [
        { "value": "...", "effective_date": "...", "superseded_at": "...", "version_number": 1 },
        { "value": "...", "effective_date": "...", "superseded_at": "...", "version_number": 2 },
        { "value": "...", "effective_date": "...", "superseded_at": null, "version_number": 3 }
    ]
}
```

---

## Review Queue

### `GET /api/queue`

List pending review items, ordered by priority (escalated first, then severity, then confidence).

**Response** `200`:
```json
[
    {
        "id": 42,
        "country": "India",
        "section": "minimum_wage",
        "old_value": "INR 21,000/month",
        "new_value": "INR 23,500/month",
        "severity": "critical",
        "confidence": 0.92,
        "source_url": "https://labour.gov.in/...",
        "source_paragraph": "The minimum wage for scheduled employment...",
        "status": "pending",
        "materiality_level": "CRITICAL",
        "change_type": "NUMERIC_THRESHOLD_CHANGE",
        "created_at": "2025-03-14T08:01:30"
    }
]
```

### `POST /api/approve/<id>`

Approve a review item and publish the change.

**Request Body**:
```json
{
    "comment": "Verified against official gazette",
    "assignee": "divya@compliance.team",
    "rationale": "Rate updated per 2025 budget announcement",
    "effective_date": "2025-04-01"
}
```

**Response** `200`:
```json
{ "status": "approved", "id": 42 }
```

### `POST /api/reject/<id>`

Reject a review item.

**Request Body**:
```json
{
    "comment": "Source appears outdated",
    "rationale": "Newer gazette contradicts this change"
}
```

### `POST /api/escalate/<id>`

Escalate a review item to senior compliance. The item's status changes to `"escalated"` and surfaces first in the queue.

### `POST /api/assign/<id>`

Assign a review item to a specific reviewer.

**Request Body**:
```json
{
    "assignee": "shweta@compliance.team",
    "comment": "Routing to EMEA lead for UAE-specific review"
}
```

### `POST /api/bulk-approve`

Approve all non-critical pending items for a country.

**Request Body**:
```json
{
    "country": "India",
    "comment": "Batch approval of informational changes",
    "rationale": "Low-risk formatting updates verified in bulk",
    "effective_date": "2025-04-01"
}
```

**Guard rails**: Only items where `severity != 'critical'` are included. Each item gets its own audit log entry.

---

## Audit Log

### `GET /api/audit`

Retrieve the immutable audit log of all review decisions.

**Query Parameters**:

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `country` | string | No | Filter by country |
| `since` | string | No | ISO date — only entries after this date |

**Response** `200`:
```json
[
    {
        "id": 101,
        "action": "review",
        "country": "India",
        "section": "minimum_wage",
        "decision": "approved",
        "old_value": "INR 21,000/month",
        "new_value": "INR 23,500/month",
        "reviewer_comment": "Confirmed in gazette",
        "reviewer_assignee": "divya@compliance.team",
        "reviewer_rationale": "Budget 2025 rate update",
        "timestamp": "2025-03-15T14:30:00"
    }
]
```

---

## Provenance

### `GET /api/provenance/<country>`

All current provenance chains for a country.

### `GET /api/provenance/<country>/<section>`

Single provenance chain for a rule, with nested source snapshot and crawl event data.

### `GET /api/provenance/<country>/<section>/history`

Full provenance history (all historical provenance records for the rule).

---

## Drift Detection

### `GET /api/drift`

All drift reports across all monitored countries.

### `GET /api/drift/<country>`

Drift report for a specific country.

**Response** `200`:
```json
{
    "country": "India",
    "generated_at": "2025-05-24T10:00:00",
    "drift_detected": true,
    "severity": "CRITICAL",
    "affected_sections": ["minimum_wage", "annual_leave"],
    "summary": "1 CRITICAL, 1 WARNING drift items for India",
    "recommended_action": "Review critical pending items immediately"
}
```

---

## Pipeline Operations

### `POST /api/sync`

Trigger a sync pipeline run.

**Request Body**:
```json
{
    "countries": ["India", "Australia"]
}
```

Omit `countries` to sync all monitored countries.

**Response** `200`:
```json
{
    "total_changes": 12,
    "endpoints_processed": 24,
    "failures": 2,
    "per_country": {
        "India": { "changes": 5, "failures": 0 },
        "Singapore": { "changes": 3, "failures": 1 }
    }
}
```

### `GET /api/ingestion-jobs`

List recent ingestion jobs (default: last 25).

**Response** `200`:
```json
[
    {
        "id": 89,
        "source_url": "https://labour.gov.in/...",
        "state": "reconciled",
        "queued_at": "2025-03-14T07:59:00",
        "fetched_at": "2025-03-14T08:00:02",
        "extracted_at": "2025-03-14T08:00:45",
        "reconciled_at": "2025-03-14T08:01:30",
        "failed_at": null,
        "failure_reason": null
    }
]
```

### `GET /api/metrics`

Dashboard KPI metrics.

**Response** `200`:
```json
{
    "pending_reviews": 12,
    "critical_changes": 3,
    "avg_confidence": 0.87,
    "failures_last_sync": 1,
    "countries_active": 8,
    "total_sources": 24
}
```

---

## PDF Intake

### `POST /api/intake/pdf`

Upload a PDF document for extraction.

**Content-Type**: `multipart/form-data`

| Field | Type | Description |
|-------|------|-------------|
| `file` | file | PDF document |
| `country` | string | Target country |

---

## Page Routes

| Route | Template | Description |
|-------|----------|-------------|
| `GET /` | `home.html` | Workspace selector with country grid |
| `GET /ops` | `ops_dashboard_v2.html` | Compliance operations dashboard |
| `GET /guide` | `guide_list.html` | Country card grid with rule counts |
| `GET /guide/<country>` | `guide_country.html` | Full employment guide for a country |
| `GET /compliance/intake` | `compliance_intake.html` | Compliance intake form |
