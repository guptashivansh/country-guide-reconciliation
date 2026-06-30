from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from app.api.routes import create_api_blueprint, warm_drift_cache
from app.extraction.content_chunker import ContentChunker
from app.extraction.groq_extraction_service import GroqExtractionService
from app.extraction.ollama_extraction_service import OllamaExtractionService
from app.ingestion.html_ingestion_service import HtmlIngestionService
from app.ingestion.pdf_ingestion_service import PdfIngestionService
from app.ingestion.ingestion_job_service import IngestionJobService
from app.ingestion.source_snapshot_service import SourceSnapshotService
from app.llm import create_reconciliation_provider
from app.reconciliation.llm_reconciliation_service import LLMReconciliationEngine
from app.reconciliation.reconciliation_service import ReconciliationService
from app.repositories.country_guide_repository import CountryGuideRepository
from app.repositories.config_repository import ConfigRepository
from app.repositories.ingestion_job_repository import IngestionJobRepository
from app.repositories.source_snapshot_repository import SourceSnapshotRepository
from app.repositories.source_endpoint_repository import TrustedSourceEndpointRepository
from app.repositories.provenance_repository import ProvenanceRepository
from app.review.review_service import ReviewService
from app.services.config_service import ConfigService
from app.services.source_registry_service import SourceRegistryService
from app.services.provenance_service import ProvenanceService
from app.services.temporal_rule_service import TemporalRuleService
from app.drift.detector import DriftDetector
from app.drift.repository import DriftRepository
from app.utils.config import anthropic_api_keys, claude_model, database_path, extraction_chunk_size, gemini_api_keys, gemini_model, groq_api_keys, groq_model, load_env_file, official_sources_json_url, ollama_base_url, ollama_model, slack_webhook_url, sync_cron_schedule, parser_version  # noqa: E501
from app.utils.db import Database
from app.utils.logging_config import configure_logging


def _create_extraction_service():
    import logging
    import os
    _logger = logging.getLogger(__name__)
    chunker = ContentChunker(max_chunk_size=extraction_chunk_size())
    force_ollama = os.environ.get("EXTRACTION_PROVIDER", "").lower() == "ollama"
    keys = groq_api_keys()
    if keys and not force_ollama:
        _logger.info("Using Groq for extraction")
        return GroqExtractionService(keys, chunker=chunker, model=groq_model())
    extraction_model = os.environ.get("OLLAMA_EXTRACTION_MODEL", "") or ollama_model()
    ollama_svc = OllamaExtractionService(
        model=extraction_model, base_url=ollama_base_url(), chunker=chunker,
    )
    try:
        import requests
        resp = requests.get(f"{ollama_base_url()}/api/tags", timeout=2)
        if resp.ok:
            _logger.info("Using Ollama for extraction (model=%s)", extraction_model)
            return ollama_svc
    except Exception:
        pass
    _logger.warning("No Groq keys and Ollama unreachable — extraction will fail at runtime")
    return GroqExtractionService([], chunker=chunker, model=groq_model())


def build_services(db_path=None):
    load_env_file()
    configure_logging()

    db = Database(db_path)

    country_guide_repository = CountryGuideRepository(db)
    source_snapshot_repository = SourceSnapshotRepository(db)
    ingestion_job_repository = IngestionJobRepository(db)
    source_endpoint_repository = TrustedSourceEndpointRepository(db, json_url=official_sources_json_url())

    provenance_repository = ProvenanceRepository(db)
    provenance_service = ProvenanceService(provenance_repository, parser_version=parser_version())
    temporal_rule_service = TemporalRuleService(country_guide_repository)
    drift_repository = DriftRepository(db)

    config_repository = ConfigRepository(db)
    config_service = ConfigService(config_repository)

    drift_detector = DriftDetector(drift_repository, config_service=config_service)

    reconciliation_provider = create_reconciliation_provider(
        api_keys_by_name={
            "anthropic": anthropic_api_keys(),
            "gemini": gemini_api_keys(),
            "groq": groq_api_keys(),
        },
        models_by_name={
            "anthropic": claude_model(),
            "gemini": gemini_model(),
            "groq": groq_model(),
            "ollama": ollama_model(),
        },
        ollama_base_url=ollama_base_url(),
    )
    reconciliation_engine = LLMReconciliationEngine(
        reconciliation_provider,
        config_service=config_service,
    )

    return {
        "country_guide_repository": country_guide_repository,
        "source_snapshot_repository": source_snapshot_repository,
        "ingestion_job_repository": ingestion_job_repository,
        "source_endpoint_repository": source_endpoint_repository,
        "provenance_repository": provenance_repository,
        "provenance_service": provenance_service,
        "temporal_rule_service": temporal_rule_service,
        "drift_detector": drift_detector,
        "config_repository": config_repository,
        "config_service": config_service,
        "review_service": ReviewService(country_guide_repository, provenance_service=provenance_service),
        "source_registry_service": SourceRegistryService(source_endpoint_repository),
        "ingestion_service": HtmlIngestionService(),
        "pdf_ingestion_service": PdfIngestionService(),
        "source_snapshot_service": SourceSnapshotService(source_snapshot_repository),
        "ingestion_job_service": IngestionJobService(ingestion_job_repository),
        "extraction_service": _create_extraction_service(),
        "reconciliation_service": ReconciliationService(
            country_guide_repository,
            reconciliation_engine=reconciliation_engine,
        ),
    }


def create_app(db_path=None):
    services = build_services(db_path)
    services["country_guide_repository"].initialize_schema()
    services["source_snapshot_repository"].initialize_schema()
    services["ingestion_job_repository"].initialize_schema()
    services["provenance_repository"].initialize_schema()
    services["source_endpoint_repository"].initialize_schema()
    services["config_repository"].initialize_schema()
    flask_app = Flask(__name__, template_folder="../templates", static_folder="../static")
    flask_app.config["services"] = services

    limiter = Limiter(
        get_remote_address,
        app=flask_app,
        default_limits=["200 per minute"],
        storage_uri="memory://",
    )

    flask_app.register_blueprint(create_api_blueprint(
        review_service=services["review_service"],
        source_registry_service=services["source_registry_service"],
        ingestion_service=services["ingestion_service"],
        source_snapshot_service=services["source_snapshot_service"],
        ingestion_job_service=services["ingestion_job_service"],
        extraction_service=services["extraction_service"],
        reconciliation_service=services["reconciliation_service"],
        provenance_service=services["provenance_service"],
        temporal_rule_service=services["temporal_rule_service"],
        drift_detector=services["drift_detector"],
        config_service=services["config_service"],
        pdf_ingestion_service=services["pdf_ingestion_service"],
        limiter=limiter,
    ))

    cron = sync_cron_schedule()
    if cron:
        from app.services.scheduler_service import start_scheduler
        start_scheduler(flask_app, services, cron, slack_webhook_url())

    warm_drift_cache(services["drift_detector"])

    _auto_seed_if_empty(services)

    return flask_app


def _auto_seed_if_empty(services):
    """Run Notion import in background on first boot when country_guide is empty."""
    import threading

    repo = services["country_guide_repository"]
    if repo.list_countries_summary():
        return

    def _seed():
        import logging
        from app.ingestion.notion_ingestion_service import NotionIngestionService
        from app.services.provenance_service import ProvenanceService
        from app.utils.config import parser_version
        import re

        logger = logging.getLogger(__name__)
        logger.info("Auto-seeding country_guide from Notion (background)...")

        NOTION_PAGE_ID = "7ed6a2f53972448db2cb107a8d20b661"
        NOTION_SOURCE_URL = "https://skuad.notion.site/Skuad-Country-Product-Guides-7ed6a2f53972448db2cb107a8d20b661"
        COUNTRY_ALIASES = {"united arab emirates": "UAE"}

        try:
            from notion_import import FIELD_TO_SECTION, _parse_sections, _canonical_country

            notion_service = NotionIngestionService(page_id=NOTION_PAGE_ID)
            country_texts = notion_service.fetch_all_employment_guides()

            provenance_service = ProvenanceService(
                services["provenance_repository"],
                parser_version=parser_version(),
            )

            total = 0
            for raw_country, content in country_texts.items():
                country = _canonical_country(raw_country)
                sections = _parse_sections(content)
                for section, value in sections.items():
                    repo.upsert_guide_entry(
                        country=country, section=section,
                        value=value, source_url=NOTION_SOURCE_URL,
                    )
                    provenance_service.record_seed(country, section, value, NOTION_SOURCE_URL)
                    total += 1
                logger.info("Seeded %s (%d sections)", country, len(sections))

            logger.info("Auto-seed complete: %d rules across %d countries", total, len(country_texts))
        except Exception:
            logger.exception("Auto-seed from Notion failed")

    threading.Thread(target=_seed, daemon=True).start()
