"""Configuration for reaching the Trading OS API. Env-driven with a local
development default, mirroring the Research OS DB config approach.

  TRADING_OS_BASE_URL  overrides the base URL (default http://localhost:8000)
  TRADING_OS_API_KEY   the Bearer key ('tos_...'); required — no default.
"""
from __future__ import annotations
import os
from dataclasses import dataclass

DEFAULT_BASE_URL = "http://localhost:8000"


class MissingApiKey(Exception):
    """Raised when TRADING_OS_API_KEY is not set. The client will not attempt
    unauthenticated calls."""


@dataclass(frozen=True)
class TradingOsConfig:
    base_url: str
    api_key: str

    @staticmethod
    def from_env() -> "TradingOsConfig":
        key = os.environ.get("TRADING_OS_API_KEY")
        if not key:
            raise MissingApiKey(
                "TRADING_OS_API_KEY is not set; the Trading OS client requires a "
                "Bearer key and will not make unauthenticated requests."
            )
        base = os.environ.get("TRADING_OS_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        return TradingOsConfig(base_url=base, api_key=key)