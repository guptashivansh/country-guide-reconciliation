from app import create_app
from app.repositories.country_guide_repository import CountryGuideRepository
from app.repositories.ingestion_job_repository import IngestionJobRepository
from app.repositories.provenance_repository import ProvenanceRepository
from app.repositories.source_snapshot_repository import SourceSnapshotRepository
from app.services.provenance_service import ProvenanceService
from app.utils.config import database_path, load_env_file, parser_version
from app.utils.logging_config import configure_logging

import logging


logger = logging.getLogger(__name__)


load_env_file()
app = create_app()


def init_db():
    db_path = database_path()
    CountryGuideRepository(db_path).initialize_schema()
    SourceSnapshotRepository(db_path).initialize_schema()
    IngestionJobRepository(db_path).initialize_schema()


def seed_initial_guide():
    db_path = database_path()
    repository = CountryGuideRepository(db_path)
    provenance_service = ProvenanceService(
        ProvenanceRepository(db_path),
        parser_version=parser_version(),
    )
    repository.seed_initial_country_guide(provenance_service=provenance_service)


if __name__ == "__main__":
    configure_logging()
    init_db()
    seed_initial_guide()
    logger.info(
        "Country Guide Reconciliation System starting",
        extra={"stage": "startup", "source_url": None},
    )
    app.run(debug=True, host="0.0.0.0", port=8080)
