import re
from difflib import SequenceMatcher
from typing import Optional, Protocol, Union

from app.reconciliation.schemas import (
    CanonicalComplianceRule,
    ChangeType,
    MaterialityLevel,
    NumericThreshold,
    SemanticReconciliationResult,
    TimelineRequirement,
)


RuleInput = Union[CanonicalComplianceRule, dict]


class SemanticReconciliationFallback(Protocol):
    def classify(
        self,
        old_rule: CanonicalComplianceRule,
        new_rule: CanonicalComplianceRule,
    ) -> Optional[SemanticReconciliationResult]:
        ...


class NullSemanticReconciliationFallback:
    def classify(
        self,
        old_rule: CanonicalComplianceRule,
        new_rule: CanonicalComplianceRule,
    ) -> Optional[SemanticReconciliationResult]:
        return None


class SemanticReconciliationEngine:
    NUMERIC_PATTERN = re.compile(
        r"(?P<comparator>at least|at most|minimum|maximum|more than|less than|up to|no more than|not less than)?"
        r"\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>%|percent|hours?|days?|weeks?|months?|years?|INR|SGD|USD|AUD|AED|NZD|PHP|PKR)?",
        re.IGNORECASE,
    )
    TIMELINE_UNITS = {"hour", "hours", "day", "days", "week", "weeks", "month", "months", "year", "years"}
    REQUIREMENT_PATTERN = re.compile(
        r"\b(must|shall|required|requires|requirement|mandatory|prohibited|not permitted|need to|has to)\b",
        re.IGNORECASE,
    )
    ELIGIBILITY_PATTERN = re.compile(
        r"\b(eligible|eligibility|applies to|covered employees|citizens|permanent residents|contractors|"
        r"full-time|part-time|probation|exempt|non-exempt|spouse|dependent)\b",
        re.IGNORECASE,
    )
    HIGH_IMPACT_PATTERN = re.compile(
        r"\b(minimum wage|salary|tax|withholding|contribution|social security|pension|fine|penalty|"
        r"termination|dismissal|visa|work permit|overtime|leave entitlement)\b",
        re.IGNORECASE,
    )
    TIMELINE_CONTEXT_PATTERN = re.compile(
        r"\b(deadline|notice|within|after|before|prior to|no later than|effective|renewal|file|submit|"
        r"report|notify|appeal|terminate|termination)\b",
        re.IGNORECASE,
    )

    def __init__(self, fallback: Optional[SemanticReconciliationFallback] = None):
        self.fallback = fallback or NullSemanticReconciliationFallback()

    def reconcile(self, old_rule: RuleInput, new_rule: RuleInput) -> SemanticReconciliationResult:
        old = self._coerce_rule(old_rule)
        new = self._coerce_rule(new_rule)

        deterministic_signals_match = self._deterministic_signals_match(old, new)
        exact_text_match = self._canonical_text(old.text) == self._canonical_text(new.text)
        if exact_text_match and deterministic_signals_match:
            return self._result(
                semantic_change_detected=False,
                materiality_level=MaterialityLevel.INFORMATIONAL,
                change_type=ChangeType.NON_MATERIAL_FORMATTING,
                summary="No semantic compliance change detected.",
                reasoning=["Canonical rule content is equivalent after whitespace and punctuation normalization."],
            )

        formatting_only = self._formatting_only(old.text, new.text)
        if formatting_only and deterministic_signals_match:
            return self._result(
                semantic_change_detected=False,
                materiality_level=MaterialityLevel.INFORMATIONAL,
                change_type=ChangeType.NON_MATERIAL_FORMATTING,
                summary="Only formatting or punctuation changed.",
                reasoning=["Normalized text matches after removing punctuation, case, and spacing differences."],
            )

        timeline_result = self._timeline_change(old, new)
        if timeline_result:
            return timeline_result

        numeric_result = self._numeric_threshold_change(old, new)
        if numeric_result:
            return numeric_result

        eligibility_result = self._eligibility_change(old, new)
        if eligibility_result:
            return eligibility_result

        requirement_result = self._requirement_change(old, new)
        if requirement_result:
            return requirement_result

        fallback_result = self.fallback.classify(old, new)
        if fallback_result:
            return fallback_result

        return self._result(
            semantic_change_detected=True,
            materiality_level=MaterialityLevel.LOW,
            change_type=ChangeType.REQUIREMENT_ADDED,
            summary="Rule wording changed, but no high-confidence material compliance signal was detected.",
            reasoning=[
                "Deterministic checks found text differences but no numeric, eligibility, timeline, or obligation delta.",
                "Classified as low materiality for reviewer confirmation.",
            ],
        )

    def _coerce_rule(self, rule: RuleInput) -> CanonicalComplianceRule:
        if isinstance(rule, CanonicalComplianceRule):
            return rule
        return CanonicalComplianceRule.model_validate(rule)

    def _numeric_threshold_change(
        self,
        old: CanonicalComplianceRule,
        new: CanonicalComplianceRule,
    ) -> Optional[SemanticReconciliationResult]:
        old_thresholds = self._effective_numeric_thresholds(old)
        new_thresholds = self._effective_numeric_thresholds(new)
        if not old_thresholds and not new_thresholds:
            return None

        old_values = self._threshold_signature(old_thresholds)
        new_values = self._threshold_signature(new_thresholds)
        if old_values == new_values:
            return None

        materiality = self._numeric_materiality(old, new, old_thresholds, new_thresholds)
        return self._result(
            semantic_change_detected=True,
            materiality_level=materiality,
            change_type=ChangeType.NUMERIC_THRESHOLD_CHANGE,
            summary="Numeric compliance threshold changed.",
            reasoning=[
                f"Old thresholds: {self._format_thresholds(old_thresholds) or 'none detected'}.",
                f"New thresholds: {self._format_thresholds(new_thresholds) or 'none detected'}.",
                f"Materiality set to {materiality.value} based on threshold movement and regulated-domain keywords.",
            ],
        )

    def _timeline_change(
        self,
        old: CanonicalComplianceRule,
        new: CanonicalComplianceRule,
    ) -> Optional[SemanticReconciliationResult]:
        old_timelines = self._effective_timelines(old)
        new_timelines = self._effective_timelines(new)
        if not old_timelines and not new_timelines:
            return None

        old_values = self._timeline_signature(old_timelines)
        new_values = self._timeline_signature(new_timelines)
        if old_values == new_values:
            return None

        materiality = MaterialityLevel.HIGH if self.HIGH_IMPACT_PATTERN.search(self._combined_text(old, new)) else MaterialityLevel.MODERATE
        return self._result(
            semantic_change_detected=True,
            materiality_level=materiality,
            change_type=ChangeType.TIMELINE_CHANGE,
            summary="Compliance timeline or deadline changed.",
            reasoning=[
                f"Old timelines: {self._format_timelines(old_timelines) or 'none detected'}.",
                f"New timelines: {self._format_timelines(new_timelines) or 'none detected'}.",
                f"Materiality set to {materiality.value} because timeline obligations affect operational deadlines.",
            ],
        )

    def _eligibility_change(
        self,
        old: CanonicalComplianceRule,
        new: CanonicalComplianceRule,
    ) -> Optional[SemanticReconciliationResult]:
        old_eligibility = self._normalized_set(old.eligibility)
        new_eligibility = self._normalized_set(new.eligibility)
        structured_changed = bool(old_eligibility or new_eligibility) and old_eligibility != new_eligibility
        text_has_eligibility = self.ELIGIBILITY_PATTERN.search(self._combined_text(old, new)) is not None
        text_changed = text_has_eligibility and self._token_similarity(old.text, new.text) < 0.92

        if not structured_changed and not text_changed:
            return None

        added = sorted(new_eligibility - old_eligibility)
        removed = sorted(old_eligibility - new_eligibility)
        materiality = MaterialityLevel.CRITICAL if "visa" in self._combined_text(old, new).lower() else MaterialityLevel.HIGH
        reasoning = ["Eligibility scope changed for the canonical rule."]
        if added:
            reasoning.append(f"Eligibility added: {', '.join(added)}.")
        if removed:
            reasoning.append(f"Eligibility removed: {', '.join(removed)}.")
        if text_changed and not structured_changed:
            reasoning.append("Eligibility-related keywords changed in rule text.")

        return self._result(
            semantic_change_detected=True,
            materiality_level=materiality,
            change_type=ChangeType.ELIGIBILITY_CHANGE,
            summary="Eligibility scope changed.",
            reasoning=reasoning,
        )

    def _requirement_change(
        self,
        old: CanonicalComplianceRule,
        new: CanonicalComplianceRule,
    ) -> Optional[SemanticReconciliationResult]:
        old_requirements = self._effective_requirements(old)
        new_requirements = self._effective_requirements(new)

        if not old_requirements and not new_requirements:
            return None

        added = sorted(new_requirements - old_requirements)
        removed = sorted(old_requirements - new_requirements)
        if not added and not removed:
            return None

        if removed and not added:
            change_type = ChangeType.REQUIREMENT_REMOVED
            summary = "Compliance requirement was removed."
        elif added:
            change_type = ChangeType.REQUIREMENT_ADDED
            summary = "Compliance requirement was added."
        else:
            change_type = ChangeType.REQUIREMENT_ADDED
            summary = "Compliance requirement changed."

        materiality = self._requirement_materiality(old, new, added, removed)
        reasoning = []
        if added:
            reasoning.append(f"Added requirement signal: {added[0]}.")
        if removed:
            reasoning.append(f"Removed requirement signal: {removed[0]}.")
        reasoning.append(f"Materiality set to {materiality.value} based on obligation keywords and affected policy domain.")

        return self._result(
            semantic_change_detected=True,
            materiality_level=materiality,
            change_type=change_type,
            summary=summary,
            reasoning=reasoning,
        )

    def _extract_numeric_thresholds(self, text: str) -> list[NumericThreshold]:
        thresholds = []
        for match in self.NUMERIC_PATTERN.finditer(text or ""):
            value = float(match.group("value"))
            unit = (match.group("unit") or "").lower()
            comparator = (match.group("comparator") or "").lower() or None
            thresholds.append(NumericThreshold(value=value, unit=unit, comparator=comparator))
        return thresholds

    def _extract_timelines(self, text: str) -> list[TimelineRequirement]:
        timelines = []
        for match in self.NUMERIC_PATTERN.finditer(text or ""):
            unit = (match.group("unit") or "").lower()
            if unit not in self.TIMELINE_UNITS:
                continue

            start = max(0, match.start() - 45)
            end = min(len(text or ""), match.end() + 45)
            if not self.TIMELINE_CONTEXT_PATTERN.search((text or "")[start:end]):
                continue

            value = float(match.group("value"))
            timelines.append(TimelineRequirement(value=str(value).rstrip("0").rstrip("."), unit=unit))
        return timelines

    def _extract_requirement_sentences(self, text: str) -> set[str]:
        sentences = re.split(r"(?<=[.!?])\s+|[\n;]+", text or "")
        return {
            self._canonical_text(sentence)
            for sentence in sentences
            if sentence.strip() and self.REQUIREMENT_PATTERN.search(sentence)
        }

    def _numeric_materiality(
        self,
        old: CanonicalComplianceRule,
        new: CanonicalComplianceRule,
        old_thresholds: list[NumericThreshold],
        new_thresholds: list[NumericThreshold],
    ) -> MaterialityLevel:
        if self.HIGH_IMPACT_PATTERN.search(self._combined_text(old, new)):
            return MaterialityLevel.HIGH

        old_total = sum(item.value for item in old_thresholds)
        new_total = sum(item.value for item in new_thresholds)
        if old_total and abs(new_total - old_total) / old_total >= 0.25:
            return MaterialityLevel.HIGH
        return MaterialityLevel.MODERATE

    def _requirement_materiality(
        self,
        old: CanonicalComplianceRule,
        new: CanonicalComplianceRule,
        added: list[str],
        removed: list[str],
    ) -> MaterialityLevel:
        combined = self._combined_text(old, new)
        if removed and self.HIGH_IMPACT_PATTERN.search(combined):
            return MaterialityLevel.HIGH
        if self.HIGH_IMPACT_PATTERN.search(combined):
            return MaterialityLevel.HIGH
        return MaterialityLevel.MODERATE if added or removed else MaterialityLevel.LOW

    def _threshold_signature(self, thresholds: list[NumericThreshold]) -> tuple[tuple[float, str, Optional[str]], ...]:
        return tuple(sorted((item.value, item.unit.lower(), item.comparator) for item in thresholds))

    def _timeline_signature(self, timelines: list[TimelineRequirement]) -> tuple[tuple[str, str], ...]:
        return tuple(sorted((item.value.lower(), item.unit.lower()) for item in timelines))

    def _format_thresholds(self, thresholds: list[NumericThreshold]) -> str:
        return ", ".join(
            f"{item.comparator + ' ' if item.comparator else ''}{item.value:g}{(' ' + item.unit) if item.unit else ''}"
            for item in thresholds
        )

    def _format_timelines(self, timelines: list[TimelineRequirement]) -> str:
        return ", ".join(f"{item.value} {item.unit}".strip() for item in timelines)

    def _normalized_set(self, values: list[str]) -> set[str]:
        return {self._canonical_text(value) for value in values if self._canonical_text(value)}

    def _deterministic_signals_match(
        self,
        old: CanonicalComplianceRule,
        new: CanonicalComplianceRule,
    ) -> bool:
        return (
            self._threshold_signature(self._effective_numeric_thresholds(old))
            == self._threshold_signature(self._effective_numeric_thresholds(new))
            and self._timeline_signature(self._effective_timelines(old))
            == self._timeline_signature(self._effective_timelines(new))
            and self._effective_requirements(old) == self._effective_requirements(new)
            and self._normalized_set(old.eligibility) == self._normalized_set(new.eligibility)
        )

    def _effective_numeric_thresholds(self, rule: CanonicalComplianceRule) -> list[NumericThreshold]:
        return rule.numeric_thresholds or self._extract_numeric_thresholds(rule.text)

    def _effective_timelines(self, rule: CanonicalComplianceRule) -> list[TimelineRequirement]:
        return rule.timelines or self._extract_timelines(rule.text)

    def _effective_requirements(self, rule: CanonicalComplianceRule) -> set[str]:
        return self._normalized_set(rule.requirements) or self._extract_requirement_sentences(rule.text)

    def _combined_text(self, old: CanonicalComplianceRule, new: CanonicalComplianceRule) -> str:
        combined = " ".join([old.section, new.section, old.title or "", new.title or "", old.text, new.text])
        return combined.replace("_", " ")

    def _formatting_only(self, old_text: str, new_text: str) -> bool:
        return self._canonical_text(old_text) == self._canonical_text(new_text)

    def _canonical_text(self, value: str) -> str:
        text = re.sub(r"[\W_]+", " ", (value or "").lower())
        return re.sub(r"\s+", " ", text).strip()

    def _token_similarity(self, old_text: str, new_text: str) -> float:
        return SequenceMatcher(None, self._canonical_text(old_text), self._canonical_text(new_text)).ratio()

    def _result(
        self,
        semantic_change_detected: bool,
        materiality_level: MaterialityLevel,
        change_type: ChangeType,
        summary: str,
        reasoning: list[str],
    ) -> SemanticReconciliationResult:
        return SemanticReconciliationResult(
            semantic_change_detected=semantic_change_detected,
            materiality_level=materiality_level,
            change_type=change_type,
            human_readable_summary=summary,
            reasoning=reasoning,
        )
