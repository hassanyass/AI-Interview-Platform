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
CMD ["sh", "-c", "alembic upgrade head && uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
