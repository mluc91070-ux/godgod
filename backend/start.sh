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

echo "godgod: starting api on port ${PORT:-8000}"
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
