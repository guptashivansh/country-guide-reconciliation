# Semantic Reconciliation Engine

## Design Rationale

When the extraction pipeline detects that a proposed rule value differs from the currently published rule, the raw text difference alone is uninformative. The string "15 days annual leave" → "fifteen days annual leave" is operationally irrelevant; the string "15 days annual leave" → "20 days annual leave" is a material compliance event. Without classification, every detected difference looks equally urgent, which means nothing is actually treated as urgent.

The semantic reconciliation engine classifies every detected difference into a change type and a materiality level. This classification does three things:

1. **Prioritizes reviewer attention** — CRITICAL changes surface at the top of the review queue; INFORMATIONAL changes appear at the bottom
2. **Gates bulk approve eligibility** — Only items below the CRITICAL threshold can be bulk-approved
3. **Provides documented reasoning** — Every classification has a `reasoning` field recording why the engine classified it as it did, enabling auditors to evaluate the classification

The engine's classification step is advisory: it never decides whether a detected difference reaches the review queue. A failed or low-confidence classification still produces a review item — it just arrives unlabeled, at the bottom of the triage order, rather than being dropped.

---

## LLM-Based Classification

`LLMReconciliationEngine` (`app/reconciliation/llm_reconciliation_service.py`) classifies every detected change by calling an LLM (Groq LLaMA 3.3 70B, `temperature=0.0`) against a fixed rubric and a closed label set, rather than matching the text against a hand-written regex pattern library. This replaced the previous `SemanticReconciliationEngine`, which is no longer part of the codebase.

**Why the regex engine was replaced.** The pattern library only recognized English compliance keywords ("minimum wage," "visa," "must," "shall," and similar fixed vocabulary). Any change phrased outside that vocabulary — non-English source text, a synonym the pattern library didn't enumerate, or a sentence structure the numeric/eligibility/requirement patterns didn't anticipate — fell through to `NON_MATERIAL_FORMATTING` regardless of its actual materiality. A rule change in a high-impact domain phrased in unfamiliar wording was indistinguishable, to the regex engine, from a punctuation fix. An LLM classifying against the same rubric generalizes across phrasing the pattern library could not enumerate in advance.

**How non-determinism is managed, not eliminated.** `temperature=0.0` minimizes — but does not guarantee zero — run-to-run variance. The prompt encodes the same materiality rubric the regex engine used (high-impact domains, eligibility/visa changes escalate to CRITICAL or HIGH, requirement removal is treated more severely than requirement addition), so the classification target is the same even though the mechanism changed. Every classification's `reasoning` is logged and stored with the review queue item, so an auditor can inspect why a given label was produced — even though, unlike a regex match, that reasoning is the model's own account rather than a literal pattern trace. Classification is advisory: it labels severity for triage, it does not gate whether a change reaches the review queue, and it does not decide approval.

**Failure mode is fail-open, not fail-closed.** An LLM call can fail to return valid JSON, return a value outside the enum, time out, or hit a rate limit. `LLMReconciliationEngine` retries internally (`max_attempts`, default 2) on both malformed responses and provider exceptions. If classification still fails after exhausting attempts, it raises, and `ReconciliationService.reconcile_extracted_rules()` catches that exception, logs a warning, and enqueues the review item without a `materiality_level` or `change_type` label rather than dropping it. A model outage degrades triage ordering; it never suppresses a detected change.

---

## Classification Contract

The engine sends a prompt built from the old and new `CanonicalComplianceRule` and requires the response to be a JSON object matching this schema exactly:

```python
class SemanticReconciliationResult(BaseModel):
    semantic_change_detected: bool
    materiality_level: MaterialityLevel   # CRITICAL | HIGH | MODERATE | LOW | INFORMATIONAL
    change_type: ChangeType               # see change types below
    human_readable_summary: str
    reasoning: list[str]
```

`change_type` is one of: `NUMERIC_THRESHOLD_CHANGE`, `ELIGIBILITY_CHANGE`, `REQUIREMENT_ADDED`, `REQUIREMENT_REMOVED`, `TIMELINE_CHANGE`, `NON_MATERIAL_FORMATTING`.

A response that fails JSON parsing, or that fails Pydantic validation (e.g. an invalid enum value like `"EXTREME"` for `materiality_level`), is treated identically to a provider exception: it consumes a retry attempt rather than being silently coerced or accepted.

---

## Materiality Rubric

The prompt encodes the same severity framework the regex engine enforced, now applied by the model rather than a pattern match:

| Signal | Materiality Level |
|--------|-------------------|
| Affects visa, work permit, or immigration eligibility; or a mandatory requirement was removed | CRITICAL |
| Affects minimum wage, tax, social security, pension, termination, dismissal, or overtime; or a numeric threshold moved by 25% or more; or the population of workers covered by the rule changed | HIGH |
| A numeric threshold, deadline, or timeline changed, but the rule is not in a high-impact domain | MODERATE |
| Wording changed and a requirement was added, but no numeric, eligibility, or timeline signal was found | LOW |
| No material compliance change — punctuation, capitalization, spacing, or non-substantive rewording only | INFORMATIONAL |

### Why requirement removal is treated as CRITICAL

Removing a mandatory obligation from a rule text means the organization was previously subject to that requirement. If the requirement is legitimately removed (the law changed), publication is straightforward. But if the requirement was removed from the source due to a website restructuring or extraction error, and the organization stops applying it based on this change, the compliance gap is direct and immediate. The CRITICAL classification ensures this change is individually reviewed — `bulk_approve_non_critical()` cannot approve it without a human looking at it directly.

---

## Reconciliation Result Object

```python
class SemanticReconciliationResult(BaseModel):
    semantic_change_detected: bool
    materiality_level: MaterialityLevel
    change_type: ChangeType
    human_readable_summary: str   # e.g., "Minimum wage increased from INR 21,000 to INR 23,500"
    reasoning: list[str]          # e.g., ["Numeric value changed from 21000 to 23500 in a minimum-wage context."]
```

The `reasoning` field is stored with the review queue item. Reviewers can examine it to understand why the engine classified the change as it did. This is a governance transparency feature: the classification is not presented as a black box, even though — unlike the old regex engine — the reasoning text is the model's stated rationale rather than a deterministic pattern-match trace.

---

## Duplicate Suppression

The reconciliation service applies a duplicate suppression check before creating a review queue item. If a pending review item already exists for the same (country, section, new_value) triple, no new item is created. This prevents the review queue from accumulating identical items from repeated syncs on unchanged sources. This logic is unchanged by the move to LLM classification — it runs in `ReconciliationService`, independent of which engine produced the materiality label.

**Behavior when a new extraction differs from both the pending item and the published rule:** A new review item is created, and the previous pending item is superseded. The system does not accumulate competing proposals for the same section.

---

## Data Flow

```
ReconciliationService receives: (old_value, new_value, country, section, source_url, snapshot_id)
    ↓
LLMReconciliationEngine.reconcile(old_rule, new_rule)
    ↓
Prompt built from old/new CanonicalComplianceRule, sent to GroqProvider.complete()
    ↓
JSON response parsed and validated against SemanticReconciliationResult
    ↓ (on malformed response or provider exception: retry, up to max_attempts)
SemanticReconciliationResult {
    semantic_change_detected: true,
    materiality_level: "CRITICAL",
    change_type: "NUMERIC_THRESHOLD_CHANGE",
    human_readable_summary: "Minimum wage increased from INR 21,000 to INR 23,500",
    reasoning: ["Numeric value changed from 21000 to 23500 in a minimum-wage context."]
}
    ↓ (on failure after exhausting attempts: caught by ReconciliationService, logged, enqueued unlabeled)
review_queue INSERT (materiality_level, change_type, reasoning stored when classification succeeded)
```

---

## Governance Controls

| Control | Implementation |
|---------|---------------|
| Critical changes require individual review | `bulk_approve_non_critical()` filters on `severity != 'critical'` at repository level |
| Classification reasoning is preserved | `reasoning` field logged and stored with every successfully classified review queue item |
| Classification failure cannot suppress a change | `ReconciliationService` catches classification exceptions and enqueues the item unlabeled rather than dropping it |
| Reviewer sees diff regardless of classification | Before/after values are always displayed; classification is advisory, not filtering |
| LLM responses are schema-validated before use | `SemanticReconciliationResult.model_validate()` rejects malformed JSON and invalid enum values, triggering a retry rather than accepting bad data |

---

## Backend Components

| Component | File | Responsibility |
|-----------|------|----------------|
| `LLMReconciliationEngine` | `app/reconciliation/llm_reconciliation_service.py` (97 lines) | Builds the classification prompt, calls the injected `LLMProvider`, parses and validates the response, retries on failure |
| `GroqProvider` | `app/llm/groq_provider.py` (45 lines) | `LLMProvider` implementation backed by the Groq SDK; rotates across configured API keys on rate limit |
| `LLMProvider` | `app/llm/provider.py` | `Protocol` defining the `complete(prompt: str) -> str` contract; the reconciliation engine depends on this interface, not on Groq directly |
| `ReconciliationService` | `app/reconciliation/reconciliation_service.py` (165 lines) | Orchestrates comparison, duplicate suppression, review queue insertion, fail-open handling of classification errors |
| `MaterialityLevel` | `app/reconciliation/schemas.py` | Enum: CRITICAL, HIGH, MODERATE, LOW, INFORMATIONAL |
| `ChangeType` | `app/reconciliation/schemas.py` | Enum: 6 change types |
| `SemanticReconciliationResult` | `app/reconciliation/schemas.py` | Pydantic result model |

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| LLM misclassifies a CRITICAL change as INFORMATIONAL | Reviewer sees the before/after diff regardless; INFORMATIONAL items are still surfaced in the review queue, not suppressed |
| LLM call fails (timeout, rate limit, malformed JSON) after exhausting retries | `ReconciliationService` catches the exception and enqueues the item unclassified rather than dropping it; nothing is silently lost |
| LLM returns an invalid enum value (e.g. a materiality level outside the closed set) | Pydantic validation rejects the response before it reaches the review queue; the attempt is retried instead of accepted |
| Classification produces an incorrect `human_readable_summary` | Summary is informational; the canonical evidence is always the source paragraph; summary errors do not affect governance decisions |
| Increased dependency on Groq availability/quota | Extraction and classification now share one rate-limited resource; `GroqProvider` rotates across configured keys, and a classification failure degrades to "enqueue unlabeled" rather than blocking the sync — see [Architectural Decisions](../architecture/overview.md#architectural-decisions-rationale) for the tradeoff this introduces |
