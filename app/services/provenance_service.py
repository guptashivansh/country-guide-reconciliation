import logging

logger = logging.getLogger(__name__)


class ProvenanceService:
    def __init__(self, provenance_repository, parser_version="groq/llama-3.3-70b-versatile/v1"):
        self.repo = provenance_repository
        self.parser_version = parser_version

    def record_approval(self, approval_result, reviewer_action="approved"):
        """
        Write a provenance record after a single review-queue item is approved.
        approval_result is the enriched dict returned by approve_pending_review_item.
        """
        snapshot_id = approval_result.get("source_snapshot_id")
        job = self.repo.resolve_ingestion_job_id(snapshot_id)

        try:
            pid = self.repo.write(
                country=approval_result["country"],
                section=approval_result["section"],
                rule_value=approval_result.get("new_value"),
                review_queue_id=approval_result.get("item_id"),
                source_snapshot_id=snapshot_id,
                ingestion_job_id=job["id"] if job else None,
                source_url=approval_result.get("source_url"),
                source_hash=approval_result.get("source_hash"),
                source_fragment=approval_result.get("source_paragraph"),
                extraction_confidence=approval_result.get("confidence"),
                parser_version=self.parser_version,
                reviewer_action=reviewer_action,
                reviewer_assignee=approval_result.get("reviewer_assignee"),
                reviewer_rationale=approval_result.get("reviewer_rationale"),
                reviewer_comment=approval_result.get("reviewer_comment"),
                crawled_at=job["queued_at"] if job else None,
                extracted_at=job["extracted_at"] if job else None,
                reviewed_at=approval_result.get("reviewed_at"),
            )
            self.repo.set_current(approval_result["country"], approval_result["section"], pid)
            logger.info(
                "Provenance recorded",
                extra={
                    "stage": "provenance",
                    "provenance_id": pid,
                    "country": approval_result["country"],
                    "section": approval_result["section"],
                    "action": reviewer_action,
                },
            )
            return pid
        except Exception as e:
            logger.warning(
                "Provenance write failed — approval still committed",
                extra={"stage": "provenance", "failure": str(e)},
            )
            return None

    def record_bulk_approval(self, items):
        """
        Write provenance records for a list of bulk-approved items.
        Each item is the enriched dict returned by bulk_approve_non_critical.
        """
        ids = []
        for item in items:
            pid = self.record_approval(item, reviewer_action="bulk_approved")
            ids.append(pid)
        return ids

    def record_seed(self, country, section, value, source_url):
        """Write a minimal provenance record for initially seeded rules."""
        try:
            pid = self.repo.write(
                country=country,
                section=section,
                rule_value=value,
                source_url=source_url,
                reviewer_action="seeded",
            )
            self.repo.set_current(country, section, pid)
            return pid
        except Exception as e:
            logger.warning("Seed provenance write failed", extra={"stage": "provenance", "failure": str(e)})
            return None

    def get_chain(self, country, section):
        return self.repo.get_current_chain(country, section)

    def get_history(self, country, section):
        return self.repo.get_history(country, section)
