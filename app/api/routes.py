import logging
from datetime import datetime

from flask import Blueprint, abort, jsonify, render_template, request


logger = logging.getLogger(__name__)

FLAGS = {
    "India": "🇮🇳", "Australia": "🇦🇺", "Singapore": "🇸🇬",
    "South Africa": "🇿🇦", "UAE": "🇦🇪", "New Zealand": "🇳🇿",
    "Philippines": "🇵🇭", "Pakistan": "🇵🇰",
}

SECTION_GROUPS = [
    {"id": "leave",        "label": "Leave & Time Off",       "sections": ["annual_leave", "sick_leave", "maternity_leave", "public_holidays"]},
    {"id": "hours",        "label": "Working Hours",           "sections": ["working_hours", "overtime", "probation"]},
    {"id": "compensation", "label": "Compensation",            "sections": ["minimum_wage", "income_tax", "payroll_tax", "withholding_tax"]},
    {"id": "benefits",     "label": "Benefits & Social Security", "sections": ["health_insurance", "social_security", "pension", "employee_benefits"]},
    {"id": "employment",   "label": "Employment Terms",        "sections": ["termination_notice", "employer_obligations", "industrial_relations"]},
    {"id": "immigration",  "label": "Immigration",             "sections": ["work_permit", "work_visa", "expatriate_employment"]},
    {"id": "safety",       "label": "Workplace Safety",        "sections": ["workplace_safety", "osh_obligations"]},
]


def _fmt_date(iso):
    try:
        return datetime.fromisoformat(iso).strftime("%b %d, %Y")
    except Exception:
        return iso or "—"


def _review_payload():
    data = request.get_json(silent=True) or {}
    return {
        "comment": data.get("notes", data.get("comment", "")),
        "assignee": data.get("assignee", ""),
        "rationale": data.get("rationale", ""),
    }


def create_api_blueprint(review_service, source_registry_service, ingestion_service, source_snapshot_service, ingestion_job_service, extraction_service, reconciliation_service, country_guide_repository):
    routes = Blueprint("country_guide_routes", __name__)

    @routes.route("/")
    def index():
        return render_template("index.html")

    @routes.route("/guide")
    def guide_list():
        rows = country_guide_repository.connect().execute(
            "SELECT country, COUNT(*) as n, MAX(last_updated) as updated FROM country_guide GROUP BY country ORDER BY country"
        ).fetchall()
        countries = [
            {"name": c, "flag": FLAGS.get(c, "🌐"), "rule_count": n, "last_updated": _fmt_date(u)}
            for c, n, u in rows
        ]
        return render_template("guide_list.html", countries=countries)

    @routes.route("/guide/<country>")
    def guide_country(country):
        rows = country_guide_repository.connect().execute(
            "SELECT section, value, last_updated FROM country_guide WHERE country = ? ORDER BY section",
            (country,)
        ).fetchall()
        if not rows:
            abort(404)

        rules_by_section = {s: {"section": s, "value": v, "last_updated": _fmt_date(u)} for s, v, u in rows}
        last_updated = _fmt_date(max(u for _, _, u in rows))

        groups = []
        for g in SECTION_GROUPS:
            group_rules = [rules_by_section[s] for s in g["sections"] if s in rules_by_section]
            if group_rules:
                groups.append({"id": g["id"], "label": g["label"], "rules": group_rules})

        return render_template(
            "guide_country.html",
            country=country,
            flag=FLAGS.get(country, "🌐"),
            rule_count=len(rows),
            last_updated=last_updated,
            groups=groups,
        )

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

    @routes.route("/api/metrics")
    def get_metrics():
        queue = review_service.list_pending_review_items()
        pending = [i for i in queue if i.get("status") == "pending"]
        critical = [i for i in pending if (i.get("severity") or "").lower() == "critical"]
        confidences = [float(i["confidence"]) for i in pending if i.get("confidence") is not None]
        avg_conf = round(sum(confidences) / len(confidences) * 100) if confidences else None

        jobs = ingestion_job_service.list_recent_jobs(limit=50)
        crawl_failures = len([j for j in jobs if j.get("state") == "failed"])
        last_ok_ts = next(
            (j.get("reconciled_at") for j in jobs
             if j.get("state") == "reconciled" and j.get("reconciled_at")),
            None,
        )

        all_endpoints = source_registry_service.list_trusted_source_endpoints()
        country_count = len({e.country for e in all_endpoints if e.country})

        return jsonify({
            "sources_monitored": len(all_endpoints),
            "pending_reviews": len(pending),
            "critical_changes": len(critical),
            "avg_confidence": avg_conf,
            "crawl_failures": crawl_failures,
            "last_successful_sync": last_ok_ts,
            "trusted_source_count": country_count,
        })

    @routes.route("/api/sync", methods=["POST"])
    def sync():
        total_changes = 0
        body = request.get_json(silent=True) or {}
        selected_countries = set(body.get("countries") or [])

        all_endpoints = source_registry_service.list_trusted_source_endpoints()
        endpoints = [e for e in all_endpoints if not selected_countries or e.country in selected_countries]

        logger.info("Country guide sync started", extra={"stage": "sync", "countries": list(selected_countries) or "all"})

        for source_endpoint in endpoints:
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
        payload = _review_payload()
        result = review_service.approve_review_item(
            item_id,
            payload["comment"],
            payload["assignee"],
            payload["rationale"],
        )
        if not result:
            return jsonify({"success": False, "message": "Pending item not found"}), 404

        return jsonify({
            "success": True,
            "status": result["status"],
            "reviewed_at": result["reviewed_at"],
            "message": f"'{result['section']}' approved and published to live guide"
        })

    @routes.route("/api/reject/<int:item_id>", methods=["POST"])
    def reject(item_id):
        payload = _review_payload()
        result = review_service.reject_review_item(
            item_id,
            payload["comment"],
            payload["assignee"],
            payload["rationale"],
        )
        if not result:
            return jsonify({"success": False, "message": "Pending item not found"}), 404

        return jsonify({
            "success": True,
            "status": result["status"],
            "reviewed_at": result["reviewed_at"],
            "message": f"'{result['section']}' rejected - current guide value retained"
        })

    @routes.route("/api/assign/<int:item_id>", methods=["POST"])
    def assign(item_id):
        payload = _review_payload()
        result = review_service.assign_review_item(
            item_id,
            payload["comment"],
            payload["assignee"],
        )
        if not result:
            return jsonify({"success": False, "message": "Pending item not found"}), 404

        return jsonify({
            "success": True,
            "status": result["status"],
            "reviewed_at": result["reviewed_at"],
            "message": f"'{result['section']}' assignment saved"
        })

    @routes.route("/api/escalate/<int:item_id>", methods=["POST"])
    def escalate(item_id):
        payload = _review_payload()
        result = review_service.escalate_review_item(
            item_id,
            payload["comment"],
            payload["assignee"],
            payload["rationale"],
        )
        if not result:
            return jsonify({"success": False, "message": "Pending item not found"}), 404

        return jsonify({
            "success": True,
            "status": result["status"],
            "reviewed_at": result["reviewed_at"],
            "message": f"'{result['section']}' escalated for compliance review"
        })

    return routes
