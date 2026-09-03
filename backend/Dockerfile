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

# Run Uvicorn
# Deployment-readiness audit (2026-09-02, docs/deployment-readiness.md):
# this referenced a nonexistent "app" package -- the real module is
# backend.main:app (backend/backend/main.py), matching how it's actually
# run in local dev (`uvicorn backend.main:app`, cwd = this backend/
# directory, which is exactly what rootDir: backend + COPY . . reproduce
# here). As written before this fix, the built image would crash on
# startup with ModuleNotFoundError.
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
