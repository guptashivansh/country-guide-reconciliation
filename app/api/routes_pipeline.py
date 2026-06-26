"""Ingestion/sync/metrics API routes — sync, retry-job, ingestion-jobs, metrics, PDF intake."""

import logging
import threading

from flask import Blueprint, jsonify, request

from app.services.sync_service import run_sync, run_single_job
from app.services.slack_service import send_sync_alert
from app.utils.config import slack_webhook_url

logger = logging.getLogger(__name__)

_sync_lock = threading.Lock()
_sync_status = {"running": False, "last_result": None}


def create_pipeline_blueprint(
    review_service,
    source_registry_service,
    ingestion_service,
    source_snapshot_service,
    ingestion_job_service,
    extraction_service,
    reconciliation_service,
    pdf_ingestion_service=None,
    executor=None,
    limiter=None,
):
    bp = Blueprint("pipeline", __name__)

    def _limit(limit_string):
        if limiter:
            return limiter.limit(limit_string)
        return lambda f: f

    @bp.route("/api/ingestion-jobs")
    def get_ingestion_jobs():
        return jsonify(ingestion_job_service.list_recent_jobs(limit=500))

    @bp.route("/api/retry-job/<int:job_id>", methods=["POST"])
    @_limit("10 per minute")
    def retry_job(job_id):
        retry_result = ingestion_job_service.retry_job(job_id)
        if not retry_result:
            return jsonify({"success": False, "message": "Job not found"}), 404

        new_job_id = retry_result["job_id"]
        source_url = retry_result["source_url"]
        country = retry_result.get("country") or ""

        endpoint = None
        for ep in source_registry_service.list_trusted_source_endpoints():
            if ep.url == source_url:
                endpoint = ep
                break

        services = {
            "ingestion_service": ingestion_service,
            "source_snapshot_service": source_snapshot_service,
            "ingestion_job_service": ingestion_job_service,
            "extraction_service": extraction_service,
            "reconciliation_service": reconciliation_service,
        }
        pipeline_result = run_single_job(
            services, new_job_id, source_url,
            country=endpoint.country if endpoint else country,
            sections=endpoint.sections if endpoint else None,
        )

        if pipeline_result["success"]:
            changes = pipeline_result.get("changes_queued", 0)
            return jsonify({
                "success": True,
                "job_id": new_job_id,
                "message": f"Job #{job_id} retried as #{new_job_id} — {changes} change(s) queued",
            })
        return jsonify({
            "success": True,
            "job_id": new_job_id,
            "message": f"Job #{job_id} retried as #{new_job_id} — pipeline failed: {pipeline_result.get('failure_reason', 'unknown')}",
        })

    @bp.route("/api/metrics")
    def get_metrics():
        queue = review_service.list_pending_review_items()
        pending = [i for i in queue if i.get("status") == "pending"]
        critical = [i for i in pending if (i.get("severity") or "").lower() == "critical"]
        confidences = [float(i["confidence"]) for i in pending if i.get("confidence") is not None]
        avg_conf = round(sum(confidences) / len(confidences) * 100) if confidences else None

        jobs = ingestion_job_service.list_recent_jobs(limit=500)
        crawl_failures = len([j for j in jobs if j.get("state") == "failed"])
        last_ok_ts = max(
            (j.get("reconciled_at") for j in jobs
             if j.get("state") == "reconciled" and j.get("reconciled_at")),
            default=None,
        )

        registry = source_registry_service.get_registry_stats()

        return jsonify({
            "sources_monitored": registry["endpoints"],
            "pending_reviews": len(pending),
            "critical_changes": len(critical),
            "avg_confidence": avg_conf,
            "crawl_failures": crawl_failures,
            "last_successful_sync": last_ok_ts,
            "trusted_source_count": registry["countries"],
        })

    @bp.route("/api/sync", methods=["POST"])
    @_limit("5 per minute")
    def sync():
        if _sync_status["running"]:
            return jsonify({"success": False, "message": "Sync already in progress"}), 409

        body = request.get_json(silent=True) or {}
        selected_countries = list(body.get("countries") or [])
        fetch_only = bool(body.get("fetch_only"))
        engine = body.get("engine")

        services = {
            "source_registry_service": source_registry_service,
            "ingestion_service": ingestion_service,
            "source_snapshot_service": source_snapshot_service,
            "ingestion_job_service": ingestion_job_service,
            "extraction_service": extraction_service,
            "reconciliation_service": reconciliation_service,
        }

        def _run():
            try:
                _sync_status["running"] = True
                _sync_status["last_result"] = None
                result = run_sync(services, countries=selected_countries or None, fetch_only=fetch_only, engine=engine)
                send_sync_alert(slack_webhook_url(), result, triggered_by="manual")
                _sync_status["last_result"] = result
            except Exception as e:
                logger.error("Background sync failed", extra={"failure": str(e)})
                _sync_status["last_result"] = {"total_changes": 0, "endpoints_processed": 0, "failures": 1, "error": str(e)}
            finally:
                _sync_status["running"] = False

        threading.Thread(target=_run, daemon=True).start()
        return jsonify({"success": True, "message": "Sync started in background"})

    @bp.route("/api/sync/status", methods=["GET"])
    def sync_status():
        result = _sync_status["last_result"]
        if _sync_status["running"]:
            return jsonify({"running": True, "message": "Sync in progress"})
        if result is None:
            return jsonify({"running": False, "message": "No sync has run yet"})
        return jsonify({
            "running": False,
            "changes_queued": result.get("total_changes", 0),
            "endpoints_processed": result.get("endpoints_processed", 0),
            "failures": result.get("failures", 0),
            "message": f"{result.get('total_changes', 0)} change(s) queued for review",
        })

    @bp.route("/api/intake/pdf", methods=["POST"])
    @_limit("10 per minute")
    def api_intake_pdf():
        jurisdiction = request.form.get("jurisdiction", "").strip()
        publisher = request.form.get("publisher", "").strip()
        doc_title = request.form.get("doc_title", "").strip()
        authority = request.form.get("authority", "").strip()
        effective_date = request.form.get("effective_date", "").strip()
        file_hash = request.form.get("file_hash", "").strip()
        sections_raw = request.form.get("sections", "[]")
        try:
            import json
            selected_sections = json.loads(sections_raw) if sections_raw else []
        except Exception:
            selected_sections = []

        uploaded_file = request.files.get("file")
        if not uploaded_file or not uploaded_file.filename:
            return jsonify({"success": False, "message": "No PDF file uploaded"}), 400

        if not pdf_ingestion_service:
            return jsonify({"success": False, "message": "PDF processing is not configured"}), 503

        pdf_path = pdf_ingestion_service.save_upload(uploaded_file, filename=f"{file_hash[:12]}_{doc_title}.pdf" if file_hash else None)
        ingestion_result = pdf_ingestion_service.extract_text(pdf_path)

        if not ingestion_result.succeeded:
            reason = ingestion_result.failure.reason if ingestion_result.failure else "PDF text extraction failed"
            return jsonify({"success": False, "message": reason}), 422

        source_url = f"pdf://{file_hash[:12] if file_hash else 'upload'}#{doc_title or 'untitled'}"
        job_id = ingestion_job_service.create_job(source_url, country=jurisdiction or None)
        ingestion_job_service.mark_fetched(job_id)

        snapshot_id = source_snapshot_service.persist_snapshot(
            source_url=source_url,
            raw_text=ingestion_result.raw_text,
            content_hash=ingestion_result.content_hash,
        )
        ingestion_job_service.mark_normalized(job_id, snapshot_id)

        logger.info(
            "PDF intake — text extracted, starting LLM pipeline",
            extra={
                "stage": "pdf_intake",
                "ingestion_job_id": job_id,
                "jurisdiction": jurisdiction,
                "page_count": ingestion_result.metadata.get("page_count"),
                "character_count": ingestion_result.metadata.get("character_count"),
            },
        )

        def _run_pipeline():
            try:
                extraction_result = extraction_service.extract_employment_rules(
                    content=ingestion_result.raw_text,
                    source_url=source_url,
                    country=jurisdiction,
                    sections=selected_sections or (),
                )
                if not extraction_result.succeeded:
                    reason = extraction_result.failure.reason if extraction_result.failure else "extraction returned no rules"
                    ingestion_job_service.mark_failed(job_id, reason)
                    return
                ingestion_job_service.mark_extracted(job_id)

                reconciliation_result = reconciliation_service.reconcile_extracted_rules(
                    country=jurisdiction,
                    extracted_data=extraction_result.rules,
                    source_url=source_url,
                    source_hash=ingestion_result.content_hash,
                    source_snapshot_id=snapshot_id,
                )
                if reconciliation_result.succeeded:
                    ingestion_job_service.mark_reconciled(job_id)
                else:
                    reason = reconciliation_result.failure.reason if reconciliation_result.failure else "reconciliation failed"
                    ingestion_job_service.mark_failed(job_id, reason)
            except Exception as e:
                logger.error("PDF pipeline failed", extra={"ingestion_job_id": job_id, "error": str(e)})
                ingestion_job_service.mark_failed(job_id, str(e))

        if executor:
            executor.submit(_run_pipeline)
        else:
            import threading
            threading.Thread(target=_run_pipeline, daemon=True).start()

        return jsonify({
            "success": True,
            "job_id": job_id,
            "message": f"PDF extracted ({ingestion_result.metadata.get('page_count', '?')} pages, "
                       f"{ingestion_result.metadata.get('character_count', '?')} chars). "
                       f"LLM extraction running as job #{job_id}.",
        })

    return bp
