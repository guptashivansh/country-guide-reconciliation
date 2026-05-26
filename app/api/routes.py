import logging
from datetime import datetime

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for
from app.services.sync_service import run_sync, run_single_job
from app.services.slack_service import send_sync_alert
from app.utils.config import slack_webhook_url


logger = logging.getLogger(__name__)

FLAGS = {
    "Argentina": "🇦🇷", "Australia": "🇦🇺", "Austria": "🇦🇹",
    "Azerbaijan": "🇦🇿", "Bahrain": "🇧🇭", "Bangladesh": "🇧🇩",
    "Belgium": "🇧🇪", "Belize": "🇧🇿", "Bolivia": "🇧🇴",
    "Bosnia And Herzegovina": "🇧🇦", "Botswana": "🇧🇼", "Brazil": "🇧🇷",
    "Bulgaria": "🇧🇬", "Cameroon": "🇨🇲", "Chile": "🇨🇱",
    "China": "🇨🇳", "Colombia": "🇨🇴", "Congo (Republic of Congo)": "🇨🇬",
    "Costa Rica": "🇨🇷", "Croatia": "🇭🇷", "Cyprus": "🇨🇾",
    "Czech Republic": "🇨🇿", "Denmark": "🇩🇰", "Dominican Republic": "🇩🇴",
    "Egypt": "🇪🇬", "Estonia": "🇪🇪", "France": "🇫🇷",
    "Georgia": "🇬🇪", "Germany": "🇩🇪", "Ghana": "🇬🇭",
    "Greece": "🇬🇷", "Guatemala": "🇬🇹", "Hong Kong": "🇭🇰",
    "Hungary": "🇭🇺", "India": "🇮🇳", "Indonesia": "🇮🇩",
    "Israel": "🇮🇱", "Jamaica": "🇯🇲", "Japan": "🇯🇵",
    "Jordan": "🇯🇴", "Kenya": "🇰🇪", "Kuwait": "🇰🇼",
    "Lebanon": "🇱🇧", "Lithuania": "🇱🇹", "Luxembourg": "🇱🇺",
    "Madagascar": "🇲🇬", "Malawi": "🇲🇼", "Malaysia": "🇲🇾",
    "Malta": "🇲🇹", "Mauritius": "🇲🇺", "Mexico": "🇲🇽",
    "Morocco": "🇲🇦", "Nepal": "🇳🇵", "Netherlands": "🇳🇱",
    "New Zealand": "🇳🇿", "Nicaragua": "🇳🇮", "Nigeria": "🇳🇬",
    "Norway": "🇳🇴", "Oman": "🇴🇲", "Pakistan": "🇵🇰",
    "Panama": "🇵🇦", "Paraguay": "🇵🇾", "Peru": "🇵🇪",
    "Philippines": "🇵🇭", "Poland": "🇵🇱", "Portugal": "🇵🇹",
    "Puerto Rico": "🇵🇷", "Qatar": "🇶🇦", "Romania": "🇷🇴",
    "Rwanda": "🇷🇼", "Saudi Arabia": "🇸🇦", "Serbia": "🇷🇸",
    "Singapore": "🇸🇬", "Slovakia": "🇸🇰", "South Africa": "🇿🇦",
    "South Korea": "🇰🇷", "Spain": "🇪🇸", "Sri Lanka": "🇱🇰",
    "Switzerland": "🇨🇭", "Taiwan": "🇹🇼", "Thailand": "🇹🇭",
    "Turkey": "🇹🇷", "UAE": "🇦🇪", "Uganda": "🇺🇬",
    "Ukraine": "🇺🇦", "United Kingdom": "🇬🇧", "Vietnam": "🇻🇳",
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
    def home():
        countries = [
            {"name": r["country"], "flag": FLAGS.get(r["country"], "🌐")}
            for r in review_service.list_countries_summary()
        ]
        return render_template("home.html", countries=countries)

    @routes.route("/ops")
    def index():
        return render_template("ops_dashboard_v2.html")

    @routes.route("/ops-legacy")
    def ops_legacy():
        return render_template("index.html")

    @routes.route("/guide")
    def guide_list():
        countries = [
            {"name": r["country"], "flag": FLAGS.get(r["country"], "🌐"),
             "rule_count": r["rule_count"], "last_updated": _fmt_date(r["last_updated"])}
            for r in review_service.list_countries_summary()
        ]
        return render_template("guide_list.html", countries=countries, nav_active="guides")

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

        notes = review_service.get_country_notes(country)

        return render_template(
            "guide_country.html",
            country=country,
            flag=FLAGS.get(country, "🌐"),
            rule_count=len(rows),
            last_updated=last_updated,
            groups=groups,
            notes=notes,
            nav_active="guides",
        )

    @routes.route("/api/notes/<country>", methods=["GET"])
    def get_country_notes(country):
        notes = review_service.get_country_notes(country)
        return jsonify(notes)

    @routes.route("/api/notes/<country>", methods=["PUT"])
    def save_country_notes(country):
        data = request.get_json(silent=True) or {}
        content = data.get("content", "")
        result = review_service.save_country_notes(country, content)
        return jsonify({"success": True, **result})

    @routes.route("/api/guide/<country>/<section>", methods=["PUT"])
    def edit_rule(country, section):
        data = request.get_json(silent=True) or {}
        new_value = data.get("value", "").strip()
        if not new_value:
            return jsonify({"success": False, "message": "value is required"}), 400
        result = review_service.manual_edit_rule(country, section, new_value)
        if result is None:
            return jsonify({"success": True, "message": "No change"})
        return jsonify({"success": True, **result})

    @routes.route("/api/guide")
    def get_guide():
        return jsonify(review_service.list_country_guide_entries())

    @routes.route("/api/queue")
    def get_queue():
        return jsonify(review_service.list_pending_review_items())

    @routes.route("/api/audit")
    def get_audit():
        entries = review_service.list_audit_entries()
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

    @routes.route("/api/ingestion-jobs")
    def get_ingestion_jobs():
        return jsonify(ingestion_job_service.list_recent_jobs())

    @routes.route("/api/retry-job/<int:job_id>", methods=["POST"])
    def retry_job(job_id):
        retry_result = ingestion_job_service.retry_job(job_id)
        if not retry_result:
            return jsonify({"success": False, "message": "Job not found"}), 404

        new_job_id = retry_result["job_id"]
        source_url = retry_result["source_url"]
        country = retry_result.get("country") or ""

        endpoint = None
        for ep in source_registry_service.list_trusted_source_endpoints():
            if ep.url == source_url:
                endpoint = ep
                break

        services = {
            "ingestion_service": ingestion_service,
            "source_snapshot_service": source_snapshot_service,
            "ingestion_job_service": ingestion_job_service,
            "extraction_service": extraction_service,
            "reconciliation_service": reconciliation_service,
        }
        pipeline_result = run_single_job(
            services, new_job_id, source_url,
            country=endpoint.country if endpoint else country,
            sections=endpoint.sections if endpoint else None,
        )

        if pipeline_result["success"]:
            changes = pipeline_result.get("changes_queued", 0)
            return jsonify({
                "success": True,
                "job_id": new_job_id,
                "message": f"Job #{job_id} retried as #{new_job_id} — {changes} change(s) queued",
            })
        return jsonify({
            "success": True,
            "job_id": new_job_id,
            "message": f"Job #{job_id} retried as #{new_job_id} — pipeline failed: {pipeline_result.get('failure_reason', 'unknown')}",
        })

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

        registry = source_registry_service.get_registry_stats()

        return jsonify({
            "sources_monitored": registry["endpoints"],
            "pending_reviews": len(pending),
            "critical_changes": len(critical),
            "avg_confidence": avg_conf,
            "crawl_failures": crawl_failures,
            "last_successful_sync": last_ok_ts,
            "trusted_source_count": registry["countries"],
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

    @routes.route("/api/provenance/<country>")
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

    @routes.route("/client")
    def client_overview():
        return render_template("client_overview.html")

    @routes.route("/employee/<country>")
    def employee_country(country):
        rows = review_service.get_country_sections(country)
        if not rows:
            abort(404)
        return render_template(
            "employee.html",
            country=country,
            flag=FLAGS.get(country, "🌐"),
        )

    EMPLOYEE_SECTIONS = {"leave", "hours", "compensation", "benefits"}
    CLIENT_SECTIONS = {"leave", "hours", "compensation", "benefits", "employment", "immigration"}
    OPS_SECTIONS = {"leave", "hours", "compensation", "benefits", "employment", "immigration", "safety"}

    def _build_guide_context(country, allowed_group_ids):
        rows = review_service.get_country_sections(country)
        if not rows:
            return None
        rules_by_section = {r["section"]: {"section": r["section"], "value": r["value"], "last_updated": _fmt_date(r["last_updated"])} for r in rows}
        last_updated = _fmt_date(max(r["last_updated"] for r in rows))
        groups = []
        for g in SECTION_GROUPS:
            if g["id"] not in allowed_group_ids:
                continue
            group_rules = [rules_by_section[s] for s in g["sections"] if s in rules_by_section]
            if group_rules:
                groups.append({"id": g["id"], "label": g["label"], "rules": group_rules})
        return {
            "country": country,
            "flag": FLAGS.get(country, "🌐"),
            "rule_count": sum(len(g["rules"]) for g in groups),
            "last_updated": last_updated,
            "groups": groups,
        }

    VIEW_CONFIG = {
        "employee": {"sections": EMPLOYEE_SECTIONS, "label": "Employee"},
        "client":   {"sections": CLIENT_SECTIONS,   "label": "Client"},
        "ops":      {"sections": OPS_SECTIONS,       "label": "Ops"},
    }

    @routes.route("/guide/<view>/<country>")
    def guide_view(view, country):
        cfg = VIEW_CONFIG.get(view)
        if not cfg:
            abort(404)
        ctx = _build_guide_context(country, cfg["sections"])
        if not ctx:
            abort(404)
        notes = review_service.get_country_notes(country) if view == "ops" else {"content": "", "updated_at": None}
        return render_template("guide_view.html", view=view, view_label=cfg["label"], notes=notes, **ctx)

    @routes.route("/api/employee/guide/<country>")
    def api_employee_guide(country):
        rows = review_service.get_country_sections(country)
        if not rows:
            return jsonify({"error": "Country not found"}), 404
        rules_by_section = {r["section"]: r for r in rows}
        groups = []
        for g in SECTION_GROUPS:
            group_rules = []
            for s in g["sections"]:
                r = rules_by_section.get(s)
                if r:
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
            "flag": FLAGS.get(country, "🌐"),
            "last_updated": _fmt_date(max(r["last_updated"] for r in rows)),
            "rule_count": len(rows),
            "groups": groups,
        })

    @routes.route("/api/employee/ask", methods=["POST"])
    def api_employee_ask():
        data = request.get_json(silent=True) or {}
        prompt = data.get("prompt", "").strip()
        if not prompt:
            return jsonify({"error": "No prompt provided"}), 400
        try:
            from groq import Groq
            from app.utils.config import groq_api_keys
            keys = groq_api_keys()
            if not keys:
                return jsonify({"error": "GROQ_API_KEY is not set. Get a free key at console.groq.com then run: export GROQ_API_KEY=your_key"}), 501
            client = Groq(api_key=keys[0])
            chat = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            return jsonify({"reply": chat.choices[0].message.content})
        except ImportError:
            return jsonify({"error": "groq SDK not installed. Run: pip install groq"}), 501
        except Exception as exc:
            logger.exception("Ask Abdul Kalam AI error")
            return jsonify({"error": str(exc)}), 500

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

    # ── Compliance Intelligence surfaces ──

    @routes.route("/compliance")
    def compliance_root():
        return redirect(url_for("country_guide_routes.compliance_intake_select"))

    @routes.route("/compliance/intake")
    def compliance_intake_select():
        return render_template("compliance_intake_select.html", nav_active="intake", flags=FLAGS)

    @routes.route("/intake/<country>")
    def compliance_intake_country(country):
        return render_template("compliance_intake.html", nav_active="intake", flags=FLAGS, country=country, flag=FLAGS.get(country, "🌐"))

    @routes.route("/compliance/intake/pdf")
    def compliance_intake_pdf():
        return render_template(
            "compliance_intake_pdf.html",
            nav_active="intake",
            flags=FLAGS,
            sections=[{"id": g["id"], "label": g["label"], "sections": g["sections"]} for g in SECTION_GROUPS],
        )

    @routes.route("/compliance/pipeline")
    def compliance_pipeline():
        return render_template("compliance_pipeline.html", nav_active="intake")

    @routes.route("/compliance/pipeline/<int:job_id>")
    def compliance_pipeline_job(job_id):
        return render_template("compliance_pipeline.html", nav_active="intake", focus_job=job_id)

    @routes.route("/api/intake/pdf", methods=["POST"])
    def api_intake_pdf():
        jurisdiction = request.form.get("jurisdiction", "").strip()
        publisher = request.form.get("publisher", "").strip()
        doc_title = request.form.get("doc_title", "").strip()
        authority = request.form.get("authority", "").strip()
        effective_date = request.form.get("effective_date", "").strip()
        file_hash = request.form.get("file_hash", "").strip()

        source_url = f"pdf://{file_hash[:12] if file_hash else 'upload'}#{doc_title or 'untitled'}"
        job_id = ingestion_job_service.create_job(source_url, country=jurisdiction or None)

        logger.info(
            "PDF intake registered",
            extra={
                "stage": "pdf_intake",
                "ingestion_job_id": job_id,
                "jurisdiction": jurisdiction,
                "publisher": publisher,
                "authority": authority,
                "effective_date": effective_date,
            },
        )

        return jsonify({
            "success": True,
            "job_id": job_id,
            "message": f"Document registered as job #{job_id}",
        })

    @routes.route("/compliance/dashboard")
    def compliance_dashboard():
        return render_template("compliance_base.html", nav_active="dashboard")

    @routes.route("/compliance/review")
    def compliance_review():
        return render_template("compliance_base.html", nav_active="review")

    @routes.route("/compliance/audit")
    def compliance_audit():
        return render_template("compliance_base.html", nav_active="audit")

    @routes.route("/compliance/settings")
    def compliance_settings():
        return render_template("compliance_base.html", nav_active="settings")

    @routes.route("/api/sources/stats")
    def source_registry_stats():
        return jsonify(source_registry_service.get_registry_stats())

    @routes.route("/api/sources/countries")
    def source_registry_countries():
        return jsonify(source_registry_service.list_countries())

    @routes.route("/api/sources/authorities")
    def source_registry_authorities():
        country_id = request.args.get("country_id")
        return jsonify(source_registry_service.list_authorities(country_id))

    @routes.route("/api/sources/endpoints")
    def source_registry_endpoints():
        country = request.args.get("country")
        if country:
            eps = source_registry_service.list_endpoints_for_country(country)
        else:
            eps = source_registry_service.list_trusted_source_endpoints()
        return jsonify([{
            "endpoint_id": ep.endpoint_id,
            "country": ep.country,
            "iso_code": ep.iso_code,
            "authority": ep.authority,
            "authority_type": ep.authority_type,
            "url": ep.url,
            "authority_url": ep.authority_url,
            "sections": list(ep.sections),
            "source_type": ep.source_type,
            "extraction_strategy": ep.extraction_strategy,
            "crawl_frequency": ep.crawl_frequency,
            "escalation_required": ep.escalation_required,
            "supports_replay": ep.supports_replay,
            "owner_team": ep.owner_team,
            "notes": ep.notes,
            "status": ep.status,
        } for ep in eps])

    @routes.route("/api/sources/verify", methods=["POST"])
    def source_verify_url():
        data = request.get_json(silent=True) or {}
        url = (data.get("url") or "").strip()
        if not url:
            return jsonify({"error": "url is required"}), 400
        return jsonify(source_registry_service.verify_url(url))

    @routes.route("/api/sources/classify", methods=["POST"])
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

    @routes.route("/api/sources/classifications")
    def source_classifications():
        return jsonify(source_registry_service.list_classifications())

    @routes.route("/api/sources/pdfs")
    def source_pdf_uploads():
        jobs = ingestion_job_service.list_recent_jobs(limit=100)
        pdfs = [j for j in jobs if (j.get("source_url") or "").startswith("pdf://")]
        return jsonify(pdfs)

    return routes
