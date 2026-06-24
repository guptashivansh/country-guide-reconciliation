"""Configuration CRUD API routes."""

from flask import Blueprint, jsonify, request


def create_config_blueprint(config_service=None):
    bp = Blueprint("config", __name__)

    @bp.route("/api/config/sections")
    def config_sections():
        if not config_service:
            return jsonify({"error": "config service not available"}), 503
        return jsonify(config_service.get_section_groups())

    @bp.route("/api/config/sections", methods=["POST"])
    def config_create_section():
        if not config_service:
            return jsonify({"error": "config service not available"}), 503
        data = request.get_json(silent=True) or {}
        section_id = (data.get("id") or "").strip()
        display_name = (data.get("display_name") or "").strip()
        group_id = (data.get("group_id") or "").strip()
        if not section_id or not display_name or not group_id:
            return jsonify({"error": "id, display_name, and group_id are required"}), 400
        config_service.create_section(section_id, display_name, group_id,
                                      sort_order=data.get("sort_order", 0),
                                      changed_by=data.get("changed_by", "api"))
        return jsonify({"success": True, "id": section_id}), 201

    @bp.route("/api/config/sections/<section_id>", methods=["PUT"])
    def config_update_section(section_id):
        if not config_service:
            return jsonify({"error": "config service not available"}), 503
        data = request.get_json(silent=True) or {}
        result = config_service.update_section(
            section_id,
            changed_by=data.get("changed_by", "api"),
            display_name=data.get("display_name"),
            group_id=data.get("group_id"),
            sort_order=data.get("sort_order"),
            is_active=data.get("is_active"),
        )
        if not result:
            return jsonify({"error": "section not found"}), 404
        return jsonify({"success": True})

    @bp.route("/api/config/section-groups", methods=["POST"])
    def config_create_section_group():
        if not config_service:
            return jsonify({"error": "config service not available"}), 503
        data = request.get_json(silent=True) or {}
        group_id = (data.get("id") or "").strip()
        label = (data.get("label") or "").strip()
        if not group_id or not label:
            return jsonify({"error": "id and label are required"}), 400
        config_service.create_section_group(group_id, label,
                                            sort_order=data.get("sort_order", 0),
                                            changed_by=data.get("changed_by", "api"))
        return jsonify({"success": True, "id": group_id}), 201

    @bp.route("/api/config/section-groups/<group_id>", methods=["PUT"])
    def config_update_section_group(group_id):
        if not config_service:
            return jsonify({"error": "config service not available"}), 503
        data = request.get_json(silent=True) or {}
        result = config_service.update_section_group(
            group_id,
            changed_by=data.get("changed_by", "api"),
            label=data.get("label"),
            sort_order=data.get("sort_order"),
            is_active=data.get("is_active"),
        )
        if not result:
            return jsonify({"error": "section group not found"}), 404
        return jsonify({"success": True})

    @bp.route("/api/config/view-roles/<view_name>", methods=["GET"])
    def config_get_view_roles(view_name):
        if not config_service:
            return jsonify({"error": "config service not available"}), 503
        groups = config_service.get_sections_for_view(view_name)
        return jsonify({"view_name": view_name, "group_ids": sorted(groups)})

    @bp.route("/api/config/view-roles/<view_name>", methods=["PUT"])
    def config_set_view_roles(view_name):
        if not config_service:
            return jsonify({"error": "config service not available"}), 503
        data = request.get_json(silent=True) or {}
        group_ids = data.get("group_ids", [])
        if not isinstance(group_ids, list):
            return jsonify({"error": "group_ids must be a list"}), 400
        config_service.set_view_role_sections(view_name, group_ids, changed_by=data.get("changed_by", "api"))
        return jsonify({"success": True})

    @bp.route("/api/config/rubrics")
    def config_list_rubrics():
        if not config_service:
            return jsonify({"error": "config service not available"}), 503
        return jsonify(config_service.list_classification_rubrics())

    @bp.route("/api/config/rubrics/<country>", methods=["GET"])
    def config_get_rubric(country):
        if not config_service:
            return jsonify({"error": "config service not available"}), 503
        rubric = config_service.get_classification_rubric(country=country)
        return jsonify({"country": country, "rubric_text": rubric})

    @bp.route("/api/config/rubrics", methods=["PUT"])
    def config_set_global_rubric():
        if not config_service:
            return jsonify({"error": "config service not available"}), 503
        data = request.get_json(silent=True) or {}
        rubric_text = (data.get("rubric_text") or "").strip()
        if not rubric_text:
            return jsonify({"error": "rubric_text is required"}), 400
        config_service.set_classification_rubric(rubric_text, country=None, changed_by=data.get("changed_by", "api"))
        return jsonify({"success": True})

    @bp.route("/api/config/rubrics/<country>", methods=["PUT"])
    def config_set_country_rubric(country):
        if not config_service:
            return jsonify({"error": "config service not available"}), 503
        data = request.get_json(silent=True) or {}
        rubric_text = (data.get("rubric_text") or "").strip()
        if not rubric_text:
            return jsonify({"error": "rubric_text is required"}), 400
        config_service.set_classification_rubric(rubric_text, country=country, changed_by=data.get("changed_by", "api"))
        return jsonify({"success": True})

    @bp.route("/api/config/rubrics/<country>", methods=["DELETE"])
    def config_delete_country_rubric(country):
        if not config_service:
            return jsonify({"error": "config service not available"}), 503
        data = request.get_json(silent=True) or {}
        config_service.delete_classification_rubric(country, changed_by=data.get("changed_by", "api"))
        return jsonify({"success": True})

    @bp.route("/api/config/<namespace>/<key>", methods=["GET"])
    def config_get_entry(namespace, key):
        if not config_service:
            return jsonify({"error": "config service not available"}), 503
        value = config_service.get_config(namespace, key)
        if value is None:
            return jsonify({"error": "config entry not found"}), 404
        return jsonify({"namespace": namespace, "key": key, "value": value})

    @bp.route("/api/config/<namespace>/<key>", methods=["PUT"])
    def config_set_entry(namespace, key):
        if not config_service:
            return jsonify({"error": "config service not available"}), 503
        data = request.get_json(silent=True) or {}
        if "value" not in data:
            return jsonify({"error": "value is required"}), 400
        config_service.set_config(namespace, key, data["value"],
                                  changed_by=data.get("changed_by", "api"),
                                  reason=data.get("reason"))
        return jsonify({"success": True})

    @bp.route("/api/config/<namespace>", methods=["GET"])
    def config_get_namespace(namespace):
        if not config_service:
            return jsonify({"error": "config service not available"}), 503
        return jsonify(config_service.get_namespace(namespace))

    @bp.route("/api/config/audit")
    def config_audit_log():
        if not config_service:
            return jsonify({"error": "config service not available"}), 503
        namespace = request.args.get("namespace")
        key = request.args.get("key")
        limit = int(request.args.get("limit", 50))
        return jsonify(config_service.get_config_audit_log(namespace, key, limit))

    return bp
