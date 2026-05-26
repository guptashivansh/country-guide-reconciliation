import logging


logger = logging.getLogger(__name__)


class IngestionJobService:
    def __init__(self, ingestion_job_repository):
        self.ingestion_job_repository = ingestion_job_repository

    def create_job(self, source_url, country=None):
        job_id = self.ingestion_job_repository.create_job(source_url, country=country)
        logger.info(
            "Ingestion job queued",
            extra={"stage": "queued", "source_url": source_url, "ingestion_job_id": job_id, "country": country},
        )
        return job_id

    def get_job(self, job_id):
        return self.ingestion_job_repository.get_job(job_id)

    def retry_job(self, job_id):
        original = self.ingestion_job_repository.get_job(job_id)
        if not original:
            return None
        new_id = self.ingestion_job_repository.create_job(
            original["source_url"], country=original.get("country"),
        )
        logger.info(
            "Ingestion job retried",
            extra={"stage": "queued", "original_job_id": job_id, "new_job_id": new_id, "source_url": original["source_url"]},
        )
        return {"job_id": new_id, "source_url": original["source_url"], "country": original.get("country")}

    def mark_fetched(self, job_id):
        self.ingestion_job_repository.transition_job(job_id, "fetched")
        logger.info("Ingestion job fetched", extra={"stage": "fetched", "ingestion_job_id": job_id})

    def mark_normalized(self, job_id, source_snapshot_id):
        self.ingestion_job_repository.transition_job(
            job_id,
            "normalized",
            source_snapshot_id=source_snapshot_id,
        )
        logger.info(
            "Ingestion job normalized",
            extra={"stage": "normalized", "ingestion_job_id": job_id, "source_snapshot_id": source_snapshot_id},
        )

    def mark_extracted(self, job_id):
        self.ingestion_job_repository.transition_job(job_id, "extracted")
        logger.info("Ingestion job extracted", extra={"stage": "extracted", "ingestion_job_id": job_id})

    def mark_reconciled(self, job_id):
        self.ingestion_job_repository.transition_job(job_id, "reconciled")
        logger.info("Ingestion job reconciled", extra={"stage": "reconciled", "ingestion_job_id": job_id})

    def mark_failed(self, job_id, failure_reason):
        self.ingestion_job_repository.transition_job(
            job_id,
            "failed",
            failure_reason=failure_reason,
        )
        logger.error(
            "Ingestion job failed",
            extra={"stage": "failed", "ingestion_job_id": job_id, "failure": failure_reason},
        )

    def list_recent_jobs(self, limit=25):
        return self.ingestion_job_repository.list_recent_jobs(limit=limit)
