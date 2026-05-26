---
name: notion-import
description: >
  Imports Skuad country employment guides from Notion into the country_guide database (SQLite or PostgreSQL).
  Use this skill whenever the user asks to: import from Notion, seed the database from Notion,
  run the Notion importer, update the existing state from Notion, or sync country guides from
  the Skuad Notion page. Always use this skill — don't just run the script manually.
---

# Notion Import Skill

This skill runs `notion_import.py` to seed the `country_guide` table with Skuad's internal country employment guides fetched from Notion. The Notion page is the source of truth for existing state; this import gives the reconciliation pipeline a baseline to compare against official government sources.

The database backend is determined by the `DATABASE_URL` environment variable. When set to a PostgreSQL connection string (e.g. `postgresql://user:pass@host/db`), the skill uses Postgres; otherwise it falls back to SQLite. All inline queries in this skill use `app.utils.db.Database` so they work with either backend.

## Steps to follow

### 1. Verify environment

Check that the working directory contains `notion_import.py` and that `.env` has `GROQ_API_KEY` set:

```bash
ls notion_import.py 2>/dev/null && echo "found" || echo "not found"
grep -q GROQ_API_KEY .env 2>/dev/null && echo "key present" || echo "missing key"
```

If `notion_import.py` is missing, tell the user the script wasn't found and stop.
If `GROQ_API_KEY` is missing, tell the user to add it to `.env` and stop.

### 2. Show existing state and ask which countries to import

Query the database to show what's already there, then ask the user what they want to do.
The project uses `app.utils.db.Database` which auto-selects PostgreSQL (when `DATABASE_URL` is set) or SQLite (fallback). Always use it instead of raw `sqlite3`:

```bash
python3 -c "
import sys, os
sys.path.insert(0, os.getcwd())
from app.utils.db import Database
try:
    db = Database()
    conn = db.connect()
    cur = conn.execute('SELECT country, COUNT(*) as n, MAX(last_updated) as updated FROM country_guide GROUP BY country ORDER BY country')
    rows = cur.fetchall()
    if rows:
        print('Countries already in DB:')
        for row in rows:
            country, n, updated = row[0], row[1], row[2]
            print(f'  {country}: {n} rule(s), last updated {str(updated)[:10] if updated else \"unknown\"}')
    else:
        print('DB is empty — no countries imported yet.')
    conn.close()
except Exception as e:
    print(f'Could not read DB: {e}')
"
```

The supported countries in `notion_import.py` are:
- India, Australia, Singapore, South Africa, UAE, New Zealand, Philippines, Pakistan

After showing the current DB state, ask the user:

> "Which countries do you want to import from Notion?
> - **All 8** (India, Australia, Singapore, South Africa, UAE, New Zealand, Philippines, Pakistan)
> - **Only missing ones** (countries not yet in the DB)
> - **Specific countries** — which ones?
> - **Refresh existing** (re-import all, overwriting current data)"

Wait for the user's answer before proceeding.

### 3. Update notion_import.py for the selected countries

Based on the user's choice, edit the `COUNTRY_NAMES` list in `notion_import.py` to include only the selected countries. This avoids fetching all 90 Notion candidates when only a subset is needed — each extra country adds ~1–2 minutes.

For example, if the user only wants India and Australia:
```python
COUNTRY_NAMES = ["India", "Australia"]
```

If the user wants all 8, keep the full list as-is. If UAE was previously missing, also add `"United Arab Emirates"` alongside `"UAE"` since the Notion page may use the full name:
```python
COUNTRY_NAMES = ["India", "Australia", "Singapore", "South Africa", "UAE", "United Arab Emirates", "New Zealand", "Philippines", "Pakistan"]
```

Show the user what you changed before running anything.

### 4. Run dry-run preview

Run the import in dry-run mode so the user can see what will be written before committing:

```bash
python3 notion_import.py --dry-run 2>&1
```

This fetches matching country pages from Notion (~90 candidates total, but stops once all selected countries are found) and runs Groq LLM extraction. Show the output and summarise: how many rules per country, any countries that weren't found.

**Timing note:** Tell the user upfront — this takes roughly 2–3 min for traversal + ~1–2 min per country for LLM extraction. For all 8 countries expect 7–10 minutes total.

### 5. Ask for confirmation

After showing the dry-run results, ask:

> "The dry run found [N] rules across [M] countries. Ready to write them to the database?"

Wait for explicit confirmation. If the user says no or wants to adjust the country list, go back to step 3.

### 6. Run the real import

Once confirmed:

```bash
python3 notion_import.py 2>&1
```

### 7. Report results

After the import completes, query the database to show the final state:

```bash
python3 -c "
import sys, os
sys.path.insert(0, os.getcwd())
from app.utils.db import Database
db = Database()
conn = db.connect()
cur = conn.execute('SELECT country, COUNT(*) as n, MAX(last_updated) as updated FROM country_guide GROUP BY country ORDER BY country')
rows = cur.fetchall()
print('Country guide entries in DB:')
for row in rows:
    country, n, updated = row[0], row[1], row[2]
    print(f'  {country}: {n} rule(s), last updated {str(updated)[:10] if updated else \"unknown\"}')
print(f'Total: {sum(n for _, n, _ in rows)} rules across {len(rows)} countries')
conn.close()
"
```

If UAE is still missing after a full import, suggest the user check whether the Notion page titles it as "United Arab Emirates - Employment Guide" and offer to add that alias to `COUNTRY_NAMES`.
