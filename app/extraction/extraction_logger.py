import logging

logger = logging.getLogger("app.extraction")


def log_chunks_ready(source_url, chunk_count):
    logger.info("Prepared %d chunk(s) for extraction — %s", chunk_count, source_url)


def log_llm_response(raw, attempt, max_attempts):
    preview = raw[:200].replace("\n", " ")
    logger.info("         📝 LLM returned %d chars: %s", len(raw), preview)


def log_extraction_success(source_url, rule_count, chunk_index, attempt):
    logger.info("         ✓ Chunk %d: %d rules extracted (attempt %d)", chunk_index + 1, rule_count, attempt)


def log_no_rules_parsed(source_url, attempt, max_attempts):
    logger.warning("         ⚠️  No valid rules parsed (attempt %d/%d)", attempt, max_attempts)


def log_api_error(error, attempt, max_attempts):
    logger.error("         ✗ API error: %s (attempt %d/%d)", error, attempt, max_attempts)


def log_rate_limited(provider, backoff, attempt, max_attempts):
    logger.warning("         ⏳ %s rate-limited, waiting %ds (attempt %d/%d)", provider, backoff, attempt, max_attempts)


def log_auth_failed(provider, key_index):
    logger.warning("%s auth failed on key %d, rotating", provider, key_index)


def log_aggregation_result(source_url, rule_count, status):
    logger.info("Extraction complete — %s: %d rules, status=%s", source_url, rule_count, status)


def log_no_api_key(provider, env_var):
    logger.error("Extraction skipped — %s not configured (set %s)", provider, env_var)
