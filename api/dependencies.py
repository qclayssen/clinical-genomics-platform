"""FastAPI dependency wiring.

Set CGP_DB_URL to point the API at a live Postgres instance (see
db/schema.sql). Unset (the default), the API serves the committed demo
fixtures — no external services required.
"""

from __future__ import annotations

import os
from functools import lru_cache

from api.repository import FixtureRepository, PostgresRepository, Repository


@lru_cache
def get_repository() -> Repository:
    dsn = os.environ.get("CGP_DB_URL")
    if dsn:
        return PostgresRepository(dsn)
    return FixtureRepository()
