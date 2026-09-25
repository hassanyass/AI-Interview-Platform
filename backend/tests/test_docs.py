"""H6-B: the generated documentation cannot drift.

`docs/handover/env-matrix.md` and `docs/technical/data-model.md` are
produced from the code by `scripts/generate_docs.py`. Both were written by
hand before this, and both were wrong: the data model named three tables
that had never existed and omitted fifteen that did, while no document
listed the settings at all.

Generating them is only half the fix. These tests are the other half: they
fail when a setting or a table has changed without the checked-in files
being regenerated, and when a new setting arrives with no explanation of
what it is for. A stale handover document is worse than a missing one,
because somebody will trust it.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import generate_docs  # noqa: E402


def test_the_checked_in_documentation_matches_the_code():
    exit_code = generate_docs.main(["--check"])
    assert exit_code == 0, (
        "Generated documentation is out of date. Run: python scripts/generate_docs.py"
    )


@pytest.mark.parametrize("path, class_name", [
    ("backend/backend/core/config.py", "Settings"),
    ("agent/agent/config.py", "AgentSettings"),
])
def test_every_setting_says_what_it_is_for(path, class_name):
    """A setting with no docstring becomes a blank row in the env matrix,
    which is how a handover reader learns nothing from it."""
    undocumented = [
        setting.name
        for setting in generate_docs.read_settings(REPO / path, class_name)
        if not setting.doc
    ]
    assert not undocumented, (
        f"{len(undocumented)} setting(s) in {path} have no attribute docstring: "
        f"{', '.join(undocumented)}"
    )


def test_the_matrix_names_every_setting_and_marks_the_required_ones():
    matrix = (REPO / "docs" / "handover" / "env-matrix.md").read_text(encoding="utf-8")
    backend = generate_docs.read_settings(REPO / "backend/backend/core/config.py", "Settings")
    agent = generate_docs.read_settings(REPO / "agent/agent/config.py", "AgentSettings")

    for setting in backend + agent:
        assert f"`{setting.name}`" in matrix, f"{setting.name} is missing from the env matrix"

    # The four that have no default at all must be findable as such -- that
    # list is what someone provisioning a deployment reads first.
    for name in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "SUPABASE_JWKS_URL", "DATABASE_URL"):
        assert f"| `{name}` | `str` | **required** |" in matrix, f"{name} is no longer marked required"


def test_the_data_model_covers_every_table_the_models_declare():
    import backend.db.base  # noqa: F401 -- registers every model
    from backend.db.session import Base

    document = (REPO / "docs" / "technical" / "data-model.md").read_text(encoding="utf-8")
    missing = [name for name in Base.metadata.tables if f"## `{name}`" not in document]
    assert not missing, f"tables absent from the data model: {missing}"


def test_the_tables_holding_personal_data_are_marked():
    """`security.md` §3 promises this file marks them; if a table moves out
    of that set the two documents disagree silently."""
    document = (REPO / "docs" / "technical" / "data-model.md").read_text(encoding="utf-8")
    for name in ("candidate_profiles", "resumes", "interview_messages", "evaluations"):
        assert f"## `{name}` 🔒" in document, f"{name} is no longer marked as personal data"


def test_the_phase_zero_baseline_is_left_as_history():
    """`BASELINE_SCHEMA.md` records where the schema started (7 tables) and
    is deliberately not regenerated. If someone 'fixes' it, the project
    loses that record -- the generated data model is the current one."""
    baseline = (REPO / "docs" / "BASELINE_SCHEMA.md").read_text(encoding="utf-8")
    assert "Phase 0" in baseline
    assert generate_docs.BANNER not in baseline, "the baseline snapshot must not be generated"
