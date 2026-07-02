import json
import logging

logger = logging.getLogger(__name__)

STAGE_ORDER = ["queued", "fetched", "normalized", "extracted", "reconciled"]


def run_single_job(services, job_id, source_url, country, sections=None,
                   fetch_only=False, engine=None,
                   resume_from="queued", existing_snapshot_id=None):
    ingestion_service = services["ingestion_service"]
    source_snapshot_service = services["source_snapshot_service"]
    ingestion_job_service = services["ingestion_job_service"]
    extraction_service = services["extraction_service"]
    reconciliation_service = services["reconciliation_service"]

    snapshot_id = existing_snapshot_id
    content_hash = None
    extracted_rules = None

    try:
        # ── Stage 1: Crawl + Normalize ──
        if STAGE_ORDER.index(resume_from) < STAGE_ORDER.index("normalized"):
            ingestion_result = ingestion_service.fetch_clean_text(source_url, engine=engine)

            if not ingestion_result.succeeded:
                failure_reason = ingestion_result.failure.reason if ingestion_result.failure else "source fetch failed"
                ingestion_job_service.mark_failed(job_id, failure_reason)
                return {"success": False, "failure_reason": failure_reason}

            ingestion_job_service.mark_fetched(job_id)
            content_hash = ingestion_result.content_hash

            prior = source_snapshot_service.get_latest_by_source_url(source_url)
            if prior and prior["content_hash"] == content_hash:
                snapshot_id = prior["id"]
                logger.info("Reusing snapshot %d — content unchanged", snapshot_id,
                            extra={"stage": "sync", "source_url": source_url})
                if prior["extraction_status"] == "succeeded" and prior.get("extracted_rules_json"):
                    resume_from = "extracted"
                    extracted_rules = json.loads(prior["extracted_rules_json"])
                    logger.info("Skipping extraction — reusing cached rules from snapshot %d", snapshot_id,
                                extra={"stage": "sync", "source_url": source_url})
            else:
                snapshot_id = source_snapshot_service.persist_snapshot(
                    source_url=source_url,
                    raw_text=ingestion_result.raw_text,
                    content_hash=ingestion_result.content_hash,
                )

            ingestion_job_service.mark_normalized(job_id, snapshot_id)

            if fetch_only:
                return {"success": True, "changes_queued": 0, "snapshot_id": snapshot_id}
        else:
            logger.info("Skipping crawl — resuming from %s", resume_from,
                        extra={"stage": "sync", "source_url": source_url, "ingestion_job_id": job_id})
            if resume_from == "normalized":
                ingestion_job_service.mark_fetched(job_id)
                ingestion_job_service.mark_normalized(job_id, snapshot_id)

        # ── Stage 2: Extraction ──
        if STAGE_ORDER.index(resume_from) < STAGE_ORDER.index("extracted"):
            snapshot = source_snapshot_service.get_snapshot(snapshot_id) if snapshot_id else None
            if not snapshot:
                ingestion_job_service.mark_failed(job_id, "No snapshot available for extraction")
                return {"success": False, "failure_reason": "No snapshot available for extraction"}

            extraction_result = extraction_service.extract_employment_rules(
                content=snapshot["raw_text"],
                source_url=source_url,
                country=country,
                sections=sections or (),
            )
            if extraction_result.succeeded:
                source_snapshot_service.mark_extraction_succeeded(snapshot_id, rules=extraction_result.rules)
                ingestion_job_service.mark_extracted(job_id, rules_extracted=len(extraction_result.rules))
                extracted_rules = extraction_result.rules
                content_hash = snapshot["content_hash"]
            else:
                failure_reason = extraction_result.failure.reason if extraction_result.failure else "extraction returned no valid rules"
                source_snapshot_service.mark_extraction_failed(snapshot_id)
                ingestion_job_service.mark_failed(job_id, failure_reason)
                return {"success": False, "failure_reason": failure_reason}
        else:
            logger.info("Skipping extraction — resuming from %s", resume_from,
                        extra={"stage": "sync", "source_url": source_url, "ingestion_job_id": job_id})
            ingestion_job_service.mark_extracted(job_id)

        # ── Stage 3: Reconciliation ──
        if extracted_rules is None:
            snapshot = source_snapshot_service.get_snapshot(snapshot_id) if snapshot_id else None
            if snapshot and snapshot.get("extracted_rules_json"):
                extracted_rules = json.loads(snapshot["extracted_rules_json"])
                content_hash = snapshot["content_hash"]
            else:
                ingestion_job_service.mark_failed(job_id, "No extracted rules available for reconciliation")
                return {"success": False, "failure_reason": "No extracted rules available for reconciliation"}

        if not content_hash:
            snapshot = source_snapshot_service.get_snapshot(snapshot_id)
            content_hash = snapshot["content_hash"] if snapshot else ""

        reconciliation_result = reconciliation_service.reconcile_extracted_rules(
            country=country,
            extracted_data=extracted_rules,
            source_url=source_url,
            source_hash=content_hash,
            source_snapshot_id=snapshot_id,
        )
        if not reconciliation_result.succeeded:
            failure_reason = reconciliation_result.failure.reason if reconciliation_result.failure else "reconciliation failed"
            ingestion_job_service.mark_failed(job_id, failure_reason)
            return {"success": False, "failure_reason": failure_reason}

        ingestion_job_service.mark_reconciled(job_id)
        return {"success": True, "changes_queued": reconciliation_result.changes_queued}

    except Exception as e:
        logger.error(
            "Job processing failed",
            extra={"stage": "sync", "source_url": source_url, "ingestion_job_id": job_id, "failure": str(e)},
        )
        ingestion_job_service.mark_failed(job_id, str(e))
        return {"success": False, "failure_reason": str(e)}


def run_sync(services, countries=None, fetch_only=False, engine=None):
    source_registry_service = services["source_registry_service"]
    ingestion_job_service = services["ingestion_job_service"]

    selected_countries = set(countries or [])
    all_endpoints = source_registry_service.list_trusted_source_endpoints()
    endpoints = [e for e in all_endpoints if not selected_countries or e.country in selected_countries]

    total_changes = 0
    failures = 0
    per_country = {}

    def _country_stats(country):
        return per_country.setdefault(country, {"changes": 0, "failed": False})

    print(f"\n{'='*60}")
    print(f"  SYNC STARTED — {len(endpoints)} endpoints for {list(selected_countries) or 'all countries'}")
    print(f"{'='*60}\n")

    jobs = []
    for source_endpoint in endpoints:
        job_id = ingestion_job_service.create_job(source_endpoint.url, country=source_endpoint.country)
        jobs.append((job_id, source_endpoint))

    for i, (job_id, ep) in enumerate(jobs, 1):
        stats = _country_stats(ep.country)
        short_url = ep.url.replace("https://", "").replace("http://", "")
        print(f"  [{i}/{len(jobs)}] {ep.country} — {short_url}")

        try:
            result = run_single_job(
                services, job_id, ep.url, ep.country, ep.sections,
                fetch_only=fetch_only, engine=engine,
            )
        except Exception as e:
            print(f"         ✗ EXCEPTION: {e}")
            failures += 1
            stats["failed"] = True
            continue

        if result["success"]:
            changes_queued = result["changes_queued"]
            total_changes += changes_queued
            stats["changes"] += changes_queued
            job = ingestion_job_service.get_job(job_id)
            rules = job.get("rules_extracted") if job else "?"
            print(f"         ✓ {rules} rules extracted, {changes_queued} changes queued")
        else:
            failures += 1
            stats["failed"] = True
            print(f"         ✗ FAILED: {result.get('failure_reason', 'unknown')}")

    print(f"\n{'='*60}")
    print(f"  SYNC COMPLETE — {total_changes} changes, {failures} failures")
    print(f"{'='*60}\n")

    logger.info(
        "Country guide sync completed",
        extra={"stage": "sync", "changes_queued": total_changes, "failures": failures},
    )
    return {
        "total_changes": total_changes,
        "endpoints_processed": len(endpoints),
        "failures": failures,
        "per_country": per_country,
    }
