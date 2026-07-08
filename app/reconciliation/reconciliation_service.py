import logging
import re

from app.models.workflow_results import FailureDetail, ReconciliationResult


logger = logging.getLogger(__name__)


def _normalize_for_comparison(text: str) -> str:
    text = re.sub(r"\s+", " ", text.strip()).lower()
    text = re.sub(r"^[-•*]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\d+\.\s+", "", text, flags=re.MULTILINE)
    return text.strip()


class ReconciliationService:
    def __init__(self, country_guide_repository, reconciliation_engine):
        self.country_guide_repository = country_guide_repository
        self.reconciliation_engine = reconciliation_engine

    def reconcile_canonical_rules(self, old_rule, new_rule):
        return self.reconciliation_engine.reconcile(old_rule, new_rule)

    def reconcile_against_notion(self, notion_sections_by_country):
        """
        Compare pending review items against current Notion content.
        Auto-resolve items where Notion now reflects the proposed change.

        Args:
            notion_sections_by_country: {country: {section: value}}

        Returns:
            {"resolved": int, "unresolved": int, "details": [...]}
        """
        pending_items = self.country_guide_repository.list_pending_review_items()
        resolved = 0
        unresolved = 0
        details = []

        for item in pending_items:
            country = item["country"]
            section = item["section"]
            new_value = item["new_value"] or ""

            country_sections = notion_sections_by_country.get(country)
            if not country_sections:
                unresolved += 1
                continue

            notion_value = country_sections.get(section)
            if notion_value is None:
                unresolved += 1
                continue

            norm_new = _normalize_for_comparison(new_value)
            norm_notion = _normalize_for_comparison(notion_value)

            matched = False
            if norm_new == norm_notion:
                matched = True
            elif norm_new and norm_notion:
                shorter, longer = (norm_new, norm_notion) if len(norm_new) <= len(norm_notion) else (norm_notion, norm_new)
                if shorter in longer and len(shorter) >= 0.6 * len(longer):
                    matched = True

            if matched:
                result = self.country_guide_repository.resolve_review_item_via_notion(item["id"])
                if result:
                    resolved += 1
                    details.append({
                        "item_id": item["id"],
                        "country": country,
                        "section": section,
                        "status": "resolved_via_notion",
                    })
                    logger.info(
                        "Auto-resolved review item via Notion",
                        extra={"item_id": item["id"], "country": country, "section": section},
                    )
                else:
                    unresolved += 1
            else:
                unresolved += 1

        logger.info(
            "Notion reconciliation complete",
            extra={"resolved": resolved, "unresolved": unresolved},
        )
        return {"resolved": resolved, "unresolved": unresolved, "details": details}

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
