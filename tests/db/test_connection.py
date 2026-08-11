"""B1: prove the connection helper connects and sees the research schema."""
from research_os.db import connect, dsn


def test_dsn_defaults_to_local_researchos():
    # With no env override, we target the local researchos database.
    assert "researchos" in dsn()


def test_connect_runs_trivial_query():
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("select 1")
            assert cur.fetchone()[0] == 1


def test_connection_sees_research_schema():
    # Proves we're connected to the right DB: the migration ledger exists
    # and holds the 14 migrations we applied.
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from research.schema_migration")
            assert cur.fetchone()[0] == 14
