"""Coordinator module — assembles all sub-blueprints into the parent API blueprint.

The public interface (``create_api_blueprint`` and ``warm_drift_cache``) is
unchanged so that ``app/__init__.py`` continues to work without modifications.
"""

import atexit
import time
from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint

from app.api.routes_config import create_config_blueprint
from app.api.routes_dashboard import create_dashboard_blueprint
from app.api.routes_drift import create_drift_blueprint
from app.api.routes_guide import create_guide_blueprint
from app.api.routes_pipeline import create_pipeline_blueprint
from app.api.routes_provenance import create_provenance_blueprint
from app.api.routes_review import create_review_blueprint
from app.api.routes_sources import create_sources_blueprint

# ── Shared thread pool (used by warm_drift_cache and routes_pipeline) ─────────

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pipeline")
atexit.register(lambda: _executor.shutdown(wait=False))

# ── Shared drift cache (used by routes_drift and warm_drift_cache) ────────────

_drift_cache = {"data": None, "expires": 0}
_DRIFT_CACHE_TTL = 60


def warm_drift_cache(drift_detector):
    """Pre-warm the drift cache in a background thread."""

    def _warm():
        reports = drift_detector.detect_all()
        result = [r.to_dict() for r in reports]
        _drift_cache["data"] = result
        _drift_cache["expires"] = time.monotonic() + _DRIFT_CACHE_TTL

    _executor.submit(_warm)


# ── Blueprint assembly ────────────────────────────────────────────────────────

def create_api_blueprint(
    review_service,
    source_registry_service,
    ingestion_service,
    source_snapshot_service,
    ingestion_job_service,
    extraction_service,
    reconciliation_service,
    provenance_service=None,
    temporal_rule_service=None,
    drift_detector=None,
    config_service=None,
    pdf_ingestion_service=None,
    limiter=None,
):
    parent = Blueprint("country_guide_routes", __name__)

    parent.register_blueprint(create_dashboard_blueprint(
        review_service=review_service,
        config_service=config_service,
    ))

    parent.register_blueprint(create_review_blueprint(
        review_service=review_service,
        limiter=limiter,
    ))

    parent.register_blueprint(create_guide_blueprint(
        review_service=review_service,
        temporal_rule_service=temporal_rule_service,
        config_service=config_service,
        limiter=limiter,
    ))

    parent.register_blueprint(create_drift_blueprint(
        drift_detector=drift_detector,
        drift_cache=_drift_cache,
        drift_cache_ttl=_DRIFT_CACHE_TTL,
        config_service=config_service,
    ))

    parent.register_blueprint(create_sources_blueprint(
        source_registry_service=source_registry_service,
        ingestion_job_service=ingestion_job_service,
        config_service=config_service,
    ))

    parent.register_blueprint(create_pipeline_blueprint(
        review_service=review_service,
        source_registry_service=source_registry_service,
        ingestion_service=ingestion_service,
        source_snapshot_service=source_snapshot_service,
        ingestion_job_service=ingestion_job_service,
        extraction_service=extraction_service,
        reconciliation_service=reconciliation_service,
        pdf_ingestion_service=pdf_ingestion_service,
        executor=_executor,
        limiter=limiter,
    ))

    parent.register_blueprint(create_config_blueprint(
        config_service=config_service,
    ))

    parent.register_blueprint(create_provenance_blueprint(
        review_service=review_service,
        provenance_service=provenance_service,
    ))

    return parent
