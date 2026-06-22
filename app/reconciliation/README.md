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
- `llm_reconciliation_service.py` contains `LLMReconciliationEngine`, which classifies a change by calling an injected `LLMProvider` (see `app/llm/provider.py`) rather than matching against a hand-written pattern library.
- `reconciliation_service.py` keeps the existing review-queue API intact and exposes an additive `reconcile_canonical_rules` adapter.

## LLM-Backed Classification

`LLMReconciliationEngine` builds a prompt from the old and new rule, sends it to the configured `LLMProvider` (Claude `claude-sonnet-4-6`, `temperature=0.0` in production via `ClaudeProvider`), and validates the JSON response against `SemanticReconciliationResult`. On a malformed response, an invalid enum value, or a provider exception, it retries up to `max_attempts` times before raising.

The engine depends only on the `LLMProvider` protocol — `complete(prompt: str) -> str` — not on any vendor SDK directly, so it can be tested with a fake provider and swapped to a different backend without changing this module. Production wiring (`app/__init__.py`) intentionally puts classification on a different vendor (Claude) than extraction (Groq), so neither vendor's outage degrades both pipeline stages at once.

Callers (`ReconciliationService`) treat a raised exception as fail-open: the review item is still enqueued, just without a `materiality_level`/`change_type` label, rather than being dropped.

## Example

```python
from app.llm.claude_provider import ClaudeProvider
from app.reconciliation import LLMReconciliationEngine

engine = LLMReconciliationEngine(ClaudeProvider(api_keys=["..."]))
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

In tests, swap `ClaudeProvider` for a fake implementing `complete()` to avoid calling the real API — see `tests/test_llm_reconciliation.py`.

Example JSON payloads live in `examples/reconciliation_payloads.json`.
