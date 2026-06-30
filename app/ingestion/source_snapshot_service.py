import json
import logging


logger = logging.getLogger(__name__)


class SourceSnapshotService:
    def __init__(self, source_snapshot_repository):
        self.source_snapshot_repository = source_snapshot_repository

    def persist_snapshot(self, source_url, raw_text, content_hash):
        snapshot_id = self.source_snapshot_repository.create_snapshot(
            source_url=source_url,
            raw_text=raw_text,
            content_hash=content_hash,
            extraction_status="pending",
        )
        logger.info(
            "Persisted source snapshot",
            extra={
                "stage": "snapshot",
                "source_url": source_url,
                "source_snapshot_id": snapshot_id,
                "content_hash": content_hash,
            },
        )
        return snapshot_id

    def mark_extraction_succeeded(self, snapshot_id, rules=None):
        rules_json = json.dumps([r.model_dump() if hasattr(r, 'model_dump') else r for r in rules]) if rules else None
        self.source_snapshot_repository.update_extraction_status(
            snapshot_id, "succeeded", extracted_rules_json=rules_json,
        )
        logger.info(
            "Marked snapshot extraction succeeded",
            extra={"stage": "snapshot", "source_snapshot_id": snapshot_id},
        )

    def mark_extraction_failed(self, snapshot_id):
        self.source_snapshot_repository.update_extraction_status(snapshot_id, "failed")
        logger.warning(
            "Marked snapshot extraction failed",
            extra={"stage": "snapshot", "source_snapshot_id": snapshot_id},
        )

    def get_snapshot(self, snapshot_id):
        return self.source_snapshot_repository.get_snapshot(snapshot_id)

    def get_latest_by_source_url(self, source_url):
        return self.source_snapshot_repository.get_latest_by_source_url(source_url)
