import logging
import threading
import time

from groq import Groq
from groq import AuthenticationError, RateLimitError

from app.extraction.content_chunker import ContentChunker
from app.extraction.employment_rule_parser import EmploymentRuleParser
from app.extraction.employment_rule_aggregator import EmploymentRuleAggregator
from app.models.workflow_results import ExtractionResult, FailureDetail


logger = logging.getLogger(__name__)


class GroqExtractionService:
    RPM_PER_KEY = 30

    def __init__(self, api_keys, parser=None, chunker=None, aggregator=None, max_attempts=2, model=None):
        if isinstance(api_keys, str):
            api_keys = [api_keys] if api_keys else []
        self._clients = [Groq(api_key=k) for k in api_keys if k]
        self._current = 0
        self.model = model or "llama-3.3-70b-versatile"
        self.parser = parser or EmploymentRuleParser()
        self.chunker = chunker or ContentChunker()
        self.aggregator = aggregator or EmploymentRuleAggregator()
        self.max_attempts = max_attempts
        self._min_interval = 60.0 / (self.RPM_PER_KEY * max(len(self._clients), 1))
        self._last_call = 0.0
        self._lock = threading.Lock()

    @property
    def client(self):
        return self._clients[self._current] if self._clients else None

    def _rotate_key(self):
        self._current = (self._current + 1) % len(self._clients)
        logger.info("Rotated to next Groq API key", extra={"key_index": self._current})

    def _throttle(self):
        with self._lock:
            elapsed = time.time() - self._last_call
            if elapsed < self._min_interval:
                wait = self._min_interval - elapsed
            else:
                wait = 0
            self._last_call = time.time() + wait
        if wait:
            time.sleep(wait)

    def extract_employment_rules(self, content, source_url, country, sections):
        if self.client is None:
            logger.error(
                "AI extraction skipped because GROQ_API_KEY is not configured",
                extra={
                    "stage": "extraction_config",
                    "source_url": source_url,
                    "result_status": "failed",
                    "failure_type": "configuration_error",
                },
            )
            return ExtractionResult(
                status="failed",
                source_url=source_url,
                failure=FailureDetail(
                    type="configuration_error",
                    reason="GROQ_API_KEY is not configured",
                    metadata={"stage": "extraction_config"},
                ),
            )

        allowed_sections = tuple(sections)
        chunks = self.chunker.split(content)
        logger.info(
            "Prepared content chunks for extraction",
            extra={"stage": "extraction_chunk", "source_url": source_url, "extraction_count": len(chunks)},
        )

        chunk_results = []
        failed_chunks = []
        for chunk in chunks:
            chunk_result = self._extract_chunk(
                content=chunk["text"],
                source_url=source_url,
                country=country,
                sections=allowed_sections,
                chunk_index=chunk["chunk_index"],
                chunk_count=chunk["chunk_count"],
            )
            if not chunk_result.succeeded:
                failed_chunks.append({
                    "chunk_index": chunk["chunk_index"],
                    "failure": chunk_result.failure.model_dump() if chunk_result.failure else None,
                })
            chunk_results.append({
                "source_url": source_url,
                "chunk_index": chunk["chunk_index"],
                "chunk_count": chunk["chunk_count"],
                "rules": chunk_result.rules,
            })

        aggregated_rules = self.aggregator.aggregate(chunk_results)
        status = "success"
        failure = None
        if failed_chunks and aggregated_rules:
            status = "partial"
            failure = FailureDetail(
                type="extraction_error",
                reason="One or more chunks failed extraction",
                metadata={"failed_chunks": failed_chunks},
            )
        elif failed_chunks and not aggregated_rules:
            status = "failed"
            failure = FailureDetail(
                type="extraction_error",
                reason="All chunks failed extraction or returned no valid rules",
                metadata={"failed_chunks": failed_chunks},
            )
        elif not aggregated_rules:
            status = "failed"
            failure = FailureDetail(
                type="validation_error",
                reason="Extraction returned no valid rules",
                metadata={"chunk_count": len(chunks)},
            )

        logger.info(
            "Aggregated extraction results",
            extra={
                "stage": "extraction_aggregate",
                "source_url": source_url,
                "extraction_count": len(aggregated_rules),
                "result_status": status,
            },
        )
        return ExtractionResult(
            status=status,
            source_url=source_url,
            rules=aggregated_rules,
            failure=failure,
            metadata={
                "chunk_count": len(chunks),
                "failed_chunk_count": len(failed_chunks),
                "extraction_count": len(aggregated_rules),
            },
        )

    def _extract_chunk(self, content, source_url, country, sections, chunk_index, chunk_count):
        sections_str = ", ".join(sections)
        prompt = f"""You are a legal compliance analyst for an Employer of Record (EOR) company.

Analyze the following content from {source_url} and extract employment rules for {country}.

This is chunk {chunk_index + 1} of {chunk_count} from the source.

Extract values ONLY for these sections if found: {sections_str}

Return a JSON array. Each item must have exactly these fields:
- section: one of the section names listed above (use the exact snake_case name)
- value: the extracted rule as a clear, concise string (e.g. "12 days per year", "30 days notice required")
- confidence: float between 0.0 and 1.0
- severity: "critical" (visa/permit/termination rules), "major" (wage/tax/leave rules), or "minor" (procedural/administrative)
- source_paragraph: the exact sentence from the content that supports this value

Rules:
- Only include sections where you find a specific, concrete value — not vague references.
- Do NOT include entries like "No specific value mentioned" or "Not explicitly stated".
- If a section is not covered in the content, omit it entirely.
- Return ONLY the JSON array. No explanation, no markdown fences, no backticks.

Content:
{content}
"""

        for attempt in range(1, self.max_attempts + 1):
            try:
                logger.info(
                    "Starting AI extraction attempt",
                    extra={
                        "stage": "extraction",
                        "source_url": source_url,
                        "attempt": attempt,
                        "source_chunk_index": chunk_index,
                    },
                )
                raw = self._request_extraction(prompt)
                parsed_rules = self.parser.parse(raw, sections, source_url=source_url)
                if parsed_rules:
                    logger.info(
                        "AI extraction completed",
                        extra={
                            "stage": "extraction",
                            "source_url": source_url,
                            "attempt": attempt,
                            "extraction_count": len(parsed_rules),
                            "source_chunk_index": chunk_index,
                        },
                    )
                    return ExtractionResult(
                        status="success",
                        source_url=source_url,
                        rules=parsed_rules,
                        metadata={
                            "chunk_index": chunk_index,
                            "chunk_count": chunk_count,
                            "attempt": attempt,
                        },
                    )
                logger.warning(
                    "AI extraction attempt returned no valid rules",
                    extra={
                        "stage": "extraction",
                        "source_url": source_url,
                        "attempt": attempt,
                        "source_chunk_index": chunk_index,
                    },
                )
            except Exception as e:
                logger.error(
                    "AI extraction attempt failed",
                    extra={
                        "stage": "extraction",
                        "source_url": source_url,
                        "attempt": attempt,
                        "failure": str(e),
                        "source_chunk_index": chunk_index,
                    },
                )

        return ExtractionResult(
            status="failed",
            source_url=source_url,
            failure=FailureDetail(
                type="extraction_error",
                reason="Chunk extraction failed or returned no valid rules",
                metadata={"chunk_index": chunk_index, "chunk_count": chunk_count},
            ),
            metadata={"chunk_index": chunk_index, "chunk_count": chunk_count},
        )

    def _request_extraction(self, prompt):
        max_attempts = max(len(self._clients) * 2, 4)
        for attempt in range(max_attempts):
            self._throttle()
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                )
                self._rotate_key()
                return response.choices[0].message.content.strip()
            except RateLimitError:
                logger.warning("Groq rate-limited on key %d, rotating", self._current)
                self._rotate_key()
                backoff = min(2 ** attempt, 30)
                logger.info("Backing off %ds before retry", backoff)
                time.sleep(backoff)
            except AuthenticationError:
                logger.warning("Groq auth failed on key %d, rotating", self._current)
                self._rotate_key()
        raise RuntimeError("All Groq API keys exhausted after retries")
