# Semantic Reconciliation Engine

## Design Rationale

When the extraction pipeline detects that a proposed rule value differs from the currently published rule, the raw text difference alone is uninformative. The string "15 days annual leave" → "fifteen days annual leave" is operationally irrelevant; the string "15 days annual leave" → "20 days annual leave" is a material compliance event. Without classification, every detected difference looks equally urgent, which means nothing is actually treated as urgent.

The semantic reconciliation engine classifies every detected difference into a change type and a materiality level. This classification does three things:

1. **Prioritizes reviewer attention** — CRITICAL changes surface at the top of the review queue; INFORMATIONAL changes appear at the bottom
2. **Gates bulk approve eligibility** — Only items below the CRITICAL threshold can be bulk-approved
3. **Provides documented reasoning** — Every classification has a `reasoning` field recording why the engine classified it as it did, enabling auditors to evaluate the classification

The engine's critical design property is determinism. The same (old, new) pair always produces the same classification. Reproducibility is not a convenience — it is a governance requirement.

---

## Why the Engine Does Not Use an LLM

This decision is worth stating explicitly, because it may appear counterintuitive in a system that already uses an LLM for extraction.

**LLMs are non-deterministic at temperature > 0.** Even at temperature=0.1, LLMs can produce different classifications for identical inputs across separate invocations. A compliance reviewer who sees "CRITICAL" for a change on Tuesday and "INFORMATIONAL" for the same change on Wednesday when re-processed has no basis for trusting the classification. An auditor who asks "why was this change classified as HIGH rather than CRITICAL?" cannot receive a reproducible, inspectable answer if the classification came from an LLM.

**Regex classification reasoning is auditable.** The `reasoning` field records the exact pattern match that produced the classification: "Numeric value '21000' changed to '23500' in high-impact domain 'minimum wage'." An auditor can verify this against the source text and the pattern library. LLM reasoning is opaque by comparison.

**Regex classification is instantaneous.** Sub-millisecond classification means the reconciliation layer adds no meaningful latency to the sync pipeline. LLM classification would add seconds per change detection, multiplied across every source endpoint on every sync.

**The LLM is already upstream.** The extraction layer uses AI generalization to handle diverse HTML formats. By the time content reaches reconciliation, it is structured rule text — not raw HTML. Structured text comparison is exactly where deterministic pattern matching outperforms probabilistic inference.

---

## Classification Cascade

The engine applies pattern categories in priority order (highest materiality potential first). The first matching category determines the change type:

```
1. Numeric threshold detection     → NUMERIC_THRESHOLD_CHANGE
   ↓ (if no numeric change)
2. Eligibility scope detection     → ELIGIBILITY_CHANGE
   ↓ (if no eligibility change)
3. Requirement language detection  → REQUIREMENT_ADDED or REQUIREMENT_REMOVED
   ↓ (if no requirement change)
4. Timeline/deadline detection     → TIMELINE_CHANGE
   ↓ (if none of the above)
5. Fallback                        → NON_MATERIAL_FORMATTING
```

**Conservative fallback design:** If a change does not match any specific pattern, it falls through to `NON_MATERIAL_FORMATTING` with INFORMATIONAL materiality. This means the change still enters the review queue — it is not suppressed — but it is presented at the lowest priority. A reviewer who disagrees with the classification sees the before/after diff regardless and can escalate if they believe the change warrants higher priority.

There is no category for "suppress entirely." Every detected semantic difference between an extracted rule and the published rule creates a review item.

---

## Pattern Library

### NUMERIC_PATTERN

Extracts numeric values with units and comparators from rule text.

```
Matches: "15 days", "≥ 3 months", "INR 21,000/month", "2.5%", "12 weeks", "30 calendar days"
Captures: numeric value, unit, optional comparator
```

**Classification logic:** All numeric values are extracted from the old and new text and compared. If the sets differ, the change type is `NUMERIC_THRESHOLD_CHANGE`. If the change involves a high-impact domain (see HIGH_IMPACT_PATTERN), materiality escalates to CRITICAL or HIGH.

### ELIGIBILITY_PATTERN

Detects changes to the population of workers to whom a rule applies.

```
Keywords: "eligible", "applies to", "citizens", "residents", "employees",
          "workers", "contractors", "covered under", "subject to"
```

**Classification logic:** Eligibility keywords present in the new text but absent from the old (or vice versa) indicate that the rule's scope has changed — a different set of workers is now covered. These changes are HIGH materiality regardless of domain, because an organization may be applying the rule to the wrong population.

### REQUIREMENT_PATTERN

Detects changes to mandatory obligation language.

```
Keywords: "must", "shall", "required", "mandatory", "obligated", "compulsory"
```

**Classification logic:** New mandatory language appearing in the new text is `REQUIREMENT_ADDED` (MODERATE materiality). Mandatory language disappearing from the text is `REQUIREMENT_REMOVED` (CRITICAL materiality). The asymmetry is deliberate: removing a requirement carries higher risk than adding one, because the organization may be relying on an obligation that no longer exists.

### HIGH_IMPACT_PATTERN

Identifies regulated domains where numeric changes carry elevated risk.

```
Keywords: "minimum wage", "tax", "pension", "termination", "severance",
          "social security", "health insurance", "work permit", "visa"
```

**Role in materiality escalation:** This pattern does not produce a change type independently. It is applied as a modifier during materiality assessment. A numeric change in a high-impact domain is CRITICAL; the same numeric change in a low-impact domain may be HIGH or MODERATE.

### TIMELINE_CONTEXT_PATTERN

Detects changes to deadlines, notice periods, and effective dates.

```
Keywords: "deadline", "notice", "effective", "within", "before", "after",
          "grace period", "expiry", "by the end of"
```

---

## Materiality Framework

| Change Type | High-Impact Domain | Materiality Level |
|------------|-------------------|------------------|
| NUMERIC_THRESHOLD_CHANGE | minimum wage, tax, social security | CRITICAL |
| NUMERIC_THRESHOLD_CHANGE | leave days, notice period, working hours | HIGH |
| NUMERIC_THRESHOLD_CHANGE | other domains | MODERATE |
| REQUIREMENT_REMOVED | any | CRITICAL |
| ELIGIBILITY_CHANGE | any | HIGH |
| REQUIREMENT_ADDED | any | MODERATE |
| TIMELINE_CHANGE | any | MODERATE |
| NON_MATERIAL_FORMATTING | any | INFORMATIONAL |

### Why REQUIREMENT_REMOVED is CRITICAL

Removing a mandatory obligation from a rule text means the organization was previously subject to that requirement. If the requirement is legitimately removed (the law changed), publication is straightforward. But if the requirement was removed from the source due to a website restructuring or extraction error, and the organization stops applying it based on this change, the compliance gap is direct and immediate. The CRITICAL classification ensures this change is individually reviewed.

---

## Reconciliation Result Object

```python
@dataclass
class SemanticReconciliationResult:
    semantic_change_detected: bool
    materiality_level: str     # "CRITICAL" | "HIGH" | "MODERATE" | "LOW" | "INFORMATIONAL"
    change_type: str           # See classification cascade above
    human_readable_summary: str  # E.g., "Minimum wage increased from INR 21,000 to INR 23,500"
    reasoning: str             # E.g., "Numeric value 21000 changed to 23500 in high-impact domain 'minimum wage'"
```

The `reasoning` field is stored with the review queue item. Reviewers can examine it to understand why the engine classified the change as it did. This is a governance transparency feature: the classification is not a black box.

---

## Duplicate Suppression

The reconciliation service applies a duplicate suppression check before creating a review queue item. If a pending review item already exists for the same (country, section, new_value) triple, no new item is created. This prevents the review queue from accumulating identical items from repeated syncs on unchanged sources.

**Behavior when a new extraction differs from both the pending item and the published rule:** A new review item is created, and the previous pending item is superseded. The system does not accumulate competing proposals for the same section.

---

## Data Flow

```
ReconciliationService receives: (old_value, new_value, country, section, source_url, snapshot_id)
    ↓
SemanticReconciliationEngine.reconcile(old_rule, new_rule)
    ↓
Pattern matching cascade (numeric → eligibility → requirement → timeline → formatting)
    ↓
SemanticReconciliationResult {
    semantic_change_detected: true,
    materiality_level: "CRITICAL",
    change_type: "NUMERIC_THRESHOLD_CHANGE",
    human_readable_summary: "Minimum wage increased from INR 21,000 to INR 23,500",
    reasoning: "Numeric value 21000 changed to 23500 in high-impact domain 'minimum wage'"
}
    ↓
review_queue INSERT (materiality_level, change_type, reasoning stored)
```

---

## Governance Controls

| Control | Implementation |
|---------|---------------|
| Critical changes require individual review | `bulk_approve_non_critical()` filters on `severity != 'critical'` at repository level |
| Classification reasoning is preserved | `reasoning` field stored with every review queue item |
| Classification is reproducible | Same (old, new) pair always produces same result from deterministic engine |
| Fallback never suppresses a change | `NON_MATERIAL_FORMATTING` still enters review queue with INFORMATIONAL priority |
| Reviewer sees diff regardless of classification | Before/after values are always displayed; classification is advisory, not filtering |

---

## Backend Components

| Component | File | Responsibility |
|-----------|------|----------------|
| `SemanticReconciliationEngine` | `app/reconciliation/semantic_reconciliation_service.py` (391 lines) | Pattern matching, classification, materiality scoring, reasoning generation |
| `ReconciliationService` | `app/reconciliation/reconciliation_service.py` (166 lines) | Orchestrates comparison, duplicate suppression, review queue insertion |
| `MaterialityLevel` | `app/reconciliation/schemas.py` | Enum: CRITICAL, HIGH, MODERATE, LOW, INFORMATIONAL |
| `ChangeType` | `app/reconciliation/schemas.py` | Enum: 6 change types |
| `SemanticReconciliationResult` | `app/reconciliation/schemas.py` | Pydantic result model |

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Regex misclassifies a CRITICAL change as INFORMATIONAL | Reviewer sees the before/after diff regardless; INFORMATIONAL items are still surfaced in the review queue, not suppressed |
| Pattern doesn't cover a novel change type | Falls through to NON_MATERIAL_FORMATTING; human reviewer evaluates; classification can be appealed by escalating the item |
| Numeric extraction matches a non-numeric context (e.g., a phone number) | Pattern requires contextual unit tokens (days, months, %, INR, etc.) to qualify as a threshold change; bare numerics do not match |
| High-impact domain pattern matches a benign context | High-impact keywords require proximity to numeric changes; keyword match alone does not escalate materiality |
| Classification produces incorrect human_readable_summary | Summary is informational; the canonical evidence is always the source paragraph; summary errors do not affect governance decisions |
