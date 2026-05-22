import logging


logger = logging.getLogger(__name__)


class ReviewService:
    def __init__(self, country_guide_repository):
        self.country_guide_repository = country_guide_repository

    def list_country_guide_entries(self):
        return self.country_guide_repository.list_country_guide_entries()

    def list_pending_review_items(self):
        return self.country_guide_repository.list_pending_review_items()

    def list_audit_entries(self):
        return self.country_guide_repository.list_audit_entries()

    def approve_review_item(self, item_id, comment):
        logger.info(
            "Approving review item",
            extra={"stage": "review", "review_item_id": item_id},
        )
        result = self.country_guide_repository.approve_pending_review_item(item_id, comment)
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
        return result

    def reject_review_item(self, item_id, comment):
        logger.info(
            "Rejecting review item",
            extra={"stage": "review", "review_item_id": item_id},
        )
        result = self.country_guide_repository.reject_pending_review_item(item_id, comment)
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
