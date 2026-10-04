"""Static ratchet: ``allexport`` is decided at ONE write site (slot 1.16, C028).

``set -a`` used to be consumed only by ``ShellState.set_variable`` — the plain
assignment path — so the four declaration builtins (``declare``/``typeset``/
``local``/``readonly``) silently skipped the export and a child process never
received the value. The fix moved the decision into the ONE write door,
``psh/core/variable_store.py#VariableStore._allexport_attributes``, which every
whole-variable write crosses (``VariableStore.assign``).

This ratchet fails if production code anywhere outside that owner reads the
``allexport`` option again — a second reader is a second policy site, and the
next spelling to bypass it would regress C028. The scan is AST-based: only a
string constant ``'allexport'`` used as a subscript or call argument counts
(``options['allexport']``, ``options.get('allexport')``), so a docstring or
help text that merely names the option does not trip it. The scanner is
self-tested against a synthetic offender so it cannot rot into a no-op.

Allowlisted (not option READS that decide a write):
- ``psh/core/option_registry.py`` — defines the option.
- ``psh/core/variable_store.py`` — the owner.
"""

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
PSH = ROOT / "psh"
OWNER = PSH / "core" / "variable_store.py"
ALLOWLIST = {OWNER, PSH / "core" / "option_registry.py"}


def allexport_reads(source: str):
    """Return [(reason, lineno)] for every ``'allexport'`` string constant used
    as a subscript key or as a call argument in *source*."""
    tree = ast.parse(source)
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            key = node.slice
            if isinstance(key, ast.Constant) and key.value == "allexport":
                offenders.append(("options['allexport'] subscript read", node.lineno))
        elif isinstance(node, ast.Call):
            for arg in node.args:
                if isinstance(arg, ast.Constant) and arg.value == "allexport":
                    offenders.append(("options.get('allexport') call read", node.lineno))
    return offenders


def _production_files():
    return sorted(p for p in PSH.rglob("*.py") if p not in ALLOWLIST)


def test_allexport_is_read_only_by_the_write_door():
    """No production module outside the owner decides ``set -a`` (C028)."""
    offenders = {}
    for path in _production_files():
        found = allexport_reads(path.read_text())
        if found:
            offenders[str(path.relative_to(ROOT))] = found
    assert offenders == {}, (
        "a second allexport policy site appeared — route the write through "
        f"VariableStore.assign instead: {offenders}")


def test_owner_still_reads_the_option():
    """The ratchet is live: the owner itself is what reads ``allexport``."""
    assert allexport_reads(OWNER.read_text()), (
        "VariableStore no longer reads 'allexport' — the door lost its policy, "
        "or the owner moved; update ALLOWLIST/OWNER deliberately")


def test_scanner_flags_a_subscript_offender():
    src = (
        "def set_variable(self, name, value):\n"
        "    if self.options['allexport']:\n"
        "        attrs = EXPORT\n"
    )
    assert any("subscript" in r for r, _ in allexport_reads(src))


def test_scanner_flags_a_get_offender():
    src = "flag = shell.state.options.get('allexport', False)\n"
    assert any("call read" in r for r, _ in allexport_reads(src))


def test_scanner_ignores_mentions_in_docstrings_and_help_text():
    src = (
        '"""Under set -a (allexport) the variable is exported."""\n'
        "HELP = '  -a  Enable allexport (auto-export all variables)'\n"
    )
    assert allexport_reads(src) == []
