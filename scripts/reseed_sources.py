#!/usr/bin/env python3
"""Re-import data/official-sources.json into the source registry tables.

Usage:
    python3 scripts/reseed_sources.py          # default path
    python3 scripts/reseed_sources.py path.json # custom path
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.config import load_env_file, official_sources_json_url
from app.repositories.source_endpoint_repository import TrustedSourceEndpointRepository
from app.utils.db import Database

load_env_file()

json_path = sys.argv[1] if len(sys.argv) > 1 else None
db = Database()
repo = TrustedSourceEndpointRepository(db, json_url=official_sources_json_url())

repo.initialize_schema()
repo.reseed_from_file(json_path or "")

stats = repo.get_registry_stats()
print(f"Reseeded: {stats['countries']} countries, {stats['authorities']} authorities, "
      f"{stats['endpoints']} endpoints, {stats['parsers']} parsers")
