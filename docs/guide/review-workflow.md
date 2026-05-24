# Review Workflow

The review workflow ensures every compliance change is verified by a human before publication.

## Workflow Steps

```
Pipeline detects change → Review item created → Reviewer examines diff → Approve / Reject → Audit log entry
```

### 1. Change Detection

When the sync pipeline finds a difference between extracted rules and the live guide, it creates a review queue item with:

- The old and new rule text
- A semantic diff with word-level highlighting
- The change type (Added, Modified, Clarification, Deprecated, Removed)
- A materiality assessment (Critical, Moderate, Low, Informational)
- The extraction confidence score
- The source URL and relevant excerpt

### 2. Review

![Review Queue](../assets/screenshots/review_queue.png)

Reviewers access pending items through the ops dashboard. Each item shows a before/after comparison with changes highlighted semantically — not just character-level diffs, but meaning-aware classifications.

### 3. Decision

- **Approve** — The change is published to the live guide, recorded in the version history, and logged in the audit trail
- **Reject** — The change is dismissed with a reason, also logged for audit

### 4. Audit Trail

Every decision is immutably recorded with:

- Reviewer identity
- Timestamp
- Decision (approve/reject)
- Rationale
- Source provenance metadata

This enables compliance teams to answer "who approved this rule, when, and based on what evidence?" at any point in the future.
