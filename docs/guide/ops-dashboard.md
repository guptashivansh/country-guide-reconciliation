# Ops Dashboard

The ops dashboard (`/ops`) is the primary interface for compliance operations.

![Ops Dashboard](../assets/screenshots/ops_dashboard.png)

## Metrics Cards

The top row displays 7 real-time metrics:

- **Monitored Sources** — Total official sources being tracked
- **Pending Reviews** — Changes awaiting reviewer decision
- **Critical Changes** — High-materiality changes requiring urgent attention
- **Approved Today** — Changes approved in the current session
- **Countries Active** — Countries with at least one published rule
- **Drift Alerts** — Unexpected rule changes detected
- **Last Sync** — Timestamp of the most recent pipeline run

## Review Queue

![Review Queue Detail](../assets/screenshots/review_queue.png)

The review queue shows all pending changes with:

- **Severity badges** — Color-coded by materiality (Critical, Moderate, Low, Informational)
- **Change type** — Added, Modified, Clarification, Deprecated, Removed
- **Semantic diffs** — Word-level before/after highlighting
- **Source excerpts** — Relevant passage from the official source
- **Confidence score** — LLM extraction confidence

### Actions

- **Approve** — Publish the change to the live guide
- **Reject** — Dismiss the change with a reason
- **Bulk Approve** — Approve multiple low-risk changes at once

## Sync Controls

Click **Sync Now** to trigger a pipeline run. A modal lets you select specific countries to sync (to conserve Groq API quota).

## Audit Log

The audit log tab shows an immutable record of every approval and rejection, including reviewer identity, timestamp, and decision rationale.
