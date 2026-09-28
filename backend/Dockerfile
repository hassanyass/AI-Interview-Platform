FROM python:3.13-slim
# Aligned to 3.13 (2026-09-03): the pinned requirements.txt lockfile was
# generated against the local dev environment's actual Python 3.13.5 --
# building against 3.12 risked a dependency that only ships 3.13 wheels,
# or subtly different resolved behavior. See docs/deployment-readiness.md.

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Run migrations, then Uvicorn.
# Deployment-readiness audit (2026-09-02, docs/deployment-readiness.md):
# this referenced a nonexistent "app" package -- the real module is
# backend.main:app (backend/backend/main.py), matching how it's actually
# run in local dev (`uvicorn backend.main:app`, cwd = this backend/
# directory, which is exactly what rootDir: backend + COPY . . reproduce
# here). As written before this fix, the built image would crash on
# startup with ModuleNotFoundError.
#
# Migrations moved here (2026-09-03) from render.yaml's preDeployCommand:
# confirmed against Render's own docs that Pre-Deploy Command is "available
# for paid web services, private services, and background workers" only --
# NOT the Free instance type this deployment uses. Running `alembic upgrade
# head` here instead means it executes on every container start regardless
# of plan, and (matching preDeployCommand's original fail-closed behavior)
# a failed migration makes `&&` fail so the container never starts serving
# with a stale/mismatched schema.
# H2-B: migrations no longer run on every container start -- N replicas
# would race on the same migration. The normal path is the one-shot
# `migrate` service (docker-compose.yml) or `alembic upgrade head` in the
# deploy pipeline. RUN_MIGRATIONS_ON_START=true restores the old behaviour
# for a single-instance deploy that has no pre-deploy hook (fails closed:
# a failed migration still stops the container from serving).
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# H5-C: not root. Nothing here writes to disk -- logs go to stdout and
# migrations only touch the database -- so an unprivileged user needs no
# writable paths, and a process that never needs root should not have it.
RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app

# The image says how to check itself, so an orchestrator that is not this
# repo's compose file still knows. /ready reports the database too (H2-B);
# /health would only say the process is alive.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,sys,urllib.request; sys.exit(0 if urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('PORT','8000')}/ready\", timeout=4).status == 200 else 1)"

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
