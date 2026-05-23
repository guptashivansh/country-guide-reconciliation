from app import create_app
from app.repositories.country_guide_repository import CountryGuideRepository
from app.repositories.ingestion_job_repository import IngestionJobRepository
from app.repositories.source_snapshot_repository import SourceSnapshotRepository
from app.utils.config import database_path, load_env_file
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
    repository = CountryGuideRepository(database_path())
    repository.seed_initial_country_guide()


if __name__ == "__main__":
    configure_logging()
    init_db()
    seed_initial_guide()
    logger.info(
        "Country Guide Reconciliation System starting",
        extra={"stage": "startup", "source_url": None},
    )
    app.run(debug=True, host="0.0.0.0", port=8080)
