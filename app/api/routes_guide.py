"""Guide data API routes — CRUD, history, notes, employee guide, ask."""

import logging
from datetime import datetime

from flask import Blueprint, jsonify, request

from app.api._helpers import make_config_helpers
from app.utils.config import groq_api_keys, groq_model

logger = logging.getLogger(__name__)


def _fmt_date(iso):
    try:
        return datetime.fromisoformat(iso).strftime("%b %d, %Y")
    except Exception:
        return iso or "—"


def create_guide_blueprint(review_service, temporal_rule_service=None, config_service=None, limiter=None):
    bp = Blueprint("guide", __name__)
    h = make_config_helpers(config_service)
    _flag = h["flag"]
    _section_groups = h["section_groups"]

    def _limit(limit_string):
        if limiter:
            return limiter.limit(limit_string)
        return lambda f: f

    @bp.route("/api/guide")
    def get_guide():
        return jsonify(review_service.list_country_guide_entries())

    @bp.route("/api/guide/<country>/<section>", methods=["PUT"])
    def edit_rule(country, section):
        data = request.get_json(silent=True) or {}
        new_value = data.get("value", "").strip()
        if not new_value:
            return jsonify({"success": False, "message": "value is required"}), 400
        result = review_service.manual_edit_rule(country, section, new_value)
        if result is None:
            return jsonify({"success": True, "message": "No change"})
        return jsonify({"success": True, **result})

    @bp.route("/api/guide/<country>/<section>/history")
    def get_rule_version_history(country, section):
        if not temporal_rule_service:
            return jsonify({"error": "temporal rule service not configured"}), 503
        return jsonify(temporal_rule_service.build_timeline(country, section))

    @bp.route("/api/guide/<country>/<section>/at")
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

    @bp.route("/api/notes/<country>", methods=["GET"])
    def get_country_notes(country):
        notes = review_service.get_country_notes(country)
        return jsonify(notes)

    @bp.route("/api/notes/<country>", methods=["PUT"])
    def save_country_notes(country):
        data = request.get_json(silent=True) or {}
        content = data.get("content", "")
        result = review_service.save_country_notes(country, content)
        return jsonify({"success": True, **result})

    @bp.route("/api/employee/guide/<country>")
    def api_employee_guide(country):
        rows = review_service.get_country_sections(country)
        if not rows:
            return jsonify({"error": "Country not found"}), 404
        rules_by_section = {r["section"]: r for r in rows}
        groups = []
        for g in _section_groups():
            group_rules = []
            for s in g["sections"]:
                r = rules_by_section.get(s)
                if r and (r["value"] or "").strip():
                    group_rules.append({
                        "id": s,
                        "label": s.replace("_", " ").title(),
                        "value": r["value"],
                        "last_updated": _fmt_date(r["last_updated"]),
                    })
            if group_rules:
                groups.append({"id": g["id"], "label": g["label"], "rules": group_rules})
        return jsonify({
            "country": country,
            "flag": _flag(country),
            "last_updated": _fmt_date(max(r["last_updated"] for r in rows)),
            "rule_count": len(rows),
            "groups": groups,
        })

    @bp.route("/api/employee/ask", methods=["POST"])
    @_limit("10 per minute")
    def api_employee_ask():
        data = request.get_json(silent=True) or {}
        prompt = data.get("prompt", "").strip()
        if not prompt:
            return jsonify({"error": "No prompt provided"}), 400
        try:
            from groq import Groq
            keys = groq_api_keys()
            if not keys:
                return jsonify({"error": "GROQ_API_KEY is not set. Get a free key at console.groq.com then run: export GROQ_API_KEY=your_key"}), 501
            client = Groq(api_key=keys[0])
            chat = client.chat.completions.create(
                model=groq_model(),
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            return jsonify({"reply": chat.choices[0].message.content})
        except ImportError:
            return jsonify({"error": "groq SDK not installed. Run: pip install groq"}), 501
        except Exception as exc:
            logger.exception("Ask Regulift error")
            return jsonify({"error": str(exc)}), 500

    return bp
