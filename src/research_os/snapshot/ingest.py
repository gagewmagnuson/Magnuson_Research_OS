"""Production snapshot ingest — pull ONE real immutable all-history snapshot from
the Trading OS and register it in research.snapshot (ARCHITECTURE §3, RD-002).

This is the real intake: full universe (requested_symbols=None), all history as
of the knowledge cutoff, registered for real (not rolled back). Closes the R0
gate's "a snapshot exists, is immutable, and is the sole data source read."

Usage:
  PYTHONPATH=src .venv/bin/python -m research_os.snapshot.ingest \
      --as-of 2026-08-13 --universe SP500 --macro CPIAUCSL

Run under caffeinate for the full pull (long, memory-intensive on small machines):
  caffeinate -is env PYTHONPATH=src TRADING_OS_API_KEY=tos_... \
      .venv/bin/python -m research_os.snapshot.ingest --as-of 2026-08-13
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

from research_os.trading_os_client.config import TradingOsConfig
from research_os.trading_os_client.client import TradingOsClient
from research_os.snapshot.model import SnapshotRequest
from research_os.snapshot.pull import (
    pull_snapshot, SnapshotPullAborted, SnapshotRegistrationError,
)

DEFAULT_SNAPSHOTS_ROOT = Path.home() / "Magnuson_Research_OS" / "snapshots"


def _code_sha() -> str:
    """The Research OS git commit (RD-011). The ingest itself is not a ledgered
    trial, but recording the producing commit in the manifest is good provenance."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parent
        ).decode().strip()
    except Exception:
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Production snapshot ingest.")
    ap.add_argument("--as-of", required=True,
                    help="Knowledge cutoff (YYYY-MM-DD). Use a date the Trading OS "
                         "has COMPLETE data for (not the current partial day).")
    ap.add_argument("--universe", default="SP500")
    ap.add_argument("--macro", action="append", default=None,
                    help="Macro series (repeatable). Default: ALL known series.")
    ap.add_argument("--feature", action="append", default=None,
                    help="feature name:version (repeatable). Default: ALL known features.")
    ap.add_argument("--snapshots-root", default=str(DEFAULT_SNAPSHOTS_ROOT))
    args = ap.parse_args(argv)

    as_of = date.fromisoformat(args.as_of)

    # Full production scope = ALL data the Trading OS currently has. These lists
    # are the complete known macro series and gold feature definitions; --macro
    # / --feature override them for dev slices. Keep in sync with the Trading OS
    # (macro.series and /v1/catalog/features) when it gains series/features.
    ALL_MACRO = [
        "BAMLH0A0HYM2", "CPIAUCSL", "DGS10", "DGS2", "DGS3MO", "FEDFUNDS",
        "GDPC1", "HOUST", "PAYEMS", "PPIACO", "T10Y2Y", "UNRATE",
    ]
    ALL_FEATURES = [
        {"name": "sma20", "version": 1},
        {"name": "sma50", "version": 1},
        {"name": "ema20", "version": 1},
        {"name": "log_return_1d", "version": 1},
        {"name": "return_1d", "version": 1},
        {"name": "realized_vol20", "version": 1},
        {"name": "roc20", "version": 1},
        {"name": "momentum_12_1", "version": 1},
    ]

    macro = args.macro or ALL_MACRO
    if args.feature:
        feats = [{"name": f.split(":")[0], "version": int(f.split(":")[1])}
                 for f in args.feature]
    else:
        feats = ALL_FEATURES

    request = SnapshotRequest(
        as_of=as_of, universe_code=args.universe,
        feature_versions=feats, macro_series=macro,
        requested_symbols=None,           # FULL universe — production intake
    )

    client = TradingOsClient(TradingOsConfig.from_env())
    root = Path(args.snapshots_root)
    root.mkdir(parents=True, exist_ok=True)

    print(f"[ingest] pulling FULL snapshot: universe={args.universe} as_of={as_of} "
          f"macro={macro} features={feats}")
    print(f"[ingest] snapshots root: {root}")
    print(f"[ingest] this pulls the full universe x full history — expect many "
          f"minutes and significant memory. Watch the Trading OS log for progress.\n")

    try:
        result = pull_snapshot(request, client, root, code_sha=_code_sha())
    except SnapshotPullAborted as e:
        from collections import Counter
        kinds = Counter(v.issue for v in e.violations)
        print(f"\n[ingest] ABORTED — completeness found {len(e.violations)} blocking "
              f"violation(s). Nothing registered.", file=sys.stderr)
        print(f"[ingest] by kind: {dict(kinds)}", file=sys.stderr)
        for v in e.violations[:20]:
            print(f"  {v.message}", file=sys.stderr)
        if len(e.violations) > 20:
            print(f"  ... and {len(e.violations) - 20} more", file=sys.stderr)
        return 2
    except SnapshotRegistrationError as e:
        print(f"\n[ingest] artifact assembled and hashed but registration FAILED. "
              f"Verified orphan retained at: {e.snapshot_path}", file=sys.stderr)
        print(f"[ingest] content_hash={e.content_hash}  cause={e.cause}", file=sys.stderr)
        return 3

    print(f"\n[ingest] SUCCESS")
    print(f"[ingest]   snapshot_id : {result.snapshot_id}")
    print(f"[ingest]   path        : {result.path}")
    print(f"[ingest]   content_hash: {result.content_hash}")
    print(f"[ingest]   warnings    : {len(result.warnings)}")
    for w in result.warnings[:10]:
        print(f"      - [{w.tier.value}/{w.issue}] {w.message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())