"""Review queue API routes — approve, reject, assign, escalate, bulk-approve, audit."""

from datetime import datetime

from flask import Blueprint, jsonify, request


def _review_payload():
    data = request.get_json(silent=True) or {}
    return {
        "comment": data.get("notes", data.get("comment", "")),
        "assignee": data.get("assignee", ""),
        "rationale": data.get("rationale", ""),
        "effective_date": data.get("effective_date"),
    }


def create_review_blueprint(review_service, source_registry_service=None, limiter=None):
    bp = Blueprint("review", __name__)

    def _limit(limit_string):
        if limiter:
            return limiter.limit(limit_string)
        return lambda f: f

    @bp.route("/api/queue")
    def get_queue():
        items = review_service.list_pending_review_items()
        if source_registry_service:
            active = source_registry_service.active_country_names()
            if active:
                items = [i for i in items if i.get("country") in active]
        return jsonify(items)

    @bp.route("/api/approve/<int:item_id>", methods=["POST"])
    @_limit("30 per minute")
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

    @bp.route("/api/reject/<int:item_id>", methods=["POST"])
    @_limit("30 per minute")
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

    @bp.route("/api/assign/<int:item_id>", methods=["POST"])
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

    @bp.route("/api/escalate/<int:item_id>", methods=["POST"])
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

    @bp.route("/api/bulk-approve", methods=["POST"])
    @_limit("10 per minute")
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

    @bp.route("/api/audit")
    def get_audit():
        entries = review_service.list_audit_entries()
        if source_registry_service:
            active = source_registry_service.active_country_names()
            if active:
                entries = [e for e in entries if e.get("country") in active]
        country_filter = request.args.get("country")
        since_filter = request.args.get("since")
        if country_filter:
            entries = [e for e in entries if e.get("country") == country_filter]
        if since_filter:
            try:
                since_dt = datetime.fromisoformat(since_filter)
                entries = [e for e in entries if e.get("timestamp") and datetime.fromisoformat(e["timestamp"]) > since_dt]
            except ValueError:
                pass
        if request.args.get("dedupe") == "1":
            seen = {}
            deduped = []
            for e in entries:
                key = (e.get("country"), e.get("section"))
                if key not in seen:
                    seen[key] = True
                    deduped.append(e)
            entries = deduped
        return jsonify(entries)

    return bp
