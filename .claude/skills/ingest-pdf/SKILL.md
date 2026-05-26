---
name: ingest-pdf
description: >
  Ingest a compliance PDF document into the extraction pipeline — create an ingestion job,
  extract employment rules via LLM, and queue changes for review. Use when the user asks to:
  upload a PDF, ingest a compliance document, process a government PDF, or extract rules from
  a document.
---

# Ingest PDF Skill

Creates an ingestion job for a compliance PDF document, extracts employment rules using Groq LLM, and queues detected changes for human review. This is the manual document intake path (as opposed to the automated crawl-based sync).

## Steps to follow

### 1. Gather document metadata

Ask the user for the following information:

> "I need details about the compliance document:
> 1. **Country/Jurisdiction** — which country does this apply to?
> 2. **Document title** — what is this document called?
> 3. **Publisher/Authority** — who published it? (e.g., Ministry of Labour)
> 4. **Effective date** — when does it take effect? (YYYY-MM-DD, or 'unknown')
> 5. **File path or URL** — where is the PDF?"

Wait for the user's answers before proceeding.

### 2. Verify the file exists

If a local file path was provided:
```bash
ls -la "FILE_PATH" 2>/dev/null && echo "File found" || echo "ERROR: File not found"
```

If a URL was provided, verify it's accessible:
```bash
python3 -c "
import urllib.request
try:
    req = urllib.request.Request('URL', method='HEAD')
    resp = urllib.request.urlopen(req, timeout=10)
    print(f'URL accessible: {resp.status}')
except Exception as e:
    print(f'ERROR: {e}')
"
```

### 3. Extract text from the PDF

```bash
python3 -c "
import sys
try:
    import pdfplumber
except ImportError:
    print('ERROR: pdfplumber not installed. Run: pip install pdfplumber')
    sys.exit(1)

with pdfplumber.open('FILE_PATH') as pdf:
    text = '\n'.join(page.extract_text() or '' for page in pdf.pages)
    print(f'Extracted {len(text):,} characters from {len(pdf.pages)} page(s)')
    print('--- Preview (first 500 chars) ---')
    print(text[:500])
"
```

Show the user the extraction preview and page count. Ask for confirmation before proceeding.

### 4. Create ingestion job and run extraction

```bash
python3 -c "
import sys, os, hashlib
sys.path.insert(0, os.getcwd())
import pdfplumber
from app import build_services
services = build_services()
services['country_guide_repository'].initialize_schema()
services['source_snapshot_repository'].initialize_schema()
services['ingestion_job_repository'].initialize_schema()
services['provenance_repository'].initialize_schema()

with pdfplumber.open('FILE_PATH') as pdf:
    text = '\n'.join(page.extract_text() or '' for page in pdf.pages)

content_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
source_url = 'pdf://FILE_PATH'

job_id = services['ingestion_job_service'].create_job(source_url, country='COUNTRY')
print(f'Ingestion job created: {job_id}')

snapshot_id = services['source_snapshot_service'].persist_snapshot(
    source_url=source_url,
    raw_text=text,
    content_hash=content_hash,
)
services['ingestion_job_service'].mark_fetched(job_id)
services['ingestion_job_service'].mark_normalized(job_id, snapshot_id)
print(f'Snapshot saved: {snapshot_id}')

extraction_result = services['extraction_service'].extract_employment_rules(
    content=text,
    source_url=source_url,
    country='COUNTRY',
    sections=(),
)

if extraction_result.succeeded:
    services['ingestion_job_service'].mark_extracted(job_id)
    print(f'Extraction succeeded: {len(extraction_result.rules)} rule(s) found')
    for rule in extraction_result.rules:
        print(f'  {rule.get(\"section\", \"?\")}: {str(rule.get(\"value\", \"\"))[:80]}')

    recon = services['reconciliation_service'].reconcile_extracted_rules(
        country='COUNTRY',
        extracted_data=extraction_result.rules,
        source_url=source_url,
        source_hash=content_hash,
        source_snapshot_id=snapshot_id,
    )
    services['ingestion_job_service'].mark_reconciled(job_id)
    print(f'Reconciliation: {recon.changes_queued} change(s) queued for review')
else:
    services['ingestion_job_service'].mark_failed(job_id, 'extraction failed')
    print(f'Extraction failed')
"
```

Replace `FILE_PATH` and `COUNTRY` with the user-provided values.

### 5. Report results

Summarise:
- Number of rules extracted
- Number of changes queued for review
- Any sections where the extracted value differs from the current guide

Suggest: "Use the **review** skill to approve or reject the queued changes."
