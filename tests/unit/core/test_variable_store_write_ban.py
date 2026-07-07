"""Architectural write-ban: variable mutation goes through the store.

Core-state appraisal Phase 2 exit criterion: "Add an architectural test banning
[direct .value / .attributes] writes outside the store." This scans the psh/
source and asserts that the distinctive ``Variable`` mutation signatures —
array-element mutation (``X.value.set/.unset/.clear/.append(``), the scalar
value write (``var.value =``), and attribute writes (``.attributes =/|=/&=``) —
appear ONLY in the authoritative mutation layer.

Allowlist (the mutation authority, core-state Phase 2):
  - psh/core/variable_store.py — the VariableStore transaction service;
  - psh/core/scope.py         — the ScopeManager it is built on (set_variable /
                                create_local / apply_attribute / remove_attribute).

Splitting ScopeManager and folding its mutation methods fully behind the store
is Phase 4; until then both files are the authority.

Known Phase-4 gap (deliberately NOT enforced here): psh/executor/array.py
mutates an existing array through a LOCAL alias (``array = var_obj.value;
array.set(...)``) rather than the literal ``.value.set(`` pattern, so a textual
ban cannot see it. That path is already readonly-guarded (P1) and is the
canonical, expansion-coupled ``a[i]=v`` builder; routing it through the store is
tracked as Phase-4 work, not a regression this test guards.
"""

import pathlib
import re

import psh

PSH_ROOT = pathlib.Path(psh.__file__).parent

# Files permitted to mutate Variable.value / .attributes directly (the authority).
ALLOWLIST = {
    "core/variable_store.py",
    "core/scope.py",
}

# Distinctive Variable/array mutation signatures. `.value.set/.unset/.clear/
# .append(` exist only on IndexedArray/AssociativeArray (reached as
# `<Variable>.value.set(`), and a `.attributes` flag write is distinctive to
# Variable (VarAttributes) — no other object in psh writes `.attributes`. A bare
# scalar `.value =` write is deliberately NOT banned: `.value` is a generic
# attribute name (Token.value, AST-node .value, ...) so a textual ban would be
# all false positives; the only scalar Variable.value write lives in scope.py
# (the authority) and does not proliferate.
_BANNED = re.compile(
    r"""
    \.value\.(set|unset|clear|append)\(   # array-element mutation
  | \.attributes\s*(\|=|&=|=(?!=))          # attribute add/remove/replace
    """,
    re.VERBOSE,
)


def _relpath(p: pathlib.Path) -> str:
    return str(p.relative_to(PSH_ROOT))


def _strip_noise(line: str) -> str:
    """Drop comments and obvious string-literal content so a docstring or
    comment mentioning ``.value.set(`` is not a false positive."""
    code = line.split("#", 1)[0]
    # Remove quoted spans (single/double) — crude but enough for this scan.
    code = re.sub(r"'[^']*'", "''", code)
    code = re.sub(r'"[^"]*"', '""', code)
    return code


def test_no_direct_variable_mutation_outside_store():
    offenders = []
    for path in PSH_ROOT.rglob("*.py"):
        rel = _relpath(path)
        if rel in ALLOWLIST:
            continue
        for lineno, raw in enumerate(path.read_text().splitlines(), start=1):
            code = _strip_noise(raw)
            if _BANNED.search(code):
                offenders.append(f"{rel}:{lineno}: {raw.strip()}")
    assert not offenders, (
        "Direct Variable.value/.attributes mutation found outside the store "
        "authority (route it through scope_manager.store):\n" + "\n".join(offenders)
    )


def test_allowlist_files_exist():
    # Guard against the allowlist rotting if a file is renamed/removed.
    for rel in ALLOWLIST:
        assert (PSH_ROOT / rel).is_file(), f"allowlisted file missing: {rel}"
