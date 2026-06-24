"""Provenance API routes."""

from flask import Blueprint, jsonify


def create_provenance_blueprint(review_service, provenance_service=None):
    bp = Blueprint("provenance", __name__)

    @bp.route("/api/provenance/<country>")
    def get_provenance_all(country):
        if not provenance_service:
            return jsonify({"error": "provenance service not configured"}), 503
        rows = review_service.get_country_sections(country)
        if not rows:
            return jsonify({"error": f"No data for {country}"}), 404
        chains = []
        for r in rows:
            chain = provenance_service.get_chain(country, r["section"])
            if chain:
                chains.append(chain)
        return jsonify({"country": country, "chains": chains})

    @bp.route("/api/provenance/<country>/<section>")
    def get_provenance(country, section):
        if not provenance_service:
            return jsonify({"error": "provenance service not configured"}), 503
        chain = provenance_service.get_chain(country, section)
        if not chain:
            return jsonify({"error": f"No provenance found for {country}/{section}"}), 404
        return jsonify(chain)

    @bp.route("/api/provenance/<country>/<section>/history")
    def get_provenance_history(country, section):
        if not provenance_service:
            return jsonify({"error": "provenance service not configured"}), 503
        history = provenance_service.get_history(country, section)
        return jsonify({"country": country, "section": section, "history": history})

    return bp
