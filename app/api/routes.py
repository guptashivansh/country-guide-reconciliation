import logging

from flask import Blueprint, jsonify, render_template, request


logger = logging.getLogger(__name__)


def create_api_blueprint(review_service, source_registry_service, ingestion_service, source_snapshot_service, ingestion_job_service, extraction_service, reconciliation_service):
    routes = Blueprint("country_guide_routes", __name__)

    @routes.route("/")
    def index():
        return render_template("index.html")

    @routes.route("/api/guide")
    def get_guide():
        return jsonify(review_service.list_country_guide_entries())

    @routes.route("/api/queue")
    def get_queue():
        return jsonify(review_service.list_pending_review_items())

    @routes.route("/api/audit")
    def get_audit():
        return jsonify(review_service.list_audit_entries())

    @routes.route("/api/ingestion-jobs")
    def get_ingestion_jobs():
        return jsonify(ingestion_job_service.list_recent_jobs())

    @routes.route("/api/sync", methods=["POST"])
    def sync():
        total_changes = 0
        logger.info("Country guide sync started", extra={"stage": "sync"})

        for source_endpoint in source_registry_service.list_trusted_source_endpoints():
            job_id = ingestion_job_service.create_job(source_endpoint.url)
            try:
                logger.info(
                    "Processing source endpoint",
                    extra={"stage": "sync", "source_url": source_endpoint.url, "ingestion_job_id": job_id},
                )
                ingestion_result = ingestion_service.fetch_clean_text(source_endpoint.url)

                if not ingestion_result.succeeded:
                    failure_reason = ingestion_result.failure.reason if ingestion_result.failure else "source fetch failed"
                    logger.warning(
                        "Source endpoint returned no content",
                        extra={
                            "stage": "ingestion_fetch",
                            "source_url": source_endpoint.url,
                            "ingestion_job_id": job_id,
                            "result_status": ingestion_result.status,
                            "failure": failure_reason,
                            "failure_type": ingestion_result.failure.type if ingestion_result.failure else None,
                        },
                    )
                    ingestion_job_service.mark_failed(job_id, failure_reason)
                    continue

                ingestion_job_service.mark_fetched(job_id)
                snapshot_id = source_snapshot_service.persist_snapshot(
                    source_url=source_endpoint.url,
                    raw_text=ingestion_result.raw_text,
                    content_hash=ingestion_result.content_hash,
                )
                ingestion_job_service.mark_normalized(job_id, snapshot_id)

                extraction_result = extraction_service.extract_employment_rules(
                    content=ingestion_result.raw_text,
                    source_url=source_endpoint.url,
                    country=source_endpoint.country,
                    sections=source_endpoint.sections,
                )
                if extraction_result.succeeded:
                    source_snapshot_service.mark_extraction_succeeded(snapshot_id)
                    ingestion_job_service.mark_extracted(job_id)
                else:
                    failure_reason = extraction_result.failure.reason if extraction_result.failure else "extraction returned no valid rules"
                    source_snapshot_service.mark_extraction_failed(snapshot_id)
                    ingestion_job_service.mark_failed(job_id, failure_reason)
                    continue
                logger.info(
                    "Extraction produced validated rules",
                    extra={
                        "stage": "extraction",
                        "source_url": source_endpoint.url,
                        "ingestion_job_id": job_id,
                        "source_snapshot_id": snapshot_id,
                        "extraction_count": len(extraction_result.rules),
                        "result_status": extraction_result.status,
                    },
                )

                reconciliation_result = reconciliation_service.reconcile_extracted_rules(
                    country=source_endpoint.country,
                    extracted_data=extraction_result.rules,
                    source_url=source_endpoint.url,
                    source_hash=ingestion_result.content_hash,
                    source_snapshot_id=snapshot_id,
                )
                if not reconciliation_result.succeeded:
                    failure_reason = reconciliation_result.failure.reason if reconciliation_result.failure else "reconciliation failed"
                    ingestion_job_service.mark_failed(job_id, failure_reason)
                    continue

                changes_queued = reconciliation_result.changes_queued
                total_changes += changes_queued
                ingestion_job_service.mark_reconciled(job_id)
                logger.info(
                    "Source endpoint processed",
                    extra={
                        "stage": "sync",
                        "source_url": source_endpoint.url,
                        "ingestion_job_id": job_id,
                        "source_snapshot_id": snapshot_id,
                        "extraction_count": len(extraction_result.rules),
                        "changes_queued": changes_queued,
                        "result_status": reconciliation_result.status,
                    },
                )
            except Exception as e:
                logger.error(
                    "Source endpoint processing failed",
                    extra={"stage": "sync", "source_url": source_endpoint.url, "ingestion_job_id": job_id, "failure": str(e)},
                )
                ingestion_job_service.mark_failed(job_id, str(e))

        logger.info(
            "Country guide sync completed",
            extra={"stage": "sync", "changes_queued": total_changes},
        )
        return jsonify({
            "success": True,
            "changes_queued": total_changes,
            "message": f"{total_changes} change(s) queued for review" if total_changes > 0 else "No changes detected"
        })

    @routes.route("/api/approve/<int:item_id>", methods=["POST"])
    def approve(item_id):
        data = request.json or {}
        result = review_service.approve_review_item(item_id, data.get("comment", ""))
        if not result:
            return jsonify({"success": False, "message": "Pending item not found"}), 404

        return jsonify({
            "success": True,
            "message": f"'{result['section']}' approved and published to live guide"
        })

    @routes.route("/api/reject/<int:item_id>", methods=["POST"])
    def reject(item_id):
        data = request.json or {}
        result = review_service.reject_review_item(item_id, data.get("comment", ""))
        if not result:
            return jsonify({"success": False, "message": "Pending item not found"}), 404

        return jsonify({
            "success": True,
            "message": f"'{result['section']}' rejected - current guide value retained"
        })

    return routes
