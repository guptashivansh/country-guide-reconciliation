"""Drift detection and coverage API routes."""

import time

from flask import Blueprint, jsonify, request


def create_drift_blueprint(drift_detector, drift_cache, drift_cache_ttl, config_service=None):
    bp = Blueprint("drift", __name__)

    coverage_cache = {"data": None, "expires": 0.0}

    @bp.route("/api/drift")
    def get_drift_all():
        if not drift_detector:
            return jsonify({"error": "drift detector not configured"}), 503
        now = time.monotonic()
        if drift_cache["data"] is not None and now < drift_cache["expires"]:
            return jsonify(drift_cache["data"])
        reports = drift_detector.detect_all()
        result = [r.to_dict() for r in reports]
        drift_cache["data"] = result
        drift_cache["expires"] = now + drift_cache_ttl
        return jsonify(result)

    @bp.route("/api/drift/<country>")
    def get_drift_country(country):
        if not drift_detector:
            return jsonify({"error": "drift detector not configured"}), 503
        report = drift_detector.detect(country)
        return jsonify(report.to_dict())

    @bp.route("/api/coverage")
    def get_coverage():
        if not drift_detector:
            return jsonify({"error": "drift detector not configured"}), 503
        now = time.monotonic()
        if coverage_cache["data"] is not None and now < coverage_cache["expires"]:
            return jsonify(coverage_cache["data"])
        result = drift_detector.get_coverage()
        coverage_cache["data"] = result
        coverage_cache["expires"] = now + drift_cache_ttl
        return jsonify(result)

    @bp.route("/api/coverage/core-sections", methods=["GET", "PUT"])
    def core_sections():
        if not config_service:
            return jsonify({"error": "config not available"}), 503
        if request.method == "GET":
            return jsonify({"core_sections": config_service.get_core_sections()})
        body = request.get_json(silent=True) or {}
        sections = body.get("core_sections", [])
        if not isinstance(sections, list):
            return jsonify({"error": "core_sections must be a list"}), 400
        config_service.set_core_sections(sections, changed_by=body.get("changed_by", "api"))
        coverage_cache["data"] = None
        return jsonify({"core_sections": sections, "status": "updated"})

    return bp
