---
name: sync
description: >
  Trigger the full compliance sync pipeline (crawl → extract → reconcile) for all or specific countries.
  Use when the user asks to: run a sync, crawl sources, refresh country data, check for updates
  from government sources, or re-sync a specific country.
---

# Compliance Sync Skill

Runs the full crawl → extract → reconcile pipeline via `app.services.sync_service.run_sync()`. Each trusted government source endpoint is fetched, its HTML is normalized, employment rules are extracted via Groq LLM, and changes are reconciled against the current guide — queuing diffs for human review.

The database backend is determined by `DATABASE_URL` (PostgreSQL) or falls back to SQLite. All queries go through `app.utils.db.Database`.

## Steps to follow

### 1. Verify environment

```bash
python3 -c "
import sys, os
sys.path.insert(0, os.getcwd())
from app.utils.config import load_env_file, groq_api_keys
load_env_file()
keys = groq_api_keys()
print(f'GROQ_API_KEY(s): {len(keys)} key(s) configured') if keys else print('ERROR: No GROQ_API_KEY set in .env')
"
```

If no Groq key is configured, tell the user to add `GROQ_API_KEY` to `.env` and stop.

### 2. Show current state and ask scope

Show the countries currently in the DB and the trusted source endpoints:

```bash
python3 -c "
import sys, os
sys.path.insert(0, os.getcwd())
from app.utils.config import load_env_file, official_sources_json_url
from app.repositories.source_endpoint_repository import TrustedSourceEndpointRepository
from app.utils.db import Database
load_env_file()

db = Database()
conn = db.connect()
cur = conn.execute('SELECT country, COUNT(*) as n FROM country_guide GROUP BY country ORDER BY country')
rows = cur.fetchall()
if rows:
    print('Countries in DB:')
    for r in rows:
        print(f'  {r[0]}: {r[1]} rule(s)')
else:
    print('DB is empty.')
conn.close()

repo = TrustedSourceEndpointRepository(json_url=official_sources_json_url())
endpoints = repo.list_active_source_endpoints()
print(f'\nTrusted source endpoints: {len(endpoints)}')
countries = sorted(set(e.country for e in endpoints))
print(f'Countries covered: {", ".join(countries)}')
"
```

Ask the user:

> "Which countries do you want to sync?
> - **All** — sync every country with a trusted source endpoint
> - **Specific countries** — which ones?
>
> Note: syncing fetches live government pages, runs LLM extraction, and queues diffs for review. This can take several minutes depending on how many endpoints are configured."

Wait for the user's answer.

### 3. Run the sync

Based on the user's choice, run with or without a country filter:

**All countries:**
```bash
python3 -c "
import sys, os
sys.path.insert(0, os.getcwd())
from app import build_services
services = build_services()
services['country_guide_repository'].initialize_schema()
services['source_snapshot_repository'].initialize_schema()
services['ingestion_job_repository'].initialize_schema()
services['provenance_repository'].initialize_schema()
from app.services.sync_service import run_sync
result = run_sync(services)
print(f'Endpoints processed: {result[\"endpoints_processed\"]}')
print(f'Total changes queued: {result[\"total_changes\"]}')
print(f'Failures: {result[\"failures\"]}')
for country, stats in sorted(result.get('per_country', {}).items()):
    status = 'FAILED' if stats.get('failed') else f'{stats[\"changes\"]} change(s)'
    print(f'  {country}: {status}')
"
```

**Specific countries** (replace the list):
```bash
python3 -c "
import sys, os
sys.path.insert(0, os.getcwd())
from app import build_services
services = build_services()
services['country_guide_repository'].initialize_schema()
services['source_snapshot_repository'].initialize_schema()
services['ingestion_job_repository'].initialize_schema()
services['provenance_repository'].initialize_schema()
from app.services.sync_service import run_sync
result = run_sync(services, countries=['India', 'Australia'])
print(f'Endpoints processed: {result[\"endpoints_processed\"]}')
print(f'Total changes queued: {result[\"total_changes\"]}')
print(f'Failures: {result[\"failures\"]}')
for country, stats in sorted(result.get('per_country', {}).items()):
    status = 'FAILED' if stats.get('failed') else f'{stats[\"changes\"]} change(s)'
    print(f'  {country}: {status}')
"
```

### 4. Report results

Summarise the sync results to the user:
- How many endpoints were processed
- How many changes were queued for review
- Any failures (and which countries failed)
- Suggest running the **review** skill to act on queued changes

If there were failures, offer to retry individual failed jobs using the **retry-job** skill.
