---
name: retry-job
description: >
  View recent ingestion jobs and retry failed ones. Use when the user asks to: retry a failed job,
  check job status, view ingestion history, re-run a crawl, or debug a pipeline failure.
---

# Retry Job Skill

Shows recent ingestion pipeline jobs and lets the user retry failed ones. Each job represents a single source endpoint going through the crawl → extract → reconcile pipeline.

## Steps to follow

### 1. List recent jobs

```bash
python3 -c "
import sys, os
sys.path.insert(0, os.getcwd())
from app import build_services
services = build_services()
services['ingestion_job_repository'].initialize_schema()
jobs = services['ingestion_job_service'].list_recent_jobs(limit=25)
if not jobs:
    print('No ingestion jobs found.')
else:
    print(f'Recent ingestion jobs ({len(jobs)}):')
    print()
    for j in jobs:
        state = j['state'].upper()
        country = j.get('country', '?')
        queued = (j.get('queued_at') or '?')[:16]
        url = j['source_url'][:60]
        fail = ''
        if j.get('failure_reason'):
            fail = f' — {j[\"failure_reason\"][:80]}'
        print(f'  [{j[\"id\"]}] {state:12s} | {country:15s} | {queued} | {url}{fail}')
"
```

### 2. Ask what to do

If there are failed jobs, ask:

> "Would you like to:
> - **Retry a specific job** — provide the job ID
> - **Retry all failed jobs** — re-run every failed job
> - **View details** of a specific job"

Wait for the user's answer.

### 3a. Retry a single job

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

retry = services['ingestion_job_service'].retry_job(JOB_ID)
if not retry:
    print(f'Job {JOB_ID} not found.')
else:
    print(f'Retrying job {JOB_ID} as new job {retry[\"job_id\"]}')
    print(f'  Source: {retry[\"source_url\"]}')
    print(f'  Country: {retry.get(\"country\", \"?\")}')

    from app.services.sync_service import run_single_job
    result = run_single_job(services, retry['job_id'], retry['source_url'], retry.get('country'))
    if result['success']:
        print(f'  Result: SUCCESS — {result.get(\"changes_queued\", 0)} change(s) queued')
    else:
        print(f'  Result: FAILED — {result.get(\"failure_reason\", \"unknown\")}')
"
```

Replace `JOB_ID` with the user-provided job ID.

### 3b. Retry all failed jobs

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
from app.services.sync_service import run_single_job

jobs = services['ingestion_job_service'].list_recent_jobs(limit=50)
failed = [j for j in jobs if j['state'] == 'failed']
print(f'Retrying {len(failed)} failed job(s)...\n')
for j in failed:
    retry = services['ingestion_job_service'].retry_job(j['id'])
    if retry:
        result = run_single_job(services, retry['job_id'], retry['source_url'], retry.get('country'))
        status = 'OK' if result['success'] else f'FAILED: {result.get(\"failure_reason\", \"?\")[:60]}'
        print(f'  [{j[\"id\"]}] {j.get(\"country\", \"?\")}: {status}')
"
```

### 3c. View job details

```bash
python3 -c "
import sys, os
sys.path.insert(0, os.getcwd())
from app import build_services
services = build_services()
services['ingestion_job_repository'].initialize_schema()
j = services['ingestion_job_service'].get_job(JOB_ID)
if not j:
    print(f'Job {JOB_ID} not found.')
else:
    print(f'Job {j[\"id\"]}:')
    print(f'  State:     {j[\"state\"]}')
    print(f'  Country:   {j.get(\"country\", \"?\")}')
    print(f'  Source:    {j[\"source_url\"]}')
    print(f'  Queued:    {j.get(\"queued_at\", \"?\")}')
    print(f'  Fetched:   {j.get(\"fetched_at\", \"—\")}')
    print(f'  Normalized:{j.get(\"normalized_at\", \"—\")}')
    print(f'  Extracted: {j.get(\"extracted_at\", \"—\")}')
    print(f'  Reconciled:{j.get(\"reconciled_at\", \"—\")}')
    print(f'  Failed:    {j.get(\"failed_at\", \"—\")}')
    print(f'  Reason:    {j.get(\"failure_reason\", \"—\")}')
    print(f'  Snapshot:  {j.get(\"source_snapshot_id\", \"—\")}')
"
```

### 4. Report results

Summarise which retries succeeded and which failed again. For persistent failures, suggest checking:
- Whether the source URL is still accessible
- Rate limiting from the government site
- Groq API key validity
