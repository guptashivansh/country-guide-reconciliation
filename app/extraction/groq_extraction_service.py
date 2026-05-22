import logging

from groq import Groq

from app.extraction.content_chunker import ContentChunker
from app.extraction.employment_rule_parser import EmploymentRuleParser
from app.extraction.employment_rule_aggregator import EmploymentRuleAggregator
from app.models.workflow_results import ExtractionResult, FailureDetail


logger = logging.getLogger(__name__)


class GroqExtractionService:
    def __init__(self, api_key, parser=None, chunker=None, aggregator=None, max_attempts=2):
        self.client = Groq(api_key=api_key) if api_key else None
        self.parser = parser or EmploymentRuleParser()
        self.chunker = chunker or ContentChunker()
        self.aggregator = aggregator or EmploymentRuleAggregator()
        self.max_attempts = max_attempts

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
        prompt = f"""
You are a legal compliance analyst for an Employer of Record (EOR) company.

Analyze the following content from {source_url} and extract employment rules for {country}.

This is chunk {chunk_index + 1} of {chunk_count} from the source.

Extract values ONLY for these sections if found: {sections_str}

Return a JSON array. Each item must have exactly these fields:
- section: one of the sections listed above
- value: the extracted rule as a clear, concise string
- confidence: float between 0 and 1 (how confident you are this is accurate)
- severity: "critical", "major", or "minor" (how important this rule is for compliance)
- source_paragraph: the exact sentence or phrase from the content that supports this value

If a section is not mentioned in the content, do not include it.
Return ONLY valid JSON. No explanation. No markdown. No backticks.

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
        response = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        return response.choices[0].message.content.strip()
