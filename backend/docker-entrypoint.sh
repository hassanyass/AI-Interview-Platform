#!/bin/sh
set -e
if [ "${RUN_MIGRATIONS_ON_START:-false}" = "true" ]; then
  echo "[entrypoint] RUN_MIGRATIONS_ON_START=true -> alembic upgrade head"
  alembic upgrade head
fi
# $PORT (Render-style) still wins over the CMD default when set.
if [ -n "$PORT" ] && [ "$1" = "uvicorn" ]; then
  exec uvicorn backend.main:app --host 0.0.0.0 --port "$PORT"
fi
exec "$@"
