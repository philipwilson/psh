"""Guard: builtins must not raw-``print(..., file=...std...)``.

Builtins have forked-child-aware base-class output helpers
(``self.write()`` / ``self.write_line()`` for stdout, ``self.error()`` /
``self.write_error_line()`` for stderr — see ``psh/builtins/base.py`` and
the error-channel convention in ``psh/builtins/CLAUDE.md``). A raw
``print(..., file=shell.stdout)`` / ``print(..., file=shell.stderr)``
bypasses that contract: in a forked child (pipeline member, background
job) the helpers write at the fd level so dup2-based redirections apply,
whereas a raw print to the Python-level stream is not guaranteed to honor
fd-level redirection and skips the helpers' flush discipline.

This test scans the builtins source and fails if any such raw print
reappears, so the v0.284 convention does not silently regress.

``base.py`` itself is exempt: ``error()`` is *defined* there in terms of
``print(..., file=stderr)`` (the single sanctioned implementation that
every builtin routes through).
"""

import re
from pathlib import Path

import pytest

BUILTINS_DIR = Path(__file__).resolve().parents[3] / "psh" / "builtins"

# Matches print(..., file=<anything>std<anything>) e.g.
#   print(x, file=shell.stdout)
#   print(x, file=self.shell.stderr)
#   print(x, file=sys.stdout)
RAW_PRINT_RE = re.compile(r"\bprint\s*\([^)]*\bfile\s*=\s*[^)]*std(?:out|err)")

# base.py defines the one sanctioned print() (inside error()).
EXEMPT = {"base.py"}


def _builtin_sources():
    return sorted(p for p in BUILTINS_DIR.glob("*.py") if p.name not in EXEMPT)


def test_builtins_dir_exists():
    assert BUILTINS_DIR.is_dir(), BUILTINS_DIR


@pytest.mark.parametrize(
    "path", _builtin_sources(), ids=lambda p: p.name
)
def test_no_raw_print_to_std_stream(path):
    offenders = []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        if RAW_PRINT_RE.search(line):
            offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Builtins must use base-class output helpers (self.write_line / "
        "self.error / self.write_error_line), not raw print(..., file=...std...). "
        "Offending lines:\n" + "\n".join(offenders)
    )
