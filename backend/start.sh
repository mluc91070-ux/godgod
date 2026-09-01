#!/bin/sh
# Container entrypoint: migrate, then serve.
#
# This lives in a script rather than in a platform's "start command" field
# because those fields are not consistently run through a shell — Render splits
# them into argv, so `alembic upgrade head && uvicorn ...` arrives as arguments
# to alembic. A script is a shell either way.
set -e

echo "godgod: running migrations"
alembic upgrade head

# Idempotent: the memory store dedupes on a content hash, so a redeploy
# re-reads the file and stores nothing new. It never fails the boot — absent
# notes are a valid state and the loader says so.
echo "godgod: loading watchlist notes"
python -m app.workers.load_notes || echo "godgod: notes not loaded, continuing"

echo "godgod: starting api on port ${PORT:-8000}"
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
