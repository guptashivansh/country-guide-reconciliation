import logging

logger = logging.getLogger(__name__)


def run_single_job(services, job_id, source_url, country, sections=None, fetch_only=False, engine=None):
    ingestion_service = services["ingestion_service"]
    source_snapshot_service = services["source_snapshot_service"]
    ingestion_job_service = services["ingestion_job_service"]
    extraction_service = services["extraction_service"]
    reconciliation_service = services["reconciliation_service"]

    try:
        ingestion_result = ingestion_service.fetch_clean_text(source_url, engine=engine)

        if not ingestion_result.succeeded:
            failure_reason = ingestion_result.failure.reason if ingestion_result.failure else "source fetch failed"
            ingestion_job_service.mark_failed(job_id, failure_reason)
            return {"success": False, "failure_reason": failure_reason}

        ingestion_job_service.mark_fetched(job_id)
        snapshot_id = source_snapshot_service.persist_snapshot(
            source_url=source_url,
            raw_text=ingestion_result.raw_text,
            content_hash=ingestion_result.content_hash,
        )
        ingestion_job_service.mark_normalized(job_id, snapshot_id)

        if fetch_only:
            return {"success": True, "changes_queued": 0, "snapshot_id": snapshot_id}

        extraction_result = extraction_service.extract_employment_rules(
            content=ingestion_result.raw_text,
            source_url=source_url,
            country=country,
            sections=sections or (),
        )
        if extraction_result.succeeded:
            source_snapshot_service.mark_extraction_succeeded(snapshot_id)
            ingestion_job_service.mark_extracted(job_id)
        else:
            failure_reason = extraction_result.failure.reason if extraction_result.failure else "extraction returned no valid rules"
            source_snapshot_service.mark_extraction_failed(snapshot_id)
            ingestion_job_service.mark_failed(job_id, failure_reason)
            return {"success": False, "failure_reason": failure_reason}

        reconciliation_result = reconciliation_service.reconcile_extracted_rules(
            country=country,
            extracted_data=extraction_result.rules,
            source_url=source_url,
            source_hash=ingestion_result.content_hash,
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
    """
    Run the full sync pipeline for all (or a subset of) country endpoints.

    Returns a dict with keys: total_changes, endpoints_processed, failures.
    """
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

    logger.info(
        "Country guide sync started",
        extra={"stage": "sync", "countries": list(selected_countries) or "all"},
    )

    for source_endpoint in endpoints:
        stats = _country_stats(source_endpoint.country)
        job_id = ingestion_job_service.create_job(source_endpoint.url, country=source_endpoint.country)

        result = run_single_job(
            services, job_id, source_endpoint.url,
            source_endpoint.country, source_endpoint.sections,
            fetch_only=fetch_only, engine=engine,
        )

        if result["success"]:
            changes_queued = result["changes_queued"]
            total_changes += changes_queued
            stats["changes"] += changes_queued
            logger.info(
                "Source endpoint processed",
                extra={
                    "stage": "sync",
                    "source_url": source_endpoint.url,
                    "ingestion_job_id": job_id,
                    "changes_queued": changes_queued,
                },
            )
        else:
            failures += 1
            stats["failed"] = True

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
