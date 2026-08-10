#!/usr/bin/env bash
# apply_migrations.sh — apply pending research.* migrations in order.
#
# Reads NNN_*.sql files in this directory in sorted order. 001_bootstrap.sql
# creates the research schema, deny_mutation(), and the schema_migration ledger,
# so from 001 onward the ledger always exists. For each file not yet recorded,
# applies it, then records it. Each apply+record is idempotent; the whole script
# is safe to re-run and safe on a fresh database.
#
# Usage:  ./apply_migrations.sh [dbname]     (default: researchos)
set -euo pipefail

DB="${1:-researchos}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Applying migrations to database: $DB"
echo "Migration directory: $DIR"

applied_count=0
skipped_count=0

for f in "$DIR"/[0-9][0-9][0-9]_*.sql; do
  fname="$(basename "$f")"

  # Is the ledger present yet? (False only before 001 runs on a fresh DB.)
  has_tracking=$(psql -d "$DB" -tAc \
    "select to_regclass('research.schema_migration') is not null;" 2>/dev/null || echo "f")

  # Skip if already recorded (only possible to check once the ledger exists).
  if [ "$has_tracking" = "t" ]; then
    already=$(psql -d "$DB" -tAc \
      "select exists(select 1 from research.schema_migration where filename = '$fname');")
    if [ "$already" = "t" ]; then
      echo "  skip   $fname (already applied)"
      skipped_count=$((skipped_count + 1))
      continue
    fi
  fi

  echo "  apply  $fname"
  # Apply the migration file in a single transaction; abort on any error.
  psql -d "$DB" -v ON_ERROR_STOP=1 --single-transaction -f "$f"

  # Record it (the ledger exists now — 001 created it, or it already existed).
  psql -d "$DB" -v ON_ERROR_STOP=1 \
    -c "insert into research.schema_migration (filename) values ('$fname') on conflict (filename) do nothing;"

  applied_count=$((applied_count + 1))
done

echo "Done. Applied: $applied_count, skipped: $skipped_count."
echo "Recorded migrations:"
psql -d "$DB" -tAc "select filename from research.schema_migration order by filename;" | sed 's/^/  /'
