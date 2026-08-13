"""The Trading OS HTTP client — faithful transport over the four snapshot domains.

Each method returns the endpoint's response as a typed result that preserves ALL
reported fields (counts, and critically the /v1/features `unresolved` list). HTTP
errors and transport failures raise TradingOsHttpError / TradingOsTransportError;
nothing partial is returned as success. No completeness logic lives here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
import json
import urllib.parse
import urllib.request
import urllib.error

from research_os.trading_os_client.config import TradingOsConfig


class TradingOsError(Exception):
    """Base for all client errors."""


class TradingOsHttpError(TradingOsError):
    """Non-2xx HTTP response. Carries status and body for diagnosis."""
    def __init__(self, status: int, url: str, body: str):
        self.status = status
        self.url = url
        self.body = body
        super().__init__(f"HTTP {status} from {url}: {body[:300]}")


class TradingOsTransportError(TradingOsError):
    """Connection/timeout/other transport failure (no HTTP status)."""


# --- typed results: each preserves exactly what the endpoint reports ----------

@dataclass(frozen=True)
class BarsResult:
    symbol: str
    security_id: int
    as_of: str
    count: int
    bars: list[dict[str, Any]]


@dataclass(frozen=True)
class FeaturesResult:
    as_of: str
    symbols: list[str] | None
    unresolved: list[str]          # PRESERVED — tier-2 completeness depends on it
    count: int
    rows: list[dict[str, Any]]


@dataclass(frozen=True)
class UniverseResult:
    index: str
    as_of: str
    count: int
    members: list[dict[str, Any]]


@dataclass(frozen=True)
class MacroResult:
    series_id: str
    as_of: str
    count: int
    observations: list[dict[str, Any]]


class TradingOsClient:
    def __init__(self, config: TradingOsConfig, timeout: float = 60.0):
        self._config = config
        self._timeout = timeout

    # --- low-level GET: returns parsed JSON, or raises. No partial success. ---
    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = self._config.base_url + path
        if params:
            # Repeatable params (e.g. symbols) expressed as list values.
            url += "?" + urllib.parse.urlencode(params, doseq=True)
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {self._config.api_key}")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read().decode()
        except urllib.error.HTTPError as e:
            raise TradingOsHttpError(e.code, url, e.read().decode()) from e
        except urllib.error.URLError as e:
            raise TradingOsTransportError(f"transport failure for {url}: {e}") from e
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise TradingOsError(f"non-JSON response from {url}: {raw[:300]}") from e

    @staticmethod
    def _fmt(d: date | str | None) -> str | None:
        return d.isoformat() if isinstance(d, date) else d

    # --- the four domains -----------------------------------------------------

    def bars(self, symbol: str, as_of: date | str,
             start: date | str | None = None, end: date | str | None = None,
             adjustment: str | None = None) -> BarsResult:
        params: dict[str, Any] = {"as_of": self._fmt(as_of)}
        if start is not None: params["start"] = self._fmt(start)
        if end is not None: params["end"] = self._fmt(end)
        if adjustment is not None: params["adjustment"] = adjustment
        d = self._get(f"/v1/bars/{urllib.parse.quote(symbol)}", params)
        return BarsResult(symbol=d["symbol"], security_id=d["security_id"],
                          as_of=d["as_of"], count=d["count"], bars=d["bars"])

    def features(self, as_of: date | str, symbols: list[str] | None = None,
                 start: date | str | None = None, end: date | str | None = None) -> FeaturesResult:
        params: dict[str, Any] = {"as_of": self._fmt(as_of)}
        if start is not None: params["start"] = self._fmt(start)
        if end is not None: params["end"] = self._fmt(end)
        if symbols: params["symbols"] = symbols
        d = self._get("/v1/features", params)
        # unresolved is preserved verbatim; if the server omits it, that is itself
        # a contract violation, so default to a sentinel that will fail loudly
        # downstream rather than a silent empty list.
        return FeaturesResult(
            as_of=d["as_of"], symbols=d.get("symbols"),
            unresolved=d["unresolved"],          # KeyError if absent — intentional
            count=d["count"], rows=d["rows"],
        )

    def universe(self, index: str, as_of: date | str) -> UniverseResult:
        d = self._get(f"/v1/universe/{urllib.parse.quote(index)}",
                      {"as_of": self._fmt(as_of)})
        return UniverseResult(index=d["index"], as_of=d["as_of"],
                              count=d["count"], members=d["members"])

    def macro(self, series: str, as_of: date | str) -> MacroResult:
        d = self._get(f"/v1/macro/{urllib.parse.quote(series)}",
                      {"as_of": self._fmt(as_of)})
        return MacroResult(series_id=d["series_id"], as_of=d["as_of"],
                           count=d["count"], observations=d["observations"])