"""Ratchet: builtins use the ONE shared option walker, not hand-rolled scans
(campaign Q2, §13, "option walkers versus justified hand-written parsers").

``Builtin.parse_flags`` / ``Builtin.parse_flags_ordered`` (``psh/builtins/
base.py``) is the single getopt-style option walker. A builtin that scans its own
leading ``-x`` / ``+x`` options by hand (``arg.startswith('-')`` / ``'+'``) instead
of the walker is the anti-pattern — UNLESS its option grammar genuinely cannot be
expressed by the walker. This guard freezes the set of hand-rolling builtin
CLASSES; each carries a SPECIFIC reason its grammar is idiosyncratic, and the set
may only SHRINK (a class migrated to ``parse_flags`` drops out).

**Detector line.** It flags a ``Builtin``-subclass class whose body contains a
``<x>.startswith('-')`` / ``<x>.startswith('+')`` call — including the inline
TUPLE form ``startswith(('-', '+'))`` (Q2 nit-1) AND the NAME-BOUND tuple-constant
form ``SIGNS = ('-', '+'); arg.startswith(SIGNS)`` (CV closing verification: the
tuple-constant evasion class was proven live-exploitable in F5, so both the
inline and the module-constant spellings are now matched — a module-level name
bound to a ``('-','+')``-bearing tuple/list/set is resolved and treated as the
literal). Declared OUT OF SCOPE (no live instance; a heuristic broad enough would
false-positive on legitimate value checks): option-detection by INDEX-EQUALITY
(``arg[0] == '-'``), by whole EQUALITY (``arg == '-v'``), or by MEMBERSHIP
(``arg in ('--verbose', '-h')``) — ``printf``'s ``-v``, ``test``/``[``'s
operators, and the long-option-only debug builtins use those shapes, which are
not the getopt scan the walker replaces. Synthetic offenders (single, inline
tuple, name-bound tuple) prove the scan bites; a ``parse_flags`` user proves it
does not false-positive.
"""

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
BUILTINS = ROOT / "psh" / "builtins"


# (relpath, class) -> why the hand-rolled scan is justified. SHRINK-ONLY.
ALLOWLIST = {
    ("psh/builtins/directory_stack.py", "DirsBuiltin"):
        "`-N` index arguments collide with option letters and bash rejects "
        "clustering here (`dirs -lv` is 'invalid number'); the walker would "
        "parse MORE than bash",
    ("psh/builtins/directory_stack.py", "PopdBuiltin"):
        "only real option is `-n` (exact-match); `+N`/`-N` are rotation "
        "OPERANDS that collide with dash syntax",
    ("psh/builtins/directory_stack.py", "PushdBuiltin"):
        "only real option is `-n` (exact-match); `+N`/`-N` are rotation "
        "OPERANDS that collide with dash syntax",
    ("psh/builtins/env_command.py", "EnvBuiltin"):
        "bare `-` == `-i`, repeatable `-u NAME`/`-uNAME`, then `NAME=VALUE` "
        "assignments follow the options — a grammar the walker cannot express",
    ("psh/builtins/environment.py", "ExportBuiltin"):
        "POSIX-special: raises SpecialBuiltinUsageError(2) with NO usage line on "
        "a bad option — the walker prints usage and returns (None, args)",
    ("psh/builtins/environment.py", "SetBuiltin"):
        "`-o name`/`+o name` long options, `+eux` clusters, `--`, and "
        "positional-param assignment — the walker's explicit non-goal",
    ("psh/builtins/function_support.py", "DeclareBuiltin"):
        "`+x` attribute-REMOVAL grammar (declaration family): the walker has no "
        "`+flag` concept",
    ("psh/builtins/function_support.py", "ReadonlyBuiltin"):
        "declaration family: interleaves NAMEs before options and collects "
        "`-a`/`-A` into a forward list; `+`-attribute aware",
    ("psh/builtins/io.py", "EchoBuiltin"):
        "`echo` has NO `--` terminator; only `-neE` clusters and the first "
        "non-flag (incl. `--`) ends the scan — the walker cannot express "
        "'no `--`'",
    ("psh/builtins/job_control.py", "JobsBuiltin"):
        "uses parse_flags for `-lnprs`, then a second argv scan to recover the "
        "last-of-`-r`/`-s` ORDER the dict folds away, plus the `-x command` "
        "pre-scan",
    ("psh/builtins/kill_command.py", "KillBuiltin"):
        "`-SIGNAME`/`-9` are signal OPERANDS, not clusters; also `-s sig`/`-l`",
    ("psh/builtins/parse_tree.py", "ParseTreeBuiltin"):
        "long-option grammar (`-h/--help`, `-f/--format VALUE`, "
        "`-p/--positions`) the walker has no concept of; debug builtin",
    ("psh/builtins/positional.py", "GetoptsBuiltin"):
        "`getopts` IS the getopt engine — it parses `optstring name`, one option "
        "per call, via GetoptsState; it cannot consume itself",
    ("psh/builtins/print_builtin.py", "PrintBuiltin"):
        "zsh grammar: bare `-` ends options, `-R` REWRITES the recognized option "
        "set mid-walk, `-u`/`-f` take values",
    ("psh/builtins/shell_options.py", "ShoptBuiltin"):
        "custom usage text and the `-s`+`-u` mutual-exclusion; `-o` maps names "
        "to set-o options — a grammar with per-scan validation",
    ("psh/builtins/shell_state.py", "HistoryBuiltin"):
        "a numeric operand (`history 5`) conflates with option letters, and the "
        "error text / exit codes diverge from the walker's contract",
    ("psh/builtins/shell_state.py", "LocalBuiltin"):
        "`+x`/`+attr` attribute-removal grammar (declaration family) — the "
        "walker has no `+flag` concept",
}


def _is_builtin_subclass(classdef):
    """A class that (directly) subclasses something named ...Builtin."""
    for base in classdef.bases:
        name = (base.id if isinstance(base, ast.Name)
                else base.attr if isinstance(base, ast.Attribute) else "")
        if name.endswith("Builtin") or name == "Builtin":
            return True
    return False


def _is_leading_sign_arg(node):
    """True if *node* is a '-'/'+' Constant, or a Tuple/List/Set CONTAINING one
    (the ``startswith(('-', '+'))`` tuple form — Q2 nit-1)."""
    if isinstance(node, ast.Constant):
        return node.value in ("-", "+")
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return any(isinstance(e, ast.Constant) and e.value in ("-", "+")
                   for e in node.elts)
    return False


def _sign_tuple_names(tree):
    """Module-level names bound to a tuple/list/set constant containing '-'/'+'
    — the name-bound evasion ``SIGNS = ('-', '+'); a.startswith(SIGNS)``."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _is_leading_sign_arg(node.value):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    names.add(tgt.id)
        elif (isinstance(node, ast.AnnAssign) and node.value is not None
              and isinstance(node.target, ast.Name)
              and _is_leading_sign_arg(node.value)):
            names.add(node.target.id)
    return names


def _scans_leading_sign(classdef, sign_names=frozenset()):
    """True if the class body calls ``<x>.startswith('-'|'+')`` — a single
    constant, the inline ``startswith(('-', '+'))`` tuple, OR ``startswith(NAME)``
    where NAME is a module-level tuple constant bearing '-'/'+' (*sign_names*)."""
    for n in ast.walk(classdef):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "startswith" and n.args):
            arg = n.args[0]
            if _is_leading_sign_arg(arg) or (
                    isinstance(arg, ast.Name) and arg.id in sign_names):
                return True
    return False


def _live_hand_rollers():
    found = set()
    for path in sorted(BUILTINS.glob("*.py")):
        if path.name == "base.py":
            continue
        rel = f"psh/builtins/{path.name}"
        tree = ast.parse(path.read_text())
        sign_names = _sign_tuple_names(tree)
        for node in ast.walk(tree):
            if (isinstance(node, ast.ClassDef) and _is_builtin_subclass(node)
                    and _scans_leading_sign(node, sign_names)):
                found.add((rel, node.name))
    return found


def test_no_unjustified_hand_rolled_option_scanner():
    live = _live_hand_rollers()
    new = sorted(live - set(ALLOWLIST))
    assert not new, (
        "builtin class(es) hand-rolling a getopt-style `-x`/`+x` option scan. "
        "Use self.parse_flags / self.parse_flags_ordered (base.py), or — if the "
        "option grammar genuinely cannot be expressed by the walker — add the "
        f"class to ALLOWLIST with a SPECIFIC reason:\n  {new}")


def test_ratchet_only_shrinks():
    live = _live_hand_rollers()
    stale = sorted(set(ALLOWLIST) - live)
    assert not stale, (
        "ALLOWLIST classes that no longer hand-scan options (migrated to the "
        f"walker, or renamed) — prune them (the ratchet only shrinks):\n  {stale}")


def test_every_allowlist_entry_has_specific_justification():
    for key, reason in ALLOWLIST.items():
        assert isinstance(reason, str) and len(reason.strip()) >= 30, (
            f"ALLOWLIST entry {key} needs a specific justification (not "
            "'pre-existing')")


def test_canonical_walker_exists():
    """The shared walker the ratchet routes toward is present."""
    src = (BUILTINS / "base.py").read_text()
    assert "def parse_flags_ordered(" in src
    assert "def parse_flags(" in src


# --- synthetic offenders -----------------------------------------------------

def test_offender_hand_rolled_scanner_is_flagged():
    """A new builtin scanning `-x` options by hand is detected."""
    src = (
        "class FooBuiltin(Builtin):\n"
        "    def execute(self, args, shell):\n"
        "        for arg in args[1:]:\n"
        "            if arg.startswith('-'):\n"
        "                pass\n"
    )
    cd = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ClassDef))
    assert _is_builtin_subclass(cd) and _scans_leading_sign(cd)


def test_offender_plus_scanner_is_flagged():
    src = (
        "class BarBuiltin(Builtin):\n"
        "    def m(self, a):\n"
        "        return a.startswith('+')\n"
    )
    cd = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ClassDef))
    assert _scans_leading_sign(cd)


def test_offender_tuple_startswith_is_flagged():
    """Q2 nit-1: the inline tuple-constant startswith evasion is caught."""
    src = (
        "class BazBuiltin(Builtin):\n"
        "    def m(self, a):\n"
        "        return a.startswith(('-', '+'))\n"
    )
    cd = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ClassDef))
    assert _scans_leading_sign(cd)


def test_offender_name_bound_tuple_startswith_is_flagged():
    """CV closing verification: the NAME-BOUND tuple-constant evasion
    ``SIGNS = ('-', '+'); a.startswith(SIGNS)`` is resolved and caught (and does
    not misfire on a name bound to an unrelated tuple)."""
    src = (
        "SIGNS = ('-', '+')\n"
        "PLAIN = ('x', 'y')\n"
        "class QuxBuiltin(Builtin):\n"
        "    def m(self, a):\n"
        "        return a.startswith(SIGNS)\n"
    )
    tree = ast.parse(src)
    sign_names = _sign_tuple_names(tree)
    assert sign_names == {"SIGNS"}
    cd = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
    assert _scans_leading_sign(cd, sign_names)
    # A class using the unrelated PLAIN constant is NOT flagged.
    src2 = ("class OkBuiltin(Builtin):\n"
            "    def m(self, a):\n        return a.startswith(PLAIN)\n")
    cd2 = next(n for n in ast.walk(ast.parse(src2)) if isinstance(n, ast.ClassDef))
    assert not _scans_leading_sign(cd2, sign_names)


def test_walker_user_is_not_flagged():
    """A builtin using parse_flags (and no leading-sign scan) is not flagged."""
    src = (
        "class GoodBuiltin(Builtin):\n"
        "    def execute(self, args, shell):\n"
        "        opts, operands = self.parse_flags(args, shell, flags='ab')\n"
        "        return 0\n"
    )
    cd = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ClassDef))
    assert _is_builtin_subclass(cd) and not _scans_leading_sign(cd)
