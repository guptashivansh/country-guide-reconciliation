---
name: rule-history
description: >
  View the version history, provenance chain, or point-in-time value of a country guide rule.
  Use when the user asks to: view rule history, check provenance, see who changed a rule,
  get the rule as of a date, view the audit trail, or trace a rule's lineage.
---

# Rule History Skill

Provides three views into a rule's lifecycle:
1. **Version timeline** — all versions of a rule with effective dates and who approved them
2. **Provenance chain** — full lineage from source crawl → extraction → review → publication
3. **Point-in-time query** — what was the rule on a specific date?

## Steps to follow

### 1. Ask what to look up

If the user hasn't specified, ask:

> "What would you like to look up?
> - **Country** — e.g., India
> - **Section** — e.g., annual_leave, working_hours, minimum_wage
> - **View** — version history, provenance chain, or value at a specific date?"

Wait for the user's answer.

### 2a. Version history

```bash
python3 -c "
import sys, os
sys.path.insert(0, os.getcwd())
from app import build_services
services = build_services()
services['country_guide_repository'].initialize_schema()
services['provenance_repository'].initialize_schema()
temporal = services['temporal_rule_service']
timeline = temporal.build_timeline('COUNTRY', 'SECTION')
current = timeline.get('current')
if current:
    print(f'Current (v{current.get(\"version_number\", \"?\")}):')
    print(f'  Value: {current[\"value\"][:120]}')
    print(f'  Effective: {current.get(\"effective_date\", \"?\")}')
    print(f'  Approval: {current.get(\"approval_reference\", \"?\")}')
print(f'\nVersion history ({len(timeline.get(\"history\", []))} version(s)):')
for v in timeline.get('history', []):
    sup = f' (superseded {v[\"superseded_at\"][:10]})' if v.get('superseded_at') else ' (current)'
    print(f'  v{v[\"version_number\"]}: effective {v.get(\"effective_date\", \"?\")}{sup}')
    print(f'    {v[\"value\"][:100]}')
    print(f'    Ref: {v.get(\"approval_reference\", \"?\")}')
"
```

### 2b. Provenance chain

```bash
python3 -c "
import sys, os
sys.path.insert(0, os.getcwd())
from app import build_services
services = build_services()
services['country_guide_repository'].initialize_schema()
services['provenance_repository'].initialize_schema()
chain = services['provenance_service'].get_chain('COUNTRY', 'SECTION')
if not chain:
    print('No provenance record found for this rule.')
else:
    c = chain['chain']
    print(f'Provenance for {chain[\"country\"]} / {chain[\"section\"]}:')
    print(f'  Rule value: {c[\"canonical_rule\"][\"value\"][:100]}')
    print(f'  Last updated: {c[\"canonical_rule\"].get(\"last_updated\", \"?\")}')
    r = c.get('reviewer_action', {})
    print(f'  Reviewer: {r.get(\"action\", \"?\")} by {r.get(\"assignee\", \"?\")} at {r.get(\"reviewed_at\", \"?\")}')
    print(f'  Rationale: {r.get(\"rationale\", \"(none)\")}')
    e = c.get('extraction', {})
    print(f'  Extraction: confidence={e.get(\"confidence\", \"?\")} parser={e.get(\"parser_version\", \"?\")}')
    snap = c.get('source_snapshot')
    if snap:
        print(f'  Snapshot: id={snap[\"snapshot_id\"]} hash={snap.get(\"content_hash\", \"?\")[:12]} captured={snap.get(\"captured_at\", \"?\")}')
    crawl = c.get('crawl_event')
    if crawl:
        print(f'  Crawl: job={crawl[\"ingestion_job_id\"]} state={crawl.get(\"state\", \"?\")} fetched={crawl.get(\"fetched_at\", \"?\")}')
    print(f'  Source: {c.get(\"source_url\", \"?\")}')

history = services['provenance_service'].get_history('COUNTRY', 'SECTION')
if history and len(history) > 1:
    print(f'\n  Provenance history ({len(history)} record(s)):')
    for h in history:
        print(f'    [{h[\"provenance_id\"]}] {h[\"reviewer_action\"]} by {h.get(\"reviewer_assignee\", \"?\")} at {h.get(\"created_at\", \"?\")[:16]}')
"
```

### 2c. Value at a specific date

```bash
python3 -c "
import sys, os
sys.path.insert(0, os.getcwd())
from app import build_services
services = build_services()
services['country_guide_repository'].initialize_schema()
temporal = services['temporal_rule_service']
rule = temporal.get_rule_at_date('COUNTRY', 'SECTION', 'YYYY-MM-DD')
if rule:
    print(f'Value of COUNTRY / SECTION as of YYYY-MM-DD:')
    print(f'  v{rule[\"version_number\"]}: {rule[\"value\"]}')
    print(f'  Effective from: {rule.get(\"effective_date\", \"?\")}')
    print(f'  Source: {rule.get(\"source_url\", \"?\")}')
else:
    print('No version found for that date — the rule may not have existed yet.')
"
```

Replace `COUNTRY`, `SECTION`, and `YYYY-MM-DD` with user-provided values.

### 3. Present results

Format the output clearly. For version history, show a timeline. For provenance, show the chain from source to publication. For point-in-time queries, show the value and its context.
