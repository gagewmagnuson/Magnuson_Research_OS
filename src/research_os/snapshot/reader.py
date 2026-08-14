"""Artifact reader: read staged snapshot Parquet back into the normalized
PulledData the completeness checks consume. This is what makes the checks validate
the ACTUAL persisted artifact (chain of custody), not the in-memory client results.

Reads only what the checks need — session-dates per security, member identity,
macro series presence — from the full staged data.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import polars as pl

from research_os.snapshot.model import (
    PulledData, BarsSeries, GoldSeries, UniverseMember, MacroSeries,
)
from research_os.snapshot.staging import (
    BARS_FILE, GOLD_FILE, UNIVERSE_FILE, MACRO_FILE,
)


def _as_date(v) -> date:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    return date.fromisoformat(str(v)[:10])


def _sessions_by_security(df: pl.DataFrame) -> dict[int, tuple[str | None, list[date]]]:
    """Group a bars/gold frame into {security_id: (symbol, sorted unique sessions)}."""
    out: dict[int, tuple[str | None, list[date]]] = {}
    if df.height == 0:
        return out
    for sid, sub in df.group_by("security_id"):
        sid_val = sid[0] if isinstance(sid, tuple) else sid
        symbol = sub["symbol"][0] if "symbol" in sub.columns and sub.height else None
        sessions = sorted({_as_date(x) for x in sub["session_date"].to_list()})
        out[int(sid_val)] = (symbol, sessions)
    return out


def read_pulled_data(staging_dir: Path, as_of: date, universe_code: str,
                     features_unresolved: list[str]) -> PulledData:
    """Read the staged artifact into the normalized representation for checks.

    features_unresolved is passed through from the pull (it is a property of the
    features RESPONSE, not persisted per-row), preserving the producer-transparency
    signal into tier-2 validation.
    """
    bars_df = pl.read_parquet(staging_dir / BARS_FILE)
    gold_df = pl.read_parquet(staging_dir / GOLD_FILE)
    univ_df = pl.read_parquet(staging_dir / UNIVERSE_FILE)
    macro_df = pl.read_parquet(staging_dir / MACRO_FILE)

    bars = [BarsSeries(sid, sym, sess)
            for sid, (sym, sess) in _sessions_by_security(bars_df).items()]
    gold = [GoldSeries(sid, sym, sess)
            for sid, (sym, sess) in _sessions_by_security(gold_df).items()]

    members = []
    if univ_df.height:
        for r in univ_df.iter_rows(named=True):
            members.append(UniverseMember(int(r["security_id"]), r.get("symbol")))

    macro = []
    if macro_df.height:
        for series_id, sub in macro_df.group_by("series_id"):
            sid_val = series_id[0] if isinstance(series_id, tuple) else series_id
            macro.append(MacroSeries(str(sid_val), sub.height))

    return PulledData(
        as_of=as_of, universe_code=universe_code,
        members=members, bars=bars, gold=gold, macro=macro,
        features_unresolved=features_unresolved,
    )