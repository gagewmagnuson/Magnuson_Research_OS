"""Shared database connection infrastructure for the Research OS.

Environment-driven with a local development default (RD-009 portability):
  RESEARCH_OS_DATABASE_URL  overrides the connection string if set;
  otherwise defaults to the local `researchos` database.
"""
from __future__ import annotations
import os
import psycopg

DEFAULT_DSN = "dbname=researchos"


def dsn() -> str:
    """The connection string: env override, else local researchos default."""
    return os.environ.get("RESEARCH_OS_DATABASE_URL", DEFAULT_DSN)


def connect() -> psycopg.Connection:
    """Open a connection to the Research OS database.

    Caller owns the connection lifecycle. Use as a context manager:
        with connect() as conn:
            ...
    """
    return psycopg.connect(dsn())
