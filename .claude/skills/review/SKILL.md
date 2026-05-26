---
name: review
description: >
  View and act on the compliance review queue — approve, reject, escalate, assign, or bulk-approve
  pending rule changes. Use when the user asks to: review changes, approve updates, check the
  review queue, reject a change, escalate an item, bulk approve, or manage pending compliance changes.
---

# Review Queue Skill

Manages the human review workflow for country guide rule changes. Changes are queued by the sync pipeline and require explicit approval before going live. This skill lets users inspect the queue, approve/reject individual items, escalate critical changes, assign reviewers, or bulk-approve non-critical items.

The database backend is determined by `DATABASE_URL` (PostgreSQL) or falls back to SQLite. All queries go through `app.utils.db.Database`.

## Steps to follow

### 1. Show the pending review queue

```bash
python3 -c "
import sys, os, json
sys.path.insert(0, os.getcwd())
from app import build_services
services = build_services()
services['country_guide_repository'].initialize_schema()
items = services['review_service'].list_pending_review_items()
if not items:
    print('Review queue is empty — no pending changes.')
else:
    print(f'{len(items)} pending item(s):\n')
    for item in items:
        sev = (item.get('severity') or 'minor').upper()
        conf = round((item.get('confidence') or 0) * 100)
        status = item.get('status', 'pending').upper()
        print(f'  [{item[\"id\"]}] {status} | {item[\"country\"]} / {item[\"section\"]} | severity={sev} confidence={conf}%')
        print(f'       Old: {(item.get(\"old_value\") or \"(none)\")[:80]}')
        print(f'       New: {(item.get(\"new_value\") or \"(none)\")[:80]}')
        print()
"
```

If the queue is empty, tell the user and stop.

### 2. Ask what action to take

Present the items and ask:

> "What would you like to do?
> - **Approve** item(s) — specify item ID(s)
> - **Reject** item(s) — specify item ID(s)
> - **Escalate** item(s) — flag for senior compliance review
> - **Assign** an item to a reviewer
> - **Bulk approve** all non-critical items for a specific country
> - **View details** of a specific item"

Wait for the user's answer.

### 3. Execute the chosen action

**Approve a single item:**
```bash
python3 -c "
import sys, os
sys.path.insert(0, os.getcwd())
from app import build_services
services = build_services()
services['country_guide_repository'].initialize_schema()
services['provenance_repository'].initialize_schema()
result = services['review_service'].approve_review_item(
    item_id=ITEM_ID,
    comment='COMMENT',
    assignee='ASSIGNEE_NAME',
    rationale='RATIONALE',
)
if result:
    print(f'Approved: {result[\"country\"]} / {result[\"section\"]}')
    print(f'New value now live: {result[\"new_value\"][:100]}')
    print(f'Version: {result.get(\"version_number\")}, effective: {result.get(\"effective_date\")}')
else:
    print('Item not found or already reviewed.')
"
```

Replace `ITEM_ID`, `COMMENT`, `ASSIGNEE_NAME`, and `RATIONALE` with user-provided values. Ask for a comment and rationale if the user didn't provide them.

**Reject a single item:**
```bash
python3 -c "
import sys, os
sys.path.insert(0, os.getcwd())
from app import build_services
services = build_services()
services['country_guide_repository'].initialize_schema()
result = services['review_service'].reject_review_item(
    item_id=ITEM_ID,
    comment='COMMENT',
    assignee='ASSIGNEE_NAME',
    rationale='RATIONALE',
)
if result:
    print(f'Rejected: {result[\"country\"]} / {result[\"section\"]}')
else:
    print('Item not found or already reviewed.')
"
```

**Escalate an item:**
```bash
python3 -c "
import sys, os
sys.path.insert(0, os.getcwd())
from app import build_services
services = build_services()
services['country_guide_repository'].initialize_schema()
result = services['review_service'].escalate_review_item(
    item_id=ITEM_ID,
    comment='COMMENT',
    assignee='ASSIGNEE_NAME',
    rationale='RATIONALE',
)
if result:
    print(f'Escalated: {result[\"country\"]} / {result[\"section\"]} — status: {result[\"status\"]}')
else:
    print('Item not found or already reviewed.')
"
```

**Bulk approve non-critical items for a country:**
```bash
python3 -c "
import sys, os
sys.path.insert(0, os.getcwd())
from app import build_services
services = build_services()
services['country_guide_repository'].initialize_schema()
services['provenance_repository'].initialize_schema()
result = services['review_service'].bulk_approve_non_critical(
    country='COUNTRY_NAME',
    comment='Bulk approved via CLI review',
    rationale='Non-critical changes verified',
)
print(f'Bulk approved {result[\"approved\"]} item(s) for COUNTRY_NAME')
"
```

**Assign an item:**
```bash
python3 -c "
import sys, os
sys.path.insert(0, os.getcwd())
from app import build_services
services = build_services()
services['country_guide_repository'].initialize_schema()
result = services['review_service'].assign_review_item(
    item_id=ITEM_ID,
    comment='COMMENT',
    assignee='ASSIGNEE_NAME',
)
if result:
    print(f'Assigned: {result[\"country\"]} / {result[\"section\"]} to ASSIGNEE_NAME')
else:
    print('Item not found or already reviewed.')
"
```

### 4. Show updated state

After any action, re-query the queue to confirm the change took effect and show remaining items:

```bash
python3 -c "
import sys, os
sys.path.insert(0, os.getcwd())
from app import build_services
services = build_services()
services['country_guide_repository'].initialize_schema()
items = services['review_service'].list_pending_review_items()
print(f'{len(items)} item(s) remaining in review queue.')
"
```

### 5. Offer next actions

After completing the review action, offer:
- Review more items (loop back to step 2)
- View the audit trail (suggest the **rule-history** skill)
- Run a drift check (suggest the **drift-check** skill)
