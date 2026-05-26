---
name: manage-sources
description: >
  List and inspect the trusted government source endpoints used by the compliance sync pipeline.
  Use when the user asks to: view sources, list endpoints, check which government sites are
  monitored, see source coverage, or understand what the sync crawls.
---

# Manage Sources Skill

Shows the trusted source endpoints that the sync pipeline crawls. These are defined in the `compliance-data` GitHub repository (official-sources.json) and loaded at runtime. Each endpoint maps a government URL to a country and set of employment law sections.

## Steps to follow

### 1. List current source endpoints

```bash
python3 -c "
import sys, os
sys.path.insert(0, os.getcwd())
from app.utils.config import load_env_file, official_sources_json_url
from app.repositories.source_endpoint_repository import TrustedSourceEndpointRepository
load_env_file()

repo = TrustedSourceEndpointRepository(json_url=official_sources_json_url())
endpoints = repo.list_active_source_endpoints()

print(f'Source: {official_sources_json_url()}')
print(f'Total active endpoints: {len(endpoints)}\n')

by_country = {}
for e in endpoints:
    by_country.setdefault(e.country, []).append(e)

for country in sorted(by_country):
    eps = by_country[country]
    print(f'{country} ({len(eps)} endpoint(s)):')
    for ep in eps:
        sections = ', '.join(ep.sections) if ep.sections else '(all sections)'
        print(f'  {ep.authority}')
        print(f'    URL: {ep.url}')
        print(f'    Sections: {sections}')
    print()
"
```

### 2. Present the results

Show the user:
- Total number of active endpoints
- Grouped by country: authority name, URL, and which sections each endpoint covers
- The source JSON URL (so they know where to edit)

### 3. Explain how to modify sources

Tell the user:

> "Source endpoints are defined in the `compliance-data` GitHub repository at:
> `data/official-sources.json`
>
> To add or modify endpoints:
> 1. Edit `official-sources.json` in the compliance-data repo
> 2. Add entries under `source_endpoints` with `authority_id`, `url`, `sections_covered`, and `status: "active"`
> 3. Ensure the authority is defined in `authorities` with `is_active: true`
> 4. Commit and push — the app fetches this JSON at startup
>
> To change the JSON URL, set `OFFICIAL_SOURCES_JSON_URL` in `.env`."

### 4. Offer next steps

- "Run **sync** to crawl these sources now"
- "Run **drift-check** to see which countries have stale data"
