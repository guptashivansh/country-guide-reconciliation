from flask import Flask

from app.api.routes import create_api_blueprint
from app.extraction.content_chunker import ContentChunker
from app.extraction.groq_extraction_service import GroqExtractionService
from app.ingestion.html_ingestion_service import HtmlIngestionService
from app.ingestion.ingestion_job_service import IngestionJobService
from app.ingestion.source_snapshot_service import SourceSnapshotService
from app.llm.claude_provider import ClaudeProvider
from app.reconciliation.llm_reconciliation_service import LLMReconciliationEngine
from app.reconciliation.reconciliation_service import ReconciliationService
from app.repositories.country_guide_repository import CountryGuideRepository
from app.repositories.ingestion_job_repository import IngestionJobRepository
from app.repositories.source_snapshot_repository import SourceSnapshotRepository
from app.repositories.source_endpoint_repository import TrustedSourceEndpointRepository
from app.repositories.provenance_repository import ProvenanceRepository
from app.review.review_service import ReviewService
from app.services.source_registry_service import SourceRegistryService
from app.services.provenance_service import ProvenanceService
from app.services.temporal_rule_service import TemporalRuleService
from app.drift.detector import DriftDetector
from app.drift.repository import DriftRepository
from app.utils.config import anthropic_api_keys, database_path, extraction_chunk_size, groq_api_keys, load_env_file, official_sources_json_url, slack_webhook_url, sync_cron_schedule, parser_version  # noqa: E501
from app.utils.db import Database
from app.utils.logging_config import configure_logging


def build_services(db_path=None):
    load_env_file()
    configure_logging()

    db = Database(db_path or database_path())

    country_guide_repository = CountryGuideRepository(db)
    source_snapshot_repository = SourceSnapshotRepository(db)
    ingestion_job_repository = IngestionJobRepository(db)
    source_endpoint_repository = TrustedSourceEndpointRepository(db, json_url=official_sources_json_url())

    provenance_repository = ProvenanceRepository(db)
    provenance_service = ProvenanceService(provenance_repository, parser_version=parser_version())
    temporal_rule_service = TemporalRuleService(country_guide_repository)
    drift_repository = DriftRepository(db)
    drift_detector = DriftDetector(drift_repository)

    return {
        "country_guide_repository": country_guide_repository,
        "source_snapshot_repository": source_snapshot_repository,
        "ingestion_job_repository": ingestion_job_repository,
        "source_endpoint_repository": source_endpoint_repository,
        "provenance_repository": provenance_repository,
        "provenance_service": provenance_service,
        "temporal_rule_service": temporal_rule_service,
        "drift_detector": drift_detector,
        "review_service": ReviewService(country_guide_repository, provenance_service=provenance_service),
        "source_registry_service": SourceRegistryService(source_endpoint_repository),
        "ingestion_service": HtmlIngestionService(),
        "source_snapshot_service": SourceSnapshotService(source_snapshot_repository),
        "ingestion_job_service": IngestionJobService(ingestion_job_repository),
        "extraction_service": GroqExtractionService(
            groq_api_keys(),
            chunker=ContentChunker(max_chunk_size=extraction_chunk_size()),
        ),
        "reconciliation_service": ReconciliationService(
            country_guide_repository,
            reconciliation_engine=LLMReconciliationEngine(ClaudeProvider(anthropic_api_keys())),
        ),
    }


def create_app(db_path=None):
    services = build_services(db_path)
    services["country_guide_repository"].initialize_schema()
    services["source_snapshot_repository"].initialize_schema()
    services["ingestion_job_repository"].initialize_schema()
    services["provenance_repository"].initialize_schema()
    services["source_endpoint_repository"].initialize_schema()
    flask_app = Flask(__name__, template_folder="../templates")
    flask_app.config["services"] = services
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
    ))

    cron = sync_cron_schedule()
    if cron:
        from app.services.scheduler_service import start_scheduler
        start_scheduler(flask_app, services, cron, slack_webhook_url())

    return flask_app
