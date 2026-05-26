import logging


logger = logging.getLogger(__name__)


class ReviewService:
    def __init__(self, country_guide_repository, provenance_service=None):
        self.country_guide_repository = country_guide_repository
        self.provenance_service = provenance_service

    def list_country_guide_entries(self):
        return self.country_guide_repository.list_country_guide_entries()

    def list_countries_summary(self):
        return self.country_guide_repository.list_countries_summary()

    def get_country_sections(self, country):
        return self.country_guide_repository.get_country_sections(country)

    def list_pending_review_items(self):
        return self.country_guide_repository.list_pending_review_items()

    def list_audit_entries(self):
        return self.country_guide_repository.list_audit_entries()

    def approve_review_item(self, item_id, comment, assignee="", rationale="", effective_date=None):
        logger.info(
            "Approving review item",
            extra={"stage": "review", "review_item_id": item_id},
        )
        result = self.country_guide_repository.approve_pending_review_item(
            item_id,
            comment,
            assignee,
            rationale,
            effective_date,
        )
        if not result:
            logger.warning(
                "Approve failed because pending review item was not found",
                extra={"stage": "review", "review_item_id": item_id},
            )
            return None
        logger.info(
            "Approved review item",
            extra={"stage": "review", "review_item_id": item_id, "section": result["section"]},
        )
        if self.provenance_service:
            self.provenance_service.record_approval(result)
        return result

    def reject_review_item(self, item_id, comment, assignee="", rationale=""):
        logger.info(
            "Rejecting review item",
            extra={"stage": "review", "review_item_id": item_id},
        )
        result = self.country_guide_repository.reject_pending_review_item(item_id, comment, assignee, rationale)
        if not result:
            logger.warning(
                "Reject failed because pending review item was not found",
                extra={"stage": "review", "review_item_id": item_id},
            )
            return None
        logger.info(
            "Rejected review item",
            extra={"stage": "review", "review_item_id": item_id, "section": result["section"]},
        )
        return result

    def assign_review_item(self, item_id, comment, assignee=""):
        logger.info(
            "Assigning review item",
            extra={"stage": "review", "review_item_id": item_id},
        )
        result = self.country_guide_repository.update_review_assignment(item_id, comment, assignee)
        if not result:
            logger.warning(
                "Assign failed because pending review item was not found",
                extra={"stage": "review", "review_item_id": item_id},
            )
            return None
        logger.info(
            "Assigned review item",
            extra={"stage": "review", "review_item_id": item_id, "section": result["section"]},
        )
        return result

    def bulk_approve_non_critical(self, country, comment="", rationale="", effective_date=None):
        logger.info(
            "Bulk approving non-critical items",
            extra={"stage": "review", "country": country},
        )
        result = self.country_guide_repository.bulk_approve_non_critical(country, comment, rationale, effective_date)
        logger.info(
            "Bulk approval complete",
            extra={"stage": "review", "country": country, "approved": result["approved"]},
        )
        if self.provenance_service and result.get("items"):
            self.provenance_service.record_bulk_approval(result["items"])
        return result

    def get_country_notes(self, country):
        return self.country_guide_repository.get_country_notes(country)

    def save_country_notes(self, country, content):
        return self.country_guide_repository.save_country_notes(country, content)

    def manual_edit_rule(self, country, section, new_value):
        return self.country_guide_repository.manual_edit_rule(country, section, new_value)

    def escalate_review_item(self, item_id, comment, assignee="", rationale=""):
        logger.info(
            "Escalating review item",
            extra={"stage": "review", "review_item_id": item_id},
        )
        result = self.country_guide_repository.escalate_review_item(item_id, comment, assignee, rationale)
        if not result:
            logger.warning(
                "Escalate failed because pending review item was not found",
                extra={"stage": "review", "review_item_id": item_id},
            )
            return None
        logger.info(
            "Escalated review item",
            extra={"stage": "review", "review_item_id": item_id, "section": result["section"]},
        )
        return result
