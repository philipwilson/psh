"""Meta-test: every psh source file is inside the mypy type-check scope.

Reappraisal #16 Tier-2 found that two packages enumerated their modules
file-by-file in ``[tool.mypy].files``, so campaign-added files
(``psh/builtins/loop_control.py``, ``psh/parser/recursive_descent/parsers/
base.py``) silently escaped the type gate. Both packages are now directory
entries; this test fails if any ``psh/**/*.py`` is not covered by some ``files``
entry, so a new module can never again slip out of the gate.
"""

import pathlib
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[3]


def _mypy_file_entries():
    with open(ROOT / "pyproject.toml", "rb") as f:
        cfg = tomllib.load(f)
    return [ROOT / e for e in cfg["tool"]["mypy"]["files"]]


def test_every_psh_source_file_is_type_checked():
    entries = _mypy_file_entries()
    missing = []
    for py in sorted((ROOT / "psh").rglob("*.py")):
        if "__pycache__" in py.parts:
            continue
        covered = any(
            py == entry or (entry.is_dir() and entry in py.parents)
            for entry in entries
        )
        if not covered:
            missing.append(py.relative_to(ROOT).as_posix())
    assert not missing, (
        "These psh source files are outside the mypy `files` scope in "
        "pyproject.toml — add a directory entry so new modules are checked "
        "automatically:\n  " + "\n  ".join(missing)
    )
