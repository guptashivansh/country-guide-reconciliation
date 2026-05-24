# API Reference

All API endpoints return JSON unless otherwise noted.

## Country Guide

### `GET /api/guide`

List all country guide rules.

**Response:**
```json
[
  {
    "country": "India",
    "section": "annual_leave",
    "value": "...",
    "last_updated": "2025-01-15T10:30:00"
  }
]
```

### `GET /api/guide/<country>`

Get all rules for a specific country.

### `GET /api/guide/<country>/<section>/at?date=YYYY-MM-DD`

Temporal query — retrieve the rule that was active at a specific point in time.

**Query Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `date` | string | ISO date (YYYY-MM-DD) |

## Review Queue

### `GET /api/review/queue`

List all pending review items.

**Query Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `status` | string | Filter by status: `pending`, `approved`, `rejected` |
| `country` | string | Filter by country |

### `POST /api/review/<id>/approve`

Approve a review item and publish the change.

**Body:**
```json
{
  "comment": "Verified against official gazette",
  "rationale": "Rate updated per 2025 budget announcement"
}
```

### `POST /api/review/<id>/reject`

Reject a review item.

**Body:**
```json
{
  "comment": "Source appears outdated",
  "rationale": "Newer gazette contradicts this change"
}
```

### `POST /api/review/bulk-approve`

Bulk-approve multiple review items.

**Body:**
```json
{
  "ids": [1, 2, 3],
  "comment": "Batch approval of informational changes"
}
```

### `GET /api/review/audit-log`

Retrieve the immutable audit log of all review decisions.

## Sync

### `POST /api/sync`

Trigger a sync pipeline run.

**Body:**
```json
{
  "countries": ["India", "Australia"]
}
```

## Pages

| Route | Description |
|-------|-------------|
| `/` | Home page |
| `/ops` | Ops dashboard |
| `/guide` | Country guide list |
| `/guide/<country>` | Country detail page |
