"""Shim (H3): `python scripts/make_admin.py <email>` now runs
`python -m backend.cli make-admin <email>`. The logic lives in
backend/backend/cli.py and uses the application's own services."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from backend.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["make-admin", *sys.argv[1:2]]))
