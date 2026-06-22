import logging

from app.models.workflow_results import FailureDetail, ReconciliationResult


logger = logging.getLogger(__name__)


class ReconciliationService:
    def __init__(self, country_guide_repository, reconciliation_engine):
        self.country_guide_repository = country_guide_repository
        self.reconciliation_engine = reconciliation_engine

    def reconcile_canonical_rules(self, old_rule, new_rule):
        return self.reconciliation_engine.reconcile(old_rule, new_rule)

    def reconcile_extracted_rules(self, country, extracted_data, source_url, source_hash, source_snapshot_id):
        changes_found = 0
        skipped_count = 0
        failures = []
        logger.info(
            "Starting reconciliation",
            extra={
                "stage": "reconciliation",
                "source_url": source_url,
                "source_snapshot_id": source_snapshot_id,
                "extraction_count": len(extracted_data),
            },
        )

        for item in extracted_data:
            try:
                section = item.get("section")
                new_value = item.get("value")
                confidence = item.get("confidence", 0.5)
                severity = item.get("severity", "minor")
                source_paragraph = item.get("source_paragraph", "")
                effective_date = item.get("effective_date")

                if not section or not new_value:
                    skipped_count += 1
                    failures.append({
                        "type": "validation_error",
                        "reason": "Extracted rule missing section or value",
                        "metadata": {"item": item},
                    })
                    logger.warning(
                        "Skipping extracted rule with missing section or value",
                        extra={"stage": "reconciliation", "source_url": source_url, "source_snapshot_id": source_snapshot_id},
                    )
                    continue

                old_value = self.country_guide_repository.get_current_value(country, section)
                if old_value.strip().lower() == new_value.strip().lower():
                    skipped_count += 1
                    logger.info(
                        "Skipping unchanged rule",
                        extra={"stage": "reconciliation", "source_url": source_url, "section": section},
                    )
                    continue

                if self.country_guide_repository.pending_review_exists(country, section):
                    skipped_count += 1
                    logger.info(
                        "Skipping duplicate pending review item",
                        extra={"stage": "reconciliation", "source_url": source_url, "section": section},
                    )
                    continue

                materiality_level = None
                change_type = None
                try:
                    sem = self.reconciliation_engine.reconcile(
                        {"country": country, "section": section, "value": old_value},
                        {"country": country, "section": section, "value": new_value},
                    )
                    materiality_level = sem.materiality_level
                    change_type = sem.change_type
                    logger.info(
                        "LLM classification complete",
                        extra={
                            "stage": "reconciliation",
                            "section": section,
                            "materiality": materiality_level,
                            "change_type": change_type,
                            "reasoning": sem.reasoning,
                        },
                    )
                except Exception as e:
                    logger.warning(
                        "LLM classification failed — enqueuing without classification",
                        extra={"stage": "reconciliation", "section": section, "error": str(e)},
                    )

                self.country_guide_repository.enqueue_review_item(
                    country=country,
                    section=section,
                    old_value=old_value,
                    new_value=new_value,
                    severity=severity,
                    confidence=confidence,
                    source_url=source_url,
                    source_paragraph=source_paragraph,
                    source_hash=source_hash,
                    source_snapshot_id=source_snapshot_id,
                    effective_date=effective_date,
                    materiality_level=materiality_level,
                    change_type=change_type,
                )
                changes_found += 1
                logger.info(
                    "Queued reconciliation review item",
                    extra={"stage": "reconciliation", "source_url": source_url, "section": section},
                )
            except Exception as e:
                skipped_count += 1
                failures.append({
                    "type": "reconciliation_error",
                    "reason": str(e),
                    "metadata": {"item": item},
                })
                logger.error(
                    "Failed to reconcile extracted rule",
                    extra={"stage": "reconciliation", "source_url": source_url, "failure": str(e)},
                )

        status = "success"
        failure = None
        if failures and changes_found:
            status = "partial"
            failure = FailureDetail(
                type="reconciliation_error",
                reason="One or more extracted rules failed reconciliation",
                metadata={"failures": failures},
            )
        elif failures and not changes_found:
            status = "failed"
            failure = FailureDetail(
                type="reconciliation_error",
                reason="No extracted rules could be reconciled",
                metadata={"failures": failures},
            )

        logger.info(
            "Completed reconciliation",
            extra={
                "stage": "reconciliation",
                "source_url": source_url,
                "source_snapshot_id": source_snapshot_id,
                "changes_queued": changes_found,
                "result_status": status,
            },
        )
        return ReconciliationResult(
            status=status,
            source_url=source_url,
            changes_queued=changes_found,
            skipped_count=skipped_count,
            failure=failure,
            metadata={
                "source_hash": source_hash,
                "source_snapshot_id": source_snapshot_id,
                "failure_count": len(failures),
            },
        )
