---
name: edit-rule
description: >
  Directly edit a live country guide rule, bypassing the review queue. Creates a versioned update
  with full audit trail. Use when the user asks to: edit a rule, update a country value, change
  a guide entry, fix a rule manually, or correct a compliance value.
---

# Edit Rule Skill

Directly modifies a live country guide rule without going through the review queue. The change is versioned, audit-logged, and attributed to a manual edit. Use this for corrections, manual updates from known-good sources, or when the review queue workflow is unnecessary.

## Steps to follow

### 1. Show available countries and sections

```bash
python3 -c "
import sys, os
sys.path.insert(0, os.getcwd())
from app import build_services
services = build_services()
services['country_guide_repository'].initialize_schema()
entries = services['review_service'].list_country_guide_entries()
by_country = {}
for e in entries:
    by_country.setdefault(e['country'], []).append(e)
for country in sorted(by_country):
    sections = [e['section'] for e in by_country[country]]
    print(f'{country}: {", ".join(sorted(sections))}')
"
```

### 2. Ask what to edit

If the user hasn't already specified, ask:

> "Which rule do you want to edit?
> - **Country** — e.g., India
> - **Section** — e.g., annual_leave, working_hours, minimum_wage
> - **New value** — the corrected text"

Wait for the user's answer.

### 3. Show current value and confirm

```bash
python3 -c "
import sys, os
sys.path.insert(0, os.getcwd())
from app import build_services
services = build_services()
services['country_guide_repository'].initialize_schema()
repo = services['country_guide_repository']
current = repo.get_current_value('COUNTRY', 'SECTION')
print(f'Current value for COUNTRY / SECTION:')
print(f'  {current}')
"
```

Show the current value and the proposed new value side by side. Ask:

> "Confirm this change?
> - **Country**: COUNTRY
> - **Section**: SECTION
> - **Current**: [current value]
> - **New**: [new value]"

Wait for explicit confirmation.

### 4. Apply the edit

```bash
python3 -c "
import sys, os
sys.path.insert(0, os.getcwd())
from app import build_services
services = build_services()
services['country_guide_repository'].initialize_schema()
services['provenance_repository'].initialize_schema()
result = services['review_service'].manual_edit_rule('COUNTRY', 'SECTION', '''NEW_VALUE''')
if result:
    print(f'Updated: {result[\"country\"]} / {result[\"section\"]}')
    print(f'Old value: {result[\"old_value\"]}')
    print(f'New value: {result[\"new_value\"]}')
    print(f'Timestamp: {result[\"updated_at\"]}')
else:
    print('No change — the new value is identical to the current value.')
"
```

Replace `COUNTRY`, `SECTION`, and `NEW_VALUE` with user-provided values. Use triple-quoted strings for multi-line values.

### 5. Confirm the update

Tell the user the edit was applied with an audit trail entry. The change is immediately live in the guide — no review queue approval needed.
