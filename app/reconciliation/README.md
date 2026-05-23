# Semantic Reconciliation Engine

This package owns semantic comparison of canonical compliance rules. It is deliberately independent from ingestion and extraction: callers pass an old canonical rule and a new canonical rule, and receive a typed `SemanticReconciliationResult`.

## Architecture

- `schemas.py` defines the canonical input and output contracts:
  - `CanonicalComplianceRule`
  - `NumericThreshold`
  - `TimelineRequirement`
  - `SemanticReconciliationResult`
  - `MaterialityLevel`
  - `ChangeType`
- `semantic_reconciliation_service.py` contains `SemanticReconciliationEngine`.
- `reconciliation_service.py` keeps the existing review-queue API intact and exposes an additive `reconcile_canonical_rules` adapter.

## Deterministic First

The engine checks deterministic signals before fallback:

1. Non-material formatting equivalence
2. Timeline/deadline changes
3. Numeric threshold changes
4. Eligibility scope changes
5. Requirement added or removed
6. Optional fallback classifier

The fallback is defined by `SemanticReconciliationFallback`. Production code can provide an LLM-backed implementation later without coupling this module to a model provider.

## Example

```python
from app.reconciliation import SemanticReconciliationEngine

engine = SemanticReconciliationEngine()
result = engine.reconcile(
    {
        "section": "termination_notice",
        "text": "Employer must provide notice within 30 days before termination.",
    },
    {
        "section": "termination_notice",
        "text": "Employer must provide notice within 45 days before termination.",
    },
)

assert result.change_type.value == "TIMELINE_CHANGE"
```

Example JSON payloads live in `examples/reconciliation_payloads.json`.
