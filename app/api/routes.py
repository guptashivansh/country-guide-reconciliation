import logging
from datetime import datetime

from flask import Blueprint, abort, jsonify, render_template, request
from app.services.sync_service import run_sync
from app.services.slack_service import send_sync_alert
from app.utils.config import slack_webhook_url


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
        "effective_date": data.get("effective_date"),
    }


def create_api_blueprint(review_service, source_registry_service, ingestion_service, source_snapshot_service, ingestion_job_service, extraction_service, reconciliation_service, provenance_service=None, temporal_rule_service=None, drift_detector=None):
    routes = Blueprint("country_guide_routes", __name__)

    @routes.route("/")
    def index():
        return render_template("index.html")

    @routes.route("/guide")
    def guide_list():
        countries = [
            {"name": r["country"], "flag": FLAGS.get(r["country"], "🌐"),
             "rule_count": r["rule_count"], "last_updated": _fmt_date(r["last_updated"])}
            for r in review_service.list_countries_summary()
        ]
        return render_template("guide_list.html", countries=countries)

    @routes.route("/guide/<country>")
    def guide_country(country):
        rows = review_service.get_country_sections(country)
        if not rows:
            abort(404)

        rules_by_section = {r["section"]: {"section": r["section"], "value": r["value"], "last_updated": _fmt_date(r["last_updated"])} for r in rows}
        last_updated = _fmt_date(max(r["last_updated"] for r in rows))

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
        body = request.get_json(silent=True) or {}
        selected_countries = list(body.get("countries") or [])

        services = {
            "source_registry_service": source_registry_service,
            "ingestion_service": ingestion_service,
            "source_snapshot_service": source_snapshot_service,
            "ingestion_job_service": ingestion_job_service,
            "extraction_service": extraction_service,
            "reconciliation_service": reconciliation_service,
        }
        result = run_sync(services, countries=selected_countries or None)
        send_sync_alert(slack_webhook_url(), result, triggered_by="manual")

        total_changes = result["total_changes"]
        return jsonify({
            "success": True,
            "changes_queued": total_changes,
            "endpoints_processed": result["endpoints_processed"],
            "failures": result["failures"],
            "message": f"{total_changes} change(s) queued for review" if total_changes > 0 else "No changes detected"
        })

    @routes.route("/api/bulk-approve", methods=["POST"])
    def bulk_approve():
        body = request.get_json(silent=True) or {}
        country = body.get("country", "").strip()
        if not country:
            return jsonify({"success": False, "message": "country is required"}), 400

        result = review_service.bulk_approve_non_critical(
            country,
            comment=body.get("comment", "Bulk approval: non-critical pending items"),
            rationale=body.get("rationale", "Bulk approved — non-critical"),
            effective_date=body.get("effective_date"),
        )
        approved = result["approved"]
        if approved == 0:
            return jsonify({"success": True, "approved": 0, "message": f"No eligible non-critical items for {country}"})
        return jsonify({
            "success": True,
            "approved": approved,
            "effective_date": body.get("effective_date"),
            "message": f"{approved} non-critical change{'s' if approved != 1 else ''} approved for {country}",
        })

    @routes.route("/api/approve/<int:item_id>", methods=["POST"])
    def approve(item_id):
        payload = _review_payload()
        result = review_service.approve_review_item(
            item_id,
            payload["comment"],
            payload["assignee"],
            payload["rationale"],
            payload["effective_date"],
        )
        if not result:
            return jsonify({"success": False, "message": "Pending item not found"}), 404

        return jsonify({
            "success": True,
            "status": result["status"],
            "reviewed_at": result["reviewed_at"],
            "effective_date": result.get("effective_date"),
            "version_number": result.get("version_number"),
            "approval_reference": result.get("approval_reference"),
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

    @routes.route("/api/provenance/<country>/<section>")
    def get_provenance(country, section):
        if not provenance_service:
            return jsonify({"error": "provenance service not configured"}), 503
        chain = provenance_service.get_chain(country, section)
        if not chain:
            return jsonify({"error": f"No provenance found for {country}/{section}"}), 404
        return jsonify(chain)

    @routes.route("/api/provenance/<country>/<section>/history")
    def get_provenance_history(country, section):
        if not provenance_service:
            return jsonify({"error": "provenance service not configured"}), 503
        history = provenance_service.get_history(country, section)
        return jsonify({"country": country, "section": section, "history": history})

    @routes.route("/api/drift")
    def get_drift_all():
        if not drift_detector:
            return jsonify({"error": "drift detector not configured"}), 503
        reports = drift_detector.detect_all()
        return jsonify([r.to_dict() for r in reports])

    @routes.route("/api/drift/<country>")
    def get_drift_country(country):
        if not drift_detector:
            return jsonify({"error": "drift detector not configured"}), 503
        report = drift_detector.detect(country)
        return jsonify(report.to_dict())

    @routes.route("/api/guide/<country>/<section>/history")
    def get_rule_version_history(country, section):
        if not temporal_rule_service:
            return jsonify({"error": "temporal rule service not configured"}), 503
        return jsonify(temporal_rule_service.build_timeline(country, section))

    @routes.route("/api/guide/<country>/<section>/at")
    def get_rule_at_date(country, section):
        if not temporal_rule_service:
            return jsonify({"error": "temporal rule service not configured"}), 503
        as_of_date = request.args.get("date") or request.args.get("as_of")
        if not as_of_date:
            return jsonify({"error": "date query parameter is required"}), 400
        try:
            rule = temporal_rule_service.get_rule_at_date(country, section, as_of_date)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if not rule:
            return jsonify({"error": f"No rule found for {country}/{section} at {as_of_date}"}), 404
        return jsonify({"country": country, "section": section, "as_of_date": as_of_date, "rule": rule})

    return routes
