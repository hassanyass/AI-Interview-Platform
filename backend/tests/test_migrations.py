"""H4-A: the migration chain is reversible and agrees with the models.

Two failures these catch, both of which have happened in this project:
a revision whose ``downgrade()`` does not actually undo its ``upgrade()``
(found only when a deploy has to be rolled back), and a model changed
without a migration, so a fresh database and the live one differ.

The whole chain runs against the disposable test database (conftest.py
already rebuilt it from Alembic for this session); each test leaves it at
``head`` so the rest of the suite is unaffected.
"""
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from backend.db.session import AsyncSessionLocal, engine

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _alembic(*args: str) -> subprocess.CompletedProcess:
    """Exactly how the deploy and conftest run it: from backend/, inheriting
    the environment's (test) DATABASE_URL."""
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR, capture_output=True, text=True,
    )


def _head() -> str:
    result = _alembic("heads")
    assert result.returncode == 0, result.stderr
    return result.stdout.split()[0]


@pytest.mark.asyncio
async def test_the_last_revision_can_be_undone_and_reapplied():
    head = _head()

    down = _alembic("downgrade", "-1")
    assert down.returncode == 0, f"downgrade -1 failed:\n{down.stdout}\n{down.stderr}"

    async with AsyncSessionLocal() as db:
        current = (await db.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    assert current != head, "downgrade -1 left the database at head"

    up = _alembic("upgrade", "head")
    assert up.returncode == 0, f"re-upgrade failed:\n{up.stdout}\n{up.stderr}"

    async with AsyncSessionLocal() as db:
        restored = (await db.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    assert restored == head


@pytest.mark.asyncio
async def test_every_model_has_a_table_in_the_migrated_schema():
    """The cheap half of a drift check: a model added without a migration
    (or a table renamed in one place only) fails here. Alembic's own
    autogenerate diff is the exhaustive version; this needs no Alembic
    context and no network."""
    import backend.db.base  # noqa: F401 -- registers every model
    from backend.db.session import Base

    async with engine.connect() as conn:
        tables = set(await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names()))

    missing = sorted(t for t in Base.metadata.tables if t not in tables)
    assert not missing, f"models with no table in the migrated schema: {missing}"


@pytest.mark.asyncio
async def test_the_migrated_schema_has_no_extra_columns_for_the_models_it_shares():
    """The other half: a column added to a model but never migrated. Only
    tables the models own are compared -- Supabase's own `auth.*` and
    anything created outside Alembic are none of this test's business."""
    import backend.db.base  # noqa: F401
    from backend.db.session import Base

    async def columns_of(conn, table: str) -> set[str]:
        return {c["name"] for c in await conn.run_sync(lambda sc, t=table: inspect(sc).get_columns(t))}

    problems: list[str] = []
    async with engine.connect() as conn:
        present = set(await conn.run_sync(lambda sc: inspect(sc).get_table_names()))
        for name, table in Base.metadata.tables.items():
            if name not in present:
                continue                      # covered by the test above
            actual = await columns_of(conn, name)
            declared = {c.name for c in table.columns}
            for column in sorted(declared - actual):
                problems.append(f"{name}.{column} is on the model but not in the database")
    assert not problems, "model/schema drift:\n  " + "\n  ".join(problems)
