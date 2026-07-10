import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.ingestion.notion_section_parser import canonical_country, parse_sections
from app.services.endpoint_health import check_endpoints
from app.ingestion.html_ingestion_service import HtmlIngestionService

logger = logging.getLogger(__name__)

STAGE_ORDER = ["queued", "fetched", "normalized", "extracted", "reconciled"]


def run_single_job(services, job_id, source_url, country, sections=None,
                   fetch_only=False, engine=None, js_heavy=False,
                   resume_from="queued", existing_snapshot_id=None,
                   content_language=None,
                   cached_etag=None, cached_last_modified=None):
    ingestion_service = services["ingestion_service"]
    source_snapshot_service = services["source_snapshot_service"]
    ingestion_job_service = services["ingestion_job_service"]
    extraction_service = services["extraction_service"]
    reconciliation_service = services["reconciliation_service"]

    snapshot_id = existing_snapshot_id
    content_hash = None
    extracted_rules = None
    resp_cache = {}

    try:
        # ── Stage 1: Crawl + Normalize ──
        if STAGE_ORDER.index(resume_from) < STAGE_ORDER.index("normalized"):
            ingestion_result = ingestion_service.fetch_clean_text(
                source_url, engine=engine, js_heavy=js_heavy,
                cached_etag=cached_etag, cached_last_modified=cached_last_modified)

            if ingestion_result.metadata.get("not_modified"):
                ingestion_job_service.mark_reconciled(job_id)
                return {"success": True, "changes_queued": 0, "not_modified": True}

            resp_cache = {
                "etag": ingestion_result.metadata.get("resp_etag"),
                "last_modified": ingestion_result.metadata.get("resp_last_modified"),
            }

            if not ingestion_result.succeeded:
                failure_reason = ingestion_result.failure.reason if ingestion_result.failure else "source fetch failed"
                ingestion_job_service.mark_failed(job_id, failure_reason)
                return {"success": False, "failure_reason": failure_reason}

            ingestion_job_service.mark_fetched(job_id)
            content_hash = ingestion_result.content_hash

            pdf_links = ingestion_result.metadata.get("pdf_links", [])
            if pdf_links:
                logger.info("Found %d PDF links in %s", len(pdf_links), source_url,
                            extra={"stage": "sync", "pdf_links": [l["url"] for l in pdf_links]})

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
                content_language=content_language,
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
        return {
            "success": True,
            "changes_queued": reconciliation_result.changes_queued,
            "content_hash": content_hash,
            "resp_cache": resp_cache,
        }

    except Exception as e:
        logger.error(
            "Job processing failed",
            extra={"stage": "sync", "source_url": source_url, "ingestion_job_id": job_id, "failure": str(e)},
        )
        ingestion_job_service.mark_failed(job_id, str(e))
        return {"success": False, "failure_reason": str(e)}


_SYNC_WORKERS = 5


def run_sync(services, countries=None, fetch_only=False, engine=None, on_progress=None):
    source_registry_service = services["source_registry_service"]
    ingestion_job_service = services["ingestion_job_service"]
    ep_repo = source_registry_service.source_endpoint_repository

    selected_countries = set(countries or [])
    all_endpoints = source_registry_service.list_trusted_source_endpoints()
    endpoints = [e for e in all_endpoints
                 if e.status == 'active'
                 and (not selected_countries or e.country in selected_countries)]

    print(f"\n{'='*60}")
    print(f"  PRE-SYNC HEALTH CHECK — {len(endpoints)} endpoints")
    print(f"{'='*60}\n")

    health_results = check_endpoints(endpoints)
    broken_ids = {r["endpoint_id"] for r in health_results if not r["ok"]}
    if broken_ids:
        skipped_eps = [e for e in endpoints if e.endpoint_id in broken_ids]
        endpoints = [e for e in endpoints if e.endpoint_id not in broken_ids]
        for ep in skipped_eps:
            short = ep.url.replace("https://", "").replace("http://", "")
            detail = next((r for r in health_results if r["endpoint_id"] == ep.endpoint_id), {})
            print(f"  SKIP {ep.country} — {short} ({detail.get('error', 'unreachable')})")
            try:
                ep_repo.update_crawl_timestamp(ep.endpoint_id, success=False)
            except Exception:
                pass
        print(f"\n  {len(broken_ids)} endpoint(s) unreachable — skipped\n")

    lock = threading.Lock()
    total_changes = 0
    failures = 0
    processed = 0
    not_modified_count = 0
    per_country = {}

    def _country_stats(country):
        return per_country.setdefault(country, {"changes": 0, "failed": False})

    total = len(endpoints)
    print(f"{'='*60}")
    print(f"  SYNC STARTED — {total} endpoints ({_SYNC_WORKERS} workers) for {list(selected_countries) or 'all countries'}")
    print(f"{'='*60}\n")

    def _process_endpoint(i, ep):
        nonlocal total_changes, failures, processed, not_modified_count

        job_id = ingestion_job_service.create_job(ep.url, country=ep.country)
        short_url = ep.url.replace("https://", "").replace("http://", "")
        success = False

        cache = {}
        try:
            cache = ep_repo.get_cache_headers(ep.endpoint_id)
        except Exception:
            pass

        try:
            result = run_single_job(
                services, job_id, ep.url, ep.country, ep.sections,
                fetch_only=fetch_only, engine=engine,
                js_heavy=getattr(ep, 'is_javascript_heavy', False),
                content_language=getattr(ep, 'content_language', None),
                cached_etag=cache.get("etag"),
                cached_last_modified=cache.get("last_modified"),
            )
        except Exception as e:
            with lock:
                failures += 1
                processed += 1
                _country_stats(ep.country)["failed"] = True
                print(f"  [{processed}/{total}] {ep.country} — {short_url} ✗ EXCEPTION: {e}")
            try:
                ep_repo.update_crawl_timestamp(ep.endpoint_id, success=False)
            except Exception:
                pass
            return

        with lock:
            processed += 1
            stats = _country_stats(ep.country)
            if result.get("not_modified"):
                success = True
                not_modified_count += 1
                print(f"  [{processed}/{total}] {ep.country} — {short_url} ○ not modified")
            elif result["success"]:
                success = True
                changes_queued = result.get("changes_queued", 0)
                total_changes += changes_queued
                stats["changes"] += changes_queued
                job = ingestion_job_service.get_job(job_id)
                rules = job.get("rules_extracted") if job else "?"
                print(f"  [{processed}/{total}] {ep.country} — {short_url} ✓ {rules} rules, {changes_queued} changes")
            else:
                failures += 1
                stats["failed"] = True
                reason = result.get("failure_reason", "unknown")[:60]
                print(f"  [{processed}/{total}] {ep.country} — {short_url} ✗ {reason}")

            if on_progress:
                on_progress({
                    "endpoints_processed": processed,
                    "endpoints_total": total,
                    "current_country": ep.country,
                    "current_url": ep.url,
                    "changes_so_far": total_changes,
                    "failures": failures,
                })

        try:
            ep_repo.update_crawl_timestamp(ep.endpoint_id, success=success)
            if success and not result.get("not_modified"):
                resp_cache = result.get("resp_cache", {})
                ep_repo.update_cache_headers(
                    ep.endpoint_id,
                    etag=resp_cache.get("etag"),
                    last_modified=resp_cache.get("last_modified"),
                    content_hash=result.get("content_hash"),
                )
        except Exception as cache_err:
            logger.warning("Failed to update cache headers for %s: %s", ep.endpoint_id, cache_err)

    with ThreadPoolExecutor(max_workers=_SYNC_WORKERS) as pool:
        futures = {
            pool.submit(_process_endpoint, i, ep): ep
            for i, ep in enumerate(endpoints, 1)
        }
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logger.error("Unexpected worker error: %s", e)

    skipped_count = len(broken_ids) if broken_ids else 0
    cached_msg = f", {not_modified_count} cached" if not_modified_count else ""
    print(f"\n{'='*60}")
    print(f"  SYNC COMPLETE — {total_changes} changes, {failures} failures, {skipped_count} skipped{cached_msg}")
    print(f"{'='*60}\n")

    logger.info(
        "Country guide sync completed",
        extra={"stage": "sync", "changes_queued": total_changes,
               "failures": failures, "skipped": skipped_count},
    )
    return {
        "total_changes": total_changes,
        "endpoints_processed": len(endpoints),
        "failures": failures,
        "skipped": skipped_count,
        "not_modified": not_modified_count,
        "per_country": per_country,
    }


def discover_landing_page_links(services, countries=None):
    source_registry_service = services["source_registry_service"]
    ep_repo = source_registry_service.source_endpoint_repository
    all_endpoints = ep_repo.list_all_source_endpoints()
    selected_countries = set(countries or [])
    landing_eps = [
        e for e in all_endpoints
        if e.status == "landing_page"
        and (not selected_countries or e.country in selected_countries)
    ]

    if not landing_eps:
        print("  No landing page endpoints to scan")
        return {"content_links": [], "pdf_links": []}

    print(f"\n{'='*60}")
    print(f"  LANDING PAGE DISCOVERY — scanning {len(landing_eps)} endpoints")
    print(f"{'='*60}\n")

    import requests as req
    from app.ingestion.html_ingestion_service import _HEADERS

    all_content_links = []
    all_pdf_links = []

    for ep in landing_eps:
        short = ep.url.replace("https://", "").replace("http://", "")
        try:
            resp = req.get(ep.url, headers=_HEADERS, timeout=15, allow_redirects=True)
            if resp.status_code != 200:
                print(f"  SKIP {ep.country} — {short} (HTTP {resp.status_code})")
                continue

            content_links = HtmlIngestionService.discover_content_links(
                ep.url, resp.text)
            pdf_links = HtmlIngestionService.extract_pdf_links(
                ep.url, resp.text)

            for link in content_links:
                link["country"] = ep.country
                link["sections"] = ep.sections
                link["content_language"] = ep.content_language
                link["parent_url"] = ep.url
            for link in pdf_links:
                link["country"] = ep.country
                link["sections"] = ep.sections
                link["parent_url"] = ep.url

            all_content_links.extend(content_links)
            all_pdf_links.extend(pdf_links)

            print(f"  {ep.country} — {short}: {len(content_links)} content links, {len(pdf_links)} PDF links")
        except Exception as exc:
            print(f"  SKIP {ep.country} — {short} ({exc})")

    existing_urls = {e.url for e in all_endpoints}
    new_content = [l for l in all_content_links if l["url"] not in existing_urls]
    new_pdfs = [l for l in all_pdf_links if l["url"] not in existing_urls]

    print(f"\n  Found {len(new_content)} new content links, {len(new_pdfs)} new PDF links")
    print(f"{'='*60}\n")

    return {"content_links": new_content, "pdf_links": new_pdfs}


def run_notion_reconciliation(services):
    """
    Fetch current Notion content, parse into sections, compare against
    all pending review items, and auto-resolve matches.
    """
    notion_service = services.get("notion_ingestion_service")
    reconciliation_service = services.get("reconciliation_service")
    if not notion_service or not reconciliation_service:
        logger.warning("Notion reconciliation skipped: missing services")
        return {"resolved": 0, "unresolved": 0, "skipped": True}

    print(f"\n{'='*60}")
    print("  NOTION RECONCILIATION — fetching current Notion content")
    print(f"{'='*60}\n")

    country_texts = notion_service.fetch_all_employment_guides()
    if not country_texts:
        logger.warning("Notion reconciliation skipped: no content fetched")
        print("  No Notion content fetched — skipping reconciliation")
        return {"resolved": 0, "unresolved": 0, "skipped": True}

    notion_sections = {}
    for raw_country, text in country_texts.items():
        country = canonical_country(raw_country)
        sections = parse_sections(text)
        if sections:
            notion_sections[country] = sections

    print(f"  Parsed {len(notion_sections)} countries from Notion")

    result = reconciliation_service.reconcile_against_notion(notion_sections)

    print(f"  Resolved: {result['resolved']} | Unresolved: {result['unresolved']}")
    print(f"{'='*60}\n")

    logger.info(
        "Notion reconciliation complete",
        extra={"resolved": result["resolved"], "unresolved": result["unresolved"]},
    )
    return result
