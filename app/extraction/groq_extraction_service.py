import json
import threading
import time

from groq import Groq
from groq import AuthenticationError, RateLimitError

from app.extraction.content_chunker import ContentChunker
from app.extraction.employment_rule_parser import EmploymentRuleParser
from app.extraction.employment_rule_aggregator import EmploymentRuleAggregator
from app.extraction.extraction_schema import (
    build_response_schema, EXTRACTION_PROMPT,
    build_language_instruction, is_content_extractable,
)
from app.extraction import extraction_logger as log
from app.models.workflow_results import ExtractionResult, FailureDetail


class GroqExtractionService:
    RPM_PER_KEY = 15

    def __init__(self, api_keys, parser=None, chunker=None, aggregator=None, max_attempts=2, model=None):
        if isinstance(api_keys, str):
            api_keys = [api_keys] if api_keys else []
        self._clients = [Groq(api_key=k, max_retries=0) for k in api_keys if k]
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

    def extract_employment_rules(self, content, source_url, country, sections,
                                 content_language=None):
        if self.client is None:
            log.log_no_api_key("Groq", "GROQ_API_KEY")
            return ExtractionResult(
                status="failed",
                source_url=source_url,
                failure=FailureDetail(
                    type="configuration_error",
                    reason="GROQ_API_KEY is not configured",
                    metadata={"stage": "extraction_config"},
                ),
            )

        extractable, reason = is_content_extractable(content)
        if not extractable:
            log.log_extraction_skipped(source_url, reason)
            return ExtractionResult(
                status="failed",
                source_url=source_url,
                failure=FailureDetail(
                    type="extraction_error",
                    reason=f"Content not extractable: {reason}",
                    metadata={"stage": "extraction_precheck"},
                ),
            )

        self._content_language = content_language
        allowed_sections = tuple(sections)
        chunks = self.chunker.split(content)
        log.log_chunks_ready(source_url, len(chunks))

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
            chunk_reasons = [fc["failure"]["reason"] for fc in failed_chunks if fc.get("failure") and fc["failure"].get("reason")]
            summary = chunk_reasons[0] if chunk_reasons else "extraction returned no valid rules"
            failure = FailureDetail(
                type="extraction_error",
                reason=summary,
                metadata={"failed_chunks": failed_chunks},
            )

        log.log_aggregation_result(source_url, len(aggregated_rules), status)
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
        prompt = EXTRACTION_PROMPT.format(
            source_url=source_url,
            country=country,
            language_instruction=build_language_instruction(
                getattr(self, '_content_language', None)),
            chunk_index=chunk_index + 1,
            chunk_count=chunk_count,
            sections_str=", ".join(sections),
            content=content,
        )
        response_format = build_response_schema(sections)

        last_reason = "unknown"
        for attempt in range(1, self.max_attempts + 1):
            try:
                raw = self._call_llm(prompt, response_format)
                log.log_llm_response(raw, attempt, self.max_attempts)

                parsed = json.loads(self.parser._strip_markdown_fence(raw))
                rules_list = parsed.get("rules", []) if isinstance(parsed, dict) else parsed

                parsed_rules = self.parser.parse(json.dumps(rules_list), sections, source_url=source_url)

                log.log_extraction_success(source_url, len(parsed_rules), chunk_index, attempt)
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
            except RuntimeError as e:
                last_reason = str(e)
                log.log_api_error(e, attempt, self.max_attempts)
            except Exception as e:
                last_reason = str(e)
                log.log_api_error(e, attempt, self.max_attempts)

        return ExtractionResult(
            status="failed",
            source_url=source_url,
            failure=FailureDetail(
                type="extraction_error",
                reason=last_reason,
                metadata={"chunk_index": chunk_index, "chunk_count": chunk_count},
            ),
            metadata={"chunk_index": chunk_index, "chunk_count": chunk_count},
        )

    def _call_llm(self, prompt, response_format=None):
        max_attempts = max(len(self._clients) * 2, 4)
        for attempt in range(max_attempts):
            self._throttle()
            try:
                kwargs = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                }
                if response_format:
                    kwargs["response_format"] = response_format
                response = self.client.chat.completions.create(**kwargs)
                self._rotate_key()
                return response.choices[0].message.content.strip()
            except RateLimitError:
                backoff = min(2 ** attempt, 30)
                log.log_rate_limited("Groq", backoff, attempt + 1, max_attempts)
                self._rotate_key()
                time.sleep(backoff)
            except AuthenticationError:
                log.log_auth_failed("Groq", self._current)
                self._rotate_key()
        raise RuntimeError("All Groq API keys exhausted after retries")
