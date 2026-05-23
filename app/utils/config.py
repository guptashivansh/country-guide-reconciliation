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


def extraction_chunk_size():
    return int(os.environ.get("EXTRACTION_CHUNK_SIZE", "6000"))


def official_sources_json_url():
    return os.environ.get(
        "OFFICIAL_SOURCES_JSON_URL",
        "https://raw.githubusercontent.com/guptashivansh/compliance-data/main/data/official-sources.json",
    )
