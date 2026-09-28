"""The lock files must be installable together.

`make install` and CI both do this:

    pip install -r backend/requirements.txt -r agent/requirements.txt -r requirements-dev.txt

One environment, three files -- the test suite imports both `backend` and
`agent` in the same process, so it has to be one environment. The two locks
were compiled independently, which let their shared transitive dependencies
drift apart: by 2026-09-25, eleven of them disagreed and pip refused the
install outright with `ResolutionImpossible` on `anyio`.

Nothing caught it for weeks because every developer's virtualenv predated
the drift and was only ever added to. It took the first real CI run, on a
clean machine, to surface it -- which is the argument for having a clean
machine in the loop, and the argument for this test, which costs
milliseconds and fails on the file rather than after a two-minute install.
"""
import collections
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
LOCKS = (
    "backend/requirements.txt",
    "agent/requirements.txt",
    "requirements-dev.txt",
)
PIN = re.compile(r"^([A-Za-z0-9._-]+)==([^\s;]+)")


def read_pins(relative: str) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in (REPO / relative).read_text(encoding="utf-8").splitlines():
        match = PIN.match(line.split("#")[0].strip())
        if match:
            # Normalised the way pip does, so Foo_Bar and foo-bar are one name.
            pins[match.group(1).lower().replace("_", "-")] = match.group(2)
    return pins


def test_no_package_is_pinned_to_two_different_versions():
    versions: dict[str, dict[str, str]] = collections.defaultdict(dict)
    for lock in LOCKS:
        for package, version in read_pins(lock).items():
            versions[package][lock] = version

    conflicts = {
        package: where for package, where in versions.items()
        if len(set(where.values())) > 1
    }
    assert not conflicts, (
        "These packages are pinned to different versions across the lock files, so "
        "`pip install -r ... -r ... -r ...` cannot resolve:\n"
        + "\n".join(
            f"  {package}: " + ", ".join(f"{version} ({lock})" for lock, version in sorted(where.items()))
            for package, where in sorted(conflicts.items())
        )
        + "\n\nRegenerate with `make lock`, which compiles the agent first and "
          "constrains the backend to its result."
    )


@pytest.mark.parametrize("lock", LOCKS)
def test_every_lock_file_is_pinned_exactly(lock):
    """A range in a lock file means two machines can install different code.
    `requirements-dev.txt` is hand-written, so this applies to it too."""
    loose = []
    for raw in (REPO / lock).read_text(encoding="utf-8").splitlines():
        line = raw.split("#")[0].strip()
        if not line or line.startswith("-"):
            continue
        if not PIN.match(line):
            loose.append(line)
    assert not loose, f"{lock} has unpinned requirement(s): {loose}"


def test_the_locks_cover_what_the_inputs_ask_for():
    """Every top-level name in a `.in` file appears in its compiled lock. A
    missing one means the lock was compiled before the input changed."""
    for source, lock in (("backend/requirements.in", "backend/requirements.txt"),
                         ("agent/requirements.in", "agent/requirements.txt")):
        pins = read_pins(lock)
        missing = []
        for line in (REPO / source).read_text(encoding="utf-8").splitlines():
            name = line.split("#")[0].strip()
            if not name or name.startswith("-"):
                continue
            # Strip extras and any version marker: `uvicorn[standard]>=1` -> `uvicorn`
            base = re.split(r"[\[<>=!;]", name)[0].strip().lower().replace("_", "-")
            if base and base not in pins:
                missing.append(base)
        assert not missing, f"{lock} is missing {missing} from {source} — run `make lock`"
