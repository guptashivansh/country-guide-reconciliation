import os


def load_env_file(path=".env"):
    """Load simple KEY=VALUE pairs from a local .env file without overwriting shell env."""
    if not os.path.exists(path):
        return

    with open(path, encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def database_path():
    return os.environ.get("COUNTRY_GUIDE_DB", "country_guides.db")


def groq_api_key():
    return os.environ.get("GROQ_API_KEY")


def groq_api_keys():
    """Return list of Groq API keys. Reads GROQ_API_KEYS (comma-separated) with GROQ_API_KEY as fallback."""
    multi = os.environ.get("GROQ_API_KEYS", "")
    keys = [k.strip().strip("'").strip('"') for k in multi.split(",") if k.strip()]
    if not keys and groq_api_key():
        keys = [groq_api_key()]
    return keys


def anthropic_api_key():
    return os.environ.get("ANTHROPIC_API_KEY")


def anthropic_api_keys():
    """Return list of Anthropic API keys. Reads ANTHROPIC_API_KEYS (comma-separated) with ANTHROPIC_API_KEY as fallback."""
    multi = os.environ.get("ANTHROPIC_API_KEYS", "")
    keys = [k.strip().strip("'").strip('"') for k in multi.split(",") if k.strip()]
    if not keys and anthropic_api_key():
        keys = [anthropic_api_key()]
    return keys


def extraction_chunk_size():
    return int(os.environ.get("EXTRACTION_CHUNK_SIZE", "6000"))


def official_sources_json_url():
    return os.environ.get("OFFICIAL_SOURCES_JSON_URL", "")


def slack_webhook_url():
    return os.environ.get("SLACK_WEBHOOK_URL", "")


def app_base_url():
    return os.environ.get("APP_BASE_URL", "http://localhost:5000").rstrip("/")


def sync_cron_schedule():
    """5-field cron expression controlling when the scheduled sync runs. Empty string disables it."""
    return os.environ.get("SYNC_CRON_SCHEDULE", "")


def groq_model():
    return os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")


def claude_model():
    return os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")


def gemini_api_key():
    return os.environ.get("GEMINI_API_KEY")


def gemini_api_keys():
    multi = os.environ.get("GEMINI_API_KEYS", "")
    keys = [k.strip().strip("'").strip('"') for k in multi.split(",") if k.strip()]
    if not keys and gemini_api_key():
        keys = [gemini_api_key()]
    return keys


def gemini_model():
    return os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")


def parser_version():
    return os.environ.get("PARSER_VERSION", f"groq/{groq_model()}/v1")


def ingestion_timeout():
    return int(os.environ.get("INGESTION_TIMEOUT", "30"))


def ingestion_max_retries():
    return int(os.environ.get("INGESTION_MAX_RETRIES", "2"))


def ingestion_strip_tags():
    default = "script,style,nav,footer,header,aside"
    return [t.strip() for t in os.environ.get("INGESTION_STRIP_TAGS", default).split(",")]


def ingestion_min_line_length():
    return int(os.environ.get("INGESTION_MIN_LINE_LENGTH", "30"))


def ingestion_max_content_length():
    return int(os.environ.get("INGESTION_MAX_CONTENT_LENGTH", "6000"))
