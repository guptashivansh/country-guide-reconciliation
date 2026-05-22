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


def extraction_chunk_size():
    return int(os.environ.get("EXTRACTION_CHUNK_SIZE", "6000"))
