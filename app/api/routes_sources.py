"""Source registry API routes."""

from flask import Blueprint, jsonify, request

from app.api._helpers import make_config_helpers


def create_sources_blueprint(source_registry_service, ingestion_job_service, config_service=None):
    bp = Blueprint("sources", __name__)
    h = make_config_helpers(config_service)
    _flags = h["flags"]

    @bp.route("/api/sources/stats")
    def source_registry_stats():
        return jsonify(source_registry_service.get_registry_stats())

    @bp.route("/api/sources/countries")
    def source_registry_countries():
        return jsonify(source_registry_service.list_countries())

    @bp.route("/api/sources/authorities")
    def source_registry_authorities():
        country_id = request.args.get("country_id")
        return jsonify(source_registry_service.list_authorities(country_id))

    @bp.route("/api/sources/endpoints")
    def source_registry_endpoints():
        country = request.args.get("country")
        if country:
            eps = source_registry_service.list_endpoints_for_country(country)
        else:
            eps = source_registry_service.list_trusted_source_endpoints()
        return jsonify([{
            "endpoint_id": ep.endpoint_id,
            "name": ep.name,
            "country": ep.country,
            "iso_code": ep.iso_code,
            "authority": ep.authority,
            "authority_type": ep.authority_type,
            "authority_url": ep.authority_url,
            "url": ep.url,
            "sections": list(ep.sections),
            "source_type": ep.source_type,
            "content_language": ep.content_language,
            "extraction_strategy": ep.extraction_strategy,
            "parser_key": ep.parser_key,
            "crawl_frequency": ep.crawl_frequency,
            "change_detection_strategy": ep.change_detection_strategy,
            "is_javascript_heavy": ep.is_javascript_heavy,
            "requires_authentication": ep.requires_authentication,
            "escalation_required": ep.escalation_required,
            "supports_replay": ep.supports_replay,
            "trust_level": ep.trust_level,
            "owner_team": ep.owner_team,
            "notes": ep.notes,
            "status": ep.status,
        } for ep in eps])

    @bp.route("/api/sources/endpoints", methods=["POST"])
    def source_create_endpoint():
        data = request.get_json(silent=True) or {}
        if not data.get("authority_id") or not data.get("url"):
            return jsonify({"error": "authority_id and url are required"}), 400
        result = source_registry_service.create_endpoint(data)
        return jsonify(result), 201

    @bp.route("/api/sources/endpoints/<endpoint_id>", methods=["PUT"])
    def source_update_endpoint(endpoint_id):
        data = request.get_json(silent=True) or {}
        result = source_registry_service.update_endpoint(endpoint_id, data)
        return jsonify(result)

    @bp.route("/api/sources/endpoints/<endpoint_id>", methods=["DELETE"])
    def source_delete_endpoint(endpoint_id):
        result = source_registry_service.delete_endpoint(endpoint_id)
        return jsonify(result)

    @bp.route("/api/sources/countries", methods=["POST"])
    def source_create_country():
        data = request.get_json(silent=True) or {}
        if not data.get("name") or not data.get("iso_code"):
            return jsonify({"error": "name and iso_code are required"}), 400
        result = source_registry_service.create_country(data)
        return jsonify(result), 201

    @bp.route("/api/sources/countries/<country_id>", methods=["PUT"])
    def source_update_country(country_id):
        data = request.get_json(silent=True) or {}
        result = source_registry_service.update_country(country_id, data)
        return jsonify(result)

    @bp.route("/api/sources/countries/<country_id>", methods=["DELETE"])
    def source_delete_country(country_id):
        result = source_registry_service.delete_country(country_id)
        return jsonify(result)

    @bp.route("/api/sources/authorities", methods=["POST"])
    def source_create_authority():
        data = request.get_json(silent=True) or {}
        if not data.get("country_id") or not data.get("name"):
            return jsonify({"error": "country_id and name are required"}), 400
        result = source_registry_service.create_authority(data)
        return jsonify(result), 201

    @bp.route("/api/sources/authorities/<authority_id>", methods=["PUT"])
    def source_update_authority(authority_id):
        data = request.get_json(silent=True) or {}
        result = source_registry_service.update_authority(authority_id, data)
        return jsonify(result)

    @bp.route("/api/sources/authorities/<authority_id>", methods=["DELETE"])
    def source_delete_authority(authority_id):
        result = source_registry_service.delete_authority(authority_id)
        return jsonify(result)

    @bp.route("/api/sources/verify", methods=["POST"])
    def source_verify_url():
        data = request.get_json(silent=True) or {}
        url = (data.get("url") or "").strip()
        if not url:
            return jsonify({"error": "url is required"}), 400
        return jsonify(source_registry_service.verify_url(url))

    @bp.route("/api/sources/classify", methods=["POST"])
    def source_classify_url():
        data = request.get_json(silent=True) or {}
        url = (data.get("url") or "").strip()
        classification = (data.get("classification") or "").strip()
        if not url or classification not in ("official", "unofficial_trusted", "not_official"):
            return jsonify({"error": "url and valid classification required"}), 400
        result = source_registry_service.classify_url(
            url, classification,
            notes=data.get("notes", ""),
            classified_by=data.get("classified_by", ""),
            matched_authority=data.get("matched_authority", ""),
            matched_country=data.get("matched_country", ""),
        )
        return jsonify(result)

    @bp.route("/api/sources/classifications")
    def source_classifications():
        return jsonify(source_registry_service.list_classifications())

    @bp.route("/api/sources/pdfs")
    def source_pdf_uploads():
        jobs = ingestion_job_service.list_recent_jobs(limit=100)
        pdfs = [j for j in jobs if (j.get("source_url") or "").startswith("pdf://")]
        return jsonify(pdfs)

    @bp.route("/api/flags")
    def api_flags():
        return jsonify(_flags())

    return bp
