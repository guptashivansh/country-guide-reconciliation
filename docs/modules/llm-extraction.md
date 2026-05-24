# LLM Extraction Service

## Role in the Governance Architecture

The extraction service occupies a precisely bounded position in the pipeline: it converts unstructured government HTML into structured `EmploymentRule` objects. Nothing else. It does not classify change materiality, does not make publication decisions, and does not interact with the governance record.

This scope boundary is a governance decision, not a technical limitation. The extraction layer is the only stage where probabilistic AI output enters the pipeline. Containing it here — with confidence scoring, Pydantic validation, and a mandatory human review gate downstream — means that AI uncertainty is isolated, quantified, and subject to human authority before it can affect any published data.

---

## What the LLM Does and Does Not Do

| The LLM Does | The LLM Does Not |
|-------------|-----------------|
| Convert unstructured HTML text to structured rule objects | Classify whether a change is material |
| Identify which regulatory sections appear in a source | Decide whether a proposed change should be published |
| Extract specific values (wage figures, leave days, notice periods) | Update any database table directly |
| Self-report a confidence score per extraction | Determine the effective date of any rule |
| Provide a source paragraph as evidence | Access the review queue, audit log, or any governance record |

The LLM's output is always a proposed extraction — a candidate for human review, not an authoritative finding.

---

## Confidence Scoring as a Governance Signal

Every `EmploymentRule` object carries an `extraction_confidence` value between 0.0 and 1.0, self-reported by the model. This score has specific downstream governance implications:

**In the review queue:** Low-confidence items are visually flagged. Reviewers are expected to apply greater scrutiny — examining the source paragraph more carefully and potentially verifying against the live source URL before approving.

**In provenance records:** `extraction_confidence` is stored in every provenance record. This means the confidence of the original extraction is permanently associated with every published rule. If a rule was published from a low-confidence extraction, that fact is in the audit trail.

**In drift detection:** Future enhancements may use confidence trends to detect model quality regression — if average confidence for a country drops significantly between syncs, it may indicate the government website has been restructured.

**What confidence does not mean:** A confidence score of 0.95 does not mean the extracted value is correct. It means the model is highly confident in its interpretation of the source text. The source text itself may be ambiguous, the page may have been restructured, or the model's interpretation may be systematically biased for a particular regulatory format. Confidence is a signal, not a guarantee. Human review is the guarantee.

---

## Multi-Key Rotation: Operational Design

The extraction service accepts a comma-separated list of Groq API keys in the `GROQ_API_KEY` environment variable. Key rotation operates as follows:

1. Extractions are attempted with the current key (index N)
2. On a 429 (rate limit) response: index advances to key N+1 mod total keys
3. The request retries immediately with the new key
4. If all keys return 429, the chunk is marked as failed and the error is logged

**Governance implication:** Rate limit failures are recorded in the `ingestion_jobs.failure_reason` column. The ops dashboard surfaces failed jobs with their reasons. A compliance lead can see exactly which sources failed extraction and on which sync cycle, enabling informed decisions about whether to trigger a manual re-sync.

**Operational limit:** This design provides N× rate limit headroom, where N is the number of configured keys. It does not provide fault tolerance against Groq API outages — if the Groq service is unavailable, all keys fail. In this case, the previously published rules remain unchanged and unaffected. The next scheduled sync will reattempt extraction.

---

## Content Chunking and Context Budget

`ContentChunker` splits input text into chunks of at most 6,000 characters, breaking on sentence boundaries (`(?<=[.!?])\s+|\n+`). Each chunk carries metadata:

```python
{"chunk_index": 0, "chunk_count": 3, "text": "..."}
```

The 6,000-character limit is a budget management decision, not an accuracy optimization. It leaves room for the system prompt, country and section context, and response formatting within the LLM's context window. Government pages that exceed 6,000 characters of relevant content are chunked, with aggregation logic ensuring the highest-confidence extraction per section survives.

**Truncation risk:** Government pages that contain critical information after the 6,000-character mark per chunk may have that information missed. This is mitigated by the sequential chunking model — the full text is covered across chunks — but chunk boundary placement can occasionally split a sentence in a way that loses context. Reviewers who see low-confidence extractions should verify against the live source URL, which is always available in the review queue.

---

## Employment Rule Validation

Every extraction is validated against a Pydantic model before entering the review pipeline:

```python
class EmploymentRule(BaseModel):
    section: str          # Must be in allowed_sections for the country
    value: str            # Non-empty rule text
    confidence: float     # 0.0 to 1.0
    severity: str         # "critical" | "major" | "minor" (normalized to lowercase)
    source_paragraph: str # Non-empty evidence from source text
```

**Validation behavior:** Rules that fail validation are dropped and logged at WARNING level. They do not enter the review queue, do not generate a provenance record, and do not affect published rules. The WARNING log is visible in the ingestion job record and in application logs.

**What validation prevents:**
- Sections outside the configured list for a country (prevents phantom section creation)
- Empty rule values (prevents publishing blank rules)
- Empty source paragraphs (prevents publishing rules with no evidence)
- Invalid severity values (prevents downstream materiality scoring errors)

**What validation does not prevent:** A correctly structured extraction that contains an incorrect value. A value like "INR 21,000/month" that is plausible but wrong will pass validation. It enters the review queue and requires human judgment.

---

## Chunk Aggregation and Deduplication

When a regulatory section appears in multiple chunks — for example, a country's minimum wage is mentioned on the first page and again in a summary section — both chunks produce `EmploymentRule` objects for the same section. The `EmploymentRuleAggregator` resolves this by keeping the highest-confidence extraction per section.

**Governance implication:** If two chunks produce contradictory extractions for the same section (one says "15 days" and another says "18 days"), the higher-confidence one enters the review queue. The lower-confidence one is discarded. This means a reviewer may not see the contradictory extraction.

**Current limitation:** There is no mechanism to flag contradictory multi-chunk extractions for reviewer attention. A future enhancement should surface section conflicts (where two chunks extracted different values) as a specific review flag, prompting closer source verification.

---

## Failure Modes and Governance Handling

| Failure | Detection | Governance Response |
|---------|-----------|---------------------|
| Groq API rate limit | 429 response | Key rotation; retry; if all keys exhausted, job marked `failed` — no rule change, no phantom review item |
| Groq API outage | Connection error | Job marked `failed`; source snapshot preserved for retry; current published rules unchanged |
| LLM returns invalid JSON | JSON parse error | Extraction attempt marked failed; logged at WARNING with raw response; no review item created |
| LLM hallucinates a plausible value | Rule passes Pydantic validation | Hallucination enters review queue; human reviewer rejects with rationale; rejection recorded in audit log |
| Extraction has low confidence (< 0.5) | `confidence` field | Review item created with low-confidence flag; reviewer expected to apply heightened scrutiny |
| Source page restructured | Extraction confidence drops broadly | Multiple low-confidence items appear in review queue; platform engineer should verify source URL and consider updating the source registry |

---

## Model Governance Record

The `parser_version` field in every provenance record (default: `"groq/llama-3.3-70b-versatile/v1"`) serves the following governance functions:

1. **Model lineage:** Every published rule can be traced to the model version that extracted it
2. **Quality regression attribution:** If extraction quality degrades, the version change can be identified in the provenance history
3. **Regulatory AI governance compliance:** Organizations subject to AI model governance requirements (e.g., EU AI Act) can demonstrate that AI model versions are tracked and attributable

When the extraction model is upgraded, the `parser_version` string must be updated in the `GroqExtractionService` constructor before deployment. New extractions use the new version string; historical provenance records retain their original version.

---

## Why Groq and Not OpenAI or Anthropic for Extraction

This decision is operational, not capability-based:

- **Inference latency:** Groq's LPU architecture provides significantly faster inference for this structured extraction task, reducing per-source processing time from ~10 seconds to ~2 seconds
- **Rate limit headroom:** Multi-key rotation works with Groq's free-tier key model, providing effective horizontal scaling without per-request cost overhead
- **Extractive task fit:** LLaMA 3.3 70B performs well on structured extraction at temperature=0.1 — this specific task does not require frontier reasoning capabilities

**Dependency risk:** The extraction layer has a hard dependency on Groq. An outage or service discontinuation would halt new extractions until an alternative provider is integrated. Published rules are unaffected; the system continues to serve its authoritative data. A provider migration would require updating `GroqExtractionService` and its API client while the repository, governance, and provenance layers remain unchanged.

---

## Backend Components

| Component | File | Lines | Responsibility |
|-----------|------|-------|----------------|
| `GroqExtractionService` | `app/extraction/groq_extraction_service.py` | 237 | API calls, key rotation, retry, prompt construction |
| `ContentChunker` | `app/extraction/content_chunker.py` | 49 | Sentence-boundary chunking |
| `EmploymentRuleParser` | `app/extraction/employment_rule_parser.py` | 55 | JSON parsing, Pydantic validation, invalid rule logging |
| `EmploymentRuleAggregator` | `app/extraction/employment_rule_aggregator.py` | 25 | Cross-chunk deduplication (highest confidence per section) |
| `EmploymentRule` | `app/models/employment_rule.py` | 36 | Pydantic model with validators |
| `ExtractionResult` | `app/models/workflow_results.py` | 59 | Result envelope with success/failure/rules |
