import logging

import requests

from app.extraction.content_chunker import ContentChunker
from app.extraction.employment_rule_parser import EmploymentRuleParser
from app.extraction.employment_rule_aggregator import EmploymentRuleAggregator
from app.models.workflow_results import ExtractionResult, FailureDetail


logger = logging.getLogger(__name__)


class OllamaExtractionService:
    def __init__(self, model="qwen2.5:3b", base_url="http://host.docker.internal:11434",
                 parser=None, chunker=None, aggregator=None, max_attempts=2):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.parser = parser or EmploymentRuleParser()
        self.chunker = chunker or ContentChunker()
        self.aggregator = aggregator or EmploymentRuleAggregator()
        self.max_attempts = max_attempts

    def extract_employment_rules(self, content, source_url, country, sections):
        allowed_sections = tuple(sections)
        chunks = self.chunker.split(content)
        logger.info(
            "Prepared content chunks for Ollama extraction",
            extra={"stage": "extraction", "source_url": source_url, "extraction_count": len(chunks)},
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
            "Aggregated Ollama extraction results",
            extra={
                "stage": "extraction_aggregate",
                "source_url": source_url,
                "extraction_count": len(aggregated_rules),
                "result_status": status,
            },
        )
        return ExtractionResult(
            status=status, source_url=source_url, rules=aggregated_rules, failure=failure,
            metadata={"chunk_count": len(chunks), "failed_chunk_count": len(failed_chunks), "extraction_count": len(aggregated_rules)},
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
                    "Starting Ollama extraction attempt",
                    extra={"stage": "extraction", "source_url": source_url, "attempt": attempt, "source_chunk_index": chunk_index},
                )
                raw = self._request_extraction(prompt)
                parsed_rules = self.parser.parse(raw, sections, source_url=source_url)
                if parsed_rules:
                    logger.info(
                        "Ollama extraction completed",
                        extra={"stage": "extraction", "source_url": source_url, "attempt": attempt, "extraction_count": len(parsed_rules), "source_chunk_index": chunk_index},
                    )
                    return ExtractionResult(
                        status="success", source_url=source_url, rules=parsed_rules,
                        metadata={"chunk_index": chunk_index, "chunk_count": chunk_count, "attempt": attempt},
                    )
                logger.warning(
                    "Ollama extraction attempt returned no valid rules",
                    extra={"stage": "extraction", "source_url": source_url, "attempt": attempt, "source_chunk_index": chunk_index},
                )
            except Exception as e:
                logger.error(
                    "Ollama extraction attempt failed",
                    extra={"stage": "extraction", "source_url": source_url, "attempt": attempt, "failure": str(e), "source_chunk_index": chunk_index},
                )

        return ExtractionResult(
            status="failed", source_url=source_url,
            failure=FailureDetail(type="extraction_error", reason="Chunk extraction failed or returned no valid rules", metadata={"chunk_index": chunk_index, "chunk_count": chunk_count}),
            metadata={"chunk_index": chunk_index, "chunk_count": chunk_count},
        )

    def _request_extraction(self, prompt):
        response = requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.1},
            },
            timeout=600,
        )
        response.raise_for_status()
        return response.json()["message"]["content"].strip()
