"""Resume orphaned queued ingestion jobs from a crashed sync run."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import build_services
from app.services.sync_service import run_single_job


def main():
    services = build_services()
    services["country_guide_repository"].initialize_schema()
    services["source_snapshot_repository"].initialize_schema()
    services["ingestion_job_repository"].initialize_schema()
    services["provenance_repository"].initialize_schema()

    ingestion_job_service = services["ingestion_job_service"]
    source_registry_service = services["source_registry_service"]

    jobs = ingestion_job_service.list_recent_jobs(limit=2000)
    queued = [j for j in jobs if j["state"] == "queued"]

    if not queued:
        print("No queued jobs to resume.")
        return

    endpoints = source_registry_service.list_trusted_source_endpoints()
    ep_by_url = {ep.url: ep for ep in endpoints}

    print(f"\n{'='*60}")
    print(f"  RESUMING {len(queued)} ORPHANED QUEUED JOBS")
    print(f"{'='*60}\n")

    total_changes = 0
    failures = 0
    skipped = 0
    t0 = time.time()

    for i, job in enumerate(queued, 1):
        job_id = job["id"]
        url = job["source_url"]
        country = job.get("country", "?")
        ep = ep_by_url.get(url)
        sections = ep.sections if ep else None

        short_url = url.replace("https://", "").replace("http://", "")
        print(f"  [{i}/{len(queued)}] {country} — {short_url}", end="", flush=True)

        if not ep:
            print(" … SKIPPED (no matching endpoint)")
            skipped += 1
            continue

        try:
            result = run_single_job(
                services, job_id, url, country, sections,
            )
        except Exception as e:
            print(f" … EXCEPTION: {e}")
            failures += 1
            continue

        if result["success"]:
            changes = result.get("changes_queued", 0)
            total_changes += changes
            print(f" … OK ({changes} changes)")
        else:
            failures += 1
            reason = result.get("failure_reason", "unknown")[:60]
            print(f" … FAILED: {reason}")

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"  RESUME COMPLETE — {total_changes} changes, {failures} failures, {skipped} skipped")
    print(f"  Time: {elapsed:.0f}s ({elapsed/60:.1f}m)")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
