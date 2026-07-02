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



def groq_api_key():
    return os.environ.get("GROQ_API_KEY")


def groq_api_keys():
    raw = os.environ.get("GROQ_API_KEYS", "") or os.environ.get("GROQ_API_KEY", "")
    return [k.strip().strip("'").strip('"') for k in raw.split(",") if k.strip()]


def anthropic_api_key():
    return os.environ.get("ANTHROPIC_API_KEY")


def anthropic_api_keys():
    raw = os.environ.get("ANTHROPIC_API_KEYS", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    return [k.strip().strip("'").strip('"') for k in raw.split(",") if k.strip()]


def extraction_chunk_size():
    return int(os.environ.get("EXTRACTION_CHUNK_SIZE", "24000"))


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
    raw = os.environ.get("GEMINI_API_KEYS", "") or os.environ.get("GEMINI_API_KEY", "")
    return [k.strip().strip("'").strip('"') for k in raw.split(",") if k.strip()]


def gemini_model():
    return os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")


def ollama_model():
    return os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")


def ollama_base_url():
    return os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434")


def extraction_provider():
    return os.environ.get("EXTRACTION_PROVIDER", "").lower()


def azure_openai_api_key():
    return os.environ.get("OPENAI_AZURE_API_KEY", "")


def azure_openai_api_keys():
    raw = os.environ.get("OPENAI_AZURE_API_KEY", "")
    return [k.strip().strip("'").strip('"') for k in raw.split(",") if k.strip()]


def azure_openai_base_url():
    return os.environ.get("OPENAI_AZURE_URL", "")


def azure_openai_extraction_model():
    return os.environ.get("AZURE_OPENAI_EXTRACTION_MODEL", "gpt-4o")


def azure_openai_reconciliation_model():
    return os.environ.get("AZURE_OPENAI_RECONCILIATION_MODEL", "gpt-4o-mini")


def parser_version():
    custom = os.environ.get("PARSER_VERSION")
    if custom:
        return custom
    if azure_openai_base_url() and azure_openai_api_keys():
        return f"azure_openai/{azure_openai_extraction_model()}/v1"
    return f"groq/{groq_model()}/v1"


def ingestion_timeout():
    return int(os.environ.get("INGESTION_TIMEOUT", "30"))


def ingestion_max_retries():
    return int(os.environ.get("INGESTION_MAX_RETRIES", "2"))



def ingestion_max_content_length():
    return int(os.environ.get("INGESTION_MAX_CONTENT_LENGTH", "24000"))
