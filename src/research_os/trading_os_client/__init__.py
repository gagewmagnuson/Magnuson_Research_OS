"""Client for the Trading OS read-only as_of HTTP contract (RD-001, RD-002).

This is the Research OS's ONE surface onto the Trading OS. It is a faithful
transport: it returns exactly what each endpoint reports — including the
`unresolved` symbol list from /v1/features and the row counts — and never
transforms missing, unresolved, or partial data into apparent success. Transport
and HTTP-status failures raise; they are never silently swallowed. All
completeness judgment happens downstream in the snapshot pull's four-tier checks,
which depend on this layer telling the whole truth.
"""