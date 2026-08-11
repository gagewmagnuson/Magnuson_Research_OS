"""Ledger subsystem: the reproducibility contract and the trial entry point.

RD-003: the tuple is the only entry point to ledgered evaluation, and every
identifier in it must resolve to a real, versioned, append-only row before a
trial is accepted.
"""
