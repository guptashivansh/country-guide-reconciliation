"""HTML page routes — dashboard, guide pages, compliance surfaces."""

from flask import Blueprint, abort, redirect, render_template, request

from app.api._helpers import make_config_helpers


def _fmt_date(iso):
    from datetime import datetime
    try:
        return datetime.fromisoformat(iso).strftime("%b %d, %Y")
    except Exception:
        return iso or "—"


def create_dashboard_blueprint(review_service, config_service=None):
    bp = Blueprint("dashboard", __name__)
    h = make_config_helpers(config_service)
    _flags = h["flags"]
    _flag = h["flag"]
    _section_groups = h["section_groups"]
    _sections_for_view = h["sections_for_view"]

    @bp.route("/")
    def home():
        countries = [
            {"name": r["country"], "flag": _flag(r["country"])}
            for r in review_service.list_countries_summary()
        ]
        return render_template("home.html", countries=countries)

    @bp.route("/ops")
    def index():
        return render_template("ops_dashboard_v2.html")

    @bp.route("/ops-legacy")
    def ops_legacy():
        return render_template("index.html")

    @bp.route("/guide")
    def guide_list():
        countries = [
            {"name": r["country"], "flag": _flag(r["country"]),
             "rule_count": r["rule_count"], "last_updated": _fmt_date(r["last_updated"])}
            for r in review_service.list_countries_summary()
        ]
        return render_template("guide_list.html", countries=countries, nav_active="guides")

    @bp.route("/guide/<country>")
    def guide_country(country):
        rows = review_service.get_country_sections(country)
        if not rows:
            abort(404)

        rules_by_section = {r["section"]: {"section": r["section"], "value": r["value"], "last_updated": _fmt_date(r["last_updated"])} for r in rows if (r["value"] or "").strip()}
        last_updated = _fmt_date(max(r["last_updated"] for r in rows))

        groups = []
        for g in _section_groups():
            group_rules = [rules_by_section[s] for s in g["sections"] if s in rules_by_section]
            if group_rules:
                groups.append({"id": g["id"], "label": g["label"], "rules": group_rules})

        notes = review_service.get_country_notes(country)

        return render_template(
            "guide_country.html",
            country=country,
            flag=_flag(country),
            rule_count=len(rows),
            last_updated=last_updated,
            groups=groups,
            notes=notes,
            nav_active="guides",
        )

    def _build_guide_context(country, allowed_group_ids):
        rows = review_service.get_country_sections(country)
        if not rows:
            return None
        rules_by_section = {r["section"]: {"section": r["section"], "value": r["value"], "last_updated": _fmt_date(r["last_updated"])} for r in rows if (r["value"] or "").strip()}
        last_updated = _fmt_date(max(r["last_updated"] for r in rows))
        groups = []
        for g in _section_groups():
            if g["id"] not in allowed_group_ids:
                continue
            group_rules = [rules_by_section[s] for s in g["sections"] if s in rules_by_section]
            if group_rules:
                groups.append({"id": g["id"], "label": g["label"], "rules": group_rules})
        return {
            "country": country,
            "flag": _flag(country),
            "rule_count": sum(len(g["rules"]) for g in groups),
            "last_updated": last_updated,
            "groups": groups,
        }

    _VIEW_LABELS = {"employee": "Employee", "client": "Client", "ops": "Ops"}

    @bp.route("/guide/<view>/<country>")
    def guide_view(view, country):
        view_label = _VIEW_LABELS.get(view)
        if not view_label:
            abort(404)
        allowed = _sections_for_view(view)
        ctx = _build_guide_context(country, allowed)
        if not ctx:
            abort(404)
        notes = review_service.get_country_notes(country) if view == "ops" else {"content": "", "updated_at": None}
        return render_template("guide_view.html", view=view, view_label=view_label, notes=notes, **ctx)

    @bp.route("/client")
    def client_overview():
        return render_template("client_overview.html")

    @bp.route("/employee/<country>")
    def employee_country(country):
        rows = review_service.get_country_sections(country)
        if not rows:
            abort(404)
        return render_template(
            "employee.html",
            country=country,
            flag=_flag(country),
        )

    # -- Compliance Intelligence surfaces --

    @bp.route("/compliance")
    def compliance_root():
        return redirect("/ops#sources")

    @bp.route("/compliance/intake")
    def compliance_intake_select():
        return redirect("/ops#sources")

    @bp.route("/intake/<country>")
    def compliance_intake_country(country):
        return render_template("compliance_intake.html", nav_active="intake", flags=_flags(), country=country, flag=_flag(country))

    @bp.route("/compliance/intake/pdf")
    def compliance_intake_pdf():
        return render_template(
            "compliance_intake_pdf.html",
            nav_active="intake",
            flags=_flags(),
            sections=[{"id": g["id"], "label": g["label"], "sections": g["sections"]} for g in _section_groups()],
        )

    @bp.route("/compliance/pipeline")
    def compliance_pipeline():
        return redirect("/ops#sources")

    @bp.route("/compliance/pipeline/<int:job_id>")
    def compliance_pipeline_job(job_id):
        return render_template("compliance_pipeline.html", nav_active="intake", focus_job=job_id)

    @bp.route("/compliance/dashboard")
    def compliance_dashboard():
        return render_template("compliance_base.html", nav_active="dashboard")

    @bp.route("/compliance/review")
    def compliance_review():
        return render_template("compliance_base.html", nav_active="review")

    @bp.route("/compliance/audit")
    def compliance_audit():
        return render_template("compliance_base.html", nav_active="audit")

    @bp.route("/compliance/settings")
    def compliance_settings():
        return render_template("compliance_base.html", nav_active="settings")

    return bp
