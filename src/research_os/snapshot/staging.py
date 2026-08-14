"""Staging writer: persist pulled client results to a snapshot directory as
domain-partitioned Parquet (one file per domain). A snapshot is immutable and
written once, so no monthly partitioning is needed — a static, domain-partitioned
layout is the simplest correct form and what the R1 engine reads.

This writes the FULL data (all bar/feature/observation fields) — research consumes
everything; the completeness reader later extracts just the coverage view.
"""
from __future__ import annotations

from pathlib import Path
import polars as pl

from research_os.trading_os_client.client import (
    BarsResult, FeaturesResult, UniverseResult, MacroResult,
)

BARS_FILE = "bars.parquet"
GOLD_FILE = "gold.parquet"
UNIVERSE_FILE = "universe.parquet"
MACRO_FILE = "macro.parquet"


def _write(df: pl.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(path)


def write_bars(results: list[BarsResult], staging_dir: Path) -> Path:
    """Flatten per-symbol BarsResults into one bars.parquet. Identity
    (security_id, symbol) is denormalized onto every row for the snapshot."""
    rows = []
    for r in results:
        for b in r.bars:
            rows.append({
                "security_id": r.security_id, "symbol": r.symbol,
                "session_date": b["session_date"],
                "open": b["open"], "high": b["high"], "low": b["low"],
                "close": b["close"], "volume": b["volume"],
                "knowledge_time": b["knowledge_time"],
            })
    bars_schema = {
        "security_id": pl.Int64, "symbol": pl.Utf8, "session_date": pl.Utf8,
        "open": pl.Float64, "high": pl.Float64, "low": pl.Float64,
        "close": pl.Float64, "volume": pl.Int64, "knowledge_time": pl.Utf8,
    }
    df = pl.DataFrame(rows, schema=bars_schema) if rows else pl.DataFrame(schema=bars_schema)
    path = staging_dir / BARS_FILE
    _write(df, path)
    return path


def write_gold(result: FeaturesResult, staging_dir: Path,
               symbol_by_secid: dict[int, str] | None = None) -> Path:
    """Write the gold feature rows. The /v1/features rows are data-only (identity
    is on the envelope per row via the reader), so we carry security_id/symbol
    from the row if present, else map via symbol_by_secid."""
    feature_cols = ["adj_close", "adj_volume", "return_1d", "log_return_1d",
                    "sma20", "sma50", "ema20", "realized_vol20", "roc20",
                    "momentum_12_1", "knowledge_time"]
    rows = []
    for row in result.rows:
        rows.append({
            "security_id": row.get("security_id"),
            "symbol": row.get("symbol"),
            "session_date": row["session_date"],
            **{c: row.get(c) for c in feature_cols},
        })
    gold_schema = {
        "security_id": pl.Int64, "symbol": pl.Utf8, "session_date": pl.Utf8,
        "adj_close": pl.Float64, "adj_volume": pl.Int64,
        "return_1d": pl.Float64, "log_return_1d": pl.Float64,
        "sma20": pl.Float64, "sma50": pl.Float64, "ema20": pl.Float64,
        "realized_vol20": pl.Float64, "roc20": pl.Float64,
        "momentum_12_1": pl.Float64, "knowledge_time": pl.Utf8,
    }
    # Pass the schema explicitly in BOTH cases. During a security's warm-up period
    # (early history), feature columns are None until enough sessions exist; if we
    # let polars infer types from the first rows, an all-None warm-up column is
    # typed Null and later float values fail to append. An explicit schema fixes
    # the types regardless of warm-up nulls. (This surfaced only once we began
    # pulling full history per ARCHITECTURE §3, not windowed slices.)
    df = pl.DataFrame(rows, schema=gold_schema) if rows else pl.DataFrame(schema=gold_schema)
    path = staging_dir / GOLD_FILE
    _write(df, path)
    return path


def write_universe(result: UniverseResult, staging_dir: Path) -> Path:
    rows = [{"security_id": m["security_id"], "symbol": m.get("symbol")}
            for m in result.members]
    df = pl.DataFrame(rows) if rows else pl.DataFrame(
        schema={"security_id": pl.Int64, "symbol": pl.Utf8})
    path = staging_dir / UNIVERSE_FILE
    _write(df, path)
    return path


def write_macro(results: list[MacroResult], staging_dir: Path) -> Path:
    rows = []
    for r in results:
        for o in r.observations:
            rows.append({
                "series_id": r.series_id, "obs_date": o["obs_date"],
                "value": o["value"], "vintage_date": o["vintage_date"],
            })
    df = pl.DataFrame(rows) if rows else pl.DataFrame(
        schema={"series_id": pl.Utf8, "obs_date": pl.Utf8, "value": pl.Utf8,
                "vintage_date": pl.Utf8})
    path = staging_dir / MACRO_FILE
    _write(df, path)
    return path