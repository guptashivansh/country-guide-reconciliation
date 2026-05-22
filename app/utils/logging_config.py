import logging
import os


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
CONTEXT_FIELDS = (
    "stage",
    "source_url",
    "ingestion_job_id",
    "source_snapshot_id",
    "source_chunk_index",
    "section",
    "attempt",
    "status_code",
    "character_count",
    "extraction_count",
    "changes_queued",
    "result_status",
    "failure_type",
    "content_hash",
    "review_item_id",
    "failure",
)


class ContextFormatter(logging.Formatter):
    def format(self, record):
        message = super().format(record)
        context = []
        for field in CONTEXT_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                context.append(f"{field}={value}")
        if context:
            return f"{message} {' '.join(context)}"
        return message


def configure_logging():
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if not root_logger.handlers:
        handler = logging.StreamHandler()
        root_logger.addHandler(handler)

    for handler in root_logger.handlers:
        handler.setFormatter(ContextFormatter(LOG_FORMAT))
        handler.setLevel(level)

    logging.getLogger("werkzeug").setLevel(logging.WARNING)
