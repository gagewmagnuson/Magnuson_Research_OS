-- seed_known_no_data.sql
-- Governance facts for research.known_no_data_security (migration 015).
--
-- These are DATA, not schema — the migration creates the table; this seed
-- reinstates the recorded governance decisions after a DB rebuild. Idempotent
-- via ON CONFLICT (the unique(security_id, universe_code) constraint), so it is
-- safe to re-run. Recording/altering these is a human governance act; edit this
-- file only as a deliberate, reviewed decision.
--
-- SP500 ever-members with no available price data (Tiingo does not carry them),
-- kept in the membership history (survivorship-correct) but exempt from the
-- member-must-have-bars completeness rule as accepted governed exceptions.
insert into research.known_no_data_security
    (security_id, universe_code, reason, source, recorded_by)
values
    (716, 'SP500',
     'no Tiingo price data available (Meredith Corp, delisted 2021-12-01)',
     'Tiingo', 'human:gage'),
    (748, 'SP500',
     'no Tiingo price data available (NYSE Euronext, delisted 2013-11-12; before Tiingo delisted-coverage window)',
     'Tiingo', 'human:gage')
on conflict (security_id, universe_code) do nothing;