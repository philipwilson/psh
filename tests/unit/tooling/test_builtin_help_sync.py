"""Meta-test: a builtin's declarative flag spec and its help text agree.

After the T3 ``parse_flags`` migration, each migrated builtin declares its
accepted options once, as the ``flags=``/``value_flags=`` arguments to
``self.parse_flags(...)`` / ``self.parse_flags_ordered(...)``. Help/synopsis
text, by contrast, is hand-written prose that drifted for years (the appraisal
counted five distinct scopes: ``unset``/``pwd``/``jobs``/... advertising or
omitting the wrong letters). This guard closes that drift class the same way
the option-registry meta-test closes shell-option drift: it reads the spec
straight from the source and cross-checks it against the rendered help, both
directions.

For every registered builtin whose class calls ``parse_flags`` /
``parse_flags_ordered`` with statically resolvable option letters:

  (a) every spec'd flag letter appears in the builtin's help/synopsis text, and
  (b) every ``-x`` the help advertises (in the synopsis or an ``Options:``
      block line) is in the spec — with a small, JUSTIFIED allowlist for
      letters handled OUTSIDE ``parse_flags`` (a special command form) and a
      pinned set of builtins whose spec is genuinely dynamic (built from a
      platform- or runtime-computed letter set, so it cannot be read
      statically).

The spec is extracted by a static AST walk of the builtin's own class source
(never by executing the builtin), resolving string constants, ``frozenset``/
``dict``/``set`` literals, ``''.join(self._ATTR)`` over a class-level literal,
and ``'lit' + name`` concatenations (the resolvable part; the rest marks the
spec dynamic). A guard-the-guard self-test drives two synthetic builtins with
deliberately mismatched spec/help and asserts BOTH directions are flagged.
"""

import ast
import inspect
import re
import textwrap

import psh.builtins  # noqa: F401 -- import triggers builtin registration
from psh.builtins.base import Builtin
from psh.builtins.registry import registry

_PARSE_METHODS = {'parse_flags', 'parse_flags_ordered'}

# ---------------------------------------------------------------------------
# Advertised letters that are legitimately NOT in a builtin's parse_flags spec.
# Each entry is (builtin_name, letter) -> reason. Keep every entry justified;
# test_allowlist_entries_are_live() fails if an entry stops being needed.
_ALLOWLIST = {
    ('jobs', 'x'): (
        "`jobs -x command [args]` is a special command form dispatched by "
        "JobsBuiltin._extract_x_command BEFORE the parse_flags('lnprs') walk, "
        "so -x is advertised in the synopsis but never a parse_flags option."
    ),
}

# Builtins whose parse_flags spec is computed at runtime and so cannot be read
# from source (the resolvable part is still checked for direction (a); direction
# (b) is skipped because the full letter set is not statically knowable). Pinned
# so a NEW dynamic-spec builtin is a deliberate addition, not a silent coverage
# hole.
_EXPECTED_DYNAMIC = {
    # ulimit's flag set is 'HSap' + the resource letters ACTIVE on this platform
    # (limits.py: ``'HSap' + active``), so it varies by OS.
    'ulimit',
}


# ---------------------------------------------------------------------------
# Static spec extraction.

def _resolve_letters(node, classdef):
    """Return (letters:set, fully_static:bool) for an AST *node*.

    fully_static is False when any part could not be resolved to a literal
    (e.g. a name referring to a runtime-computed string)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return set(node.value), True
    if isinstance(node, ast.Dict):
        letters, ok = set(), True
        for k in node.keys:
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                letters |= set(k.value)
            else:
                ok = False
        return letters, ok
    if isinstance(node, ast.Set):
        letters, ok = set(), True
        for e in node.elts:
            if isinstance(e, ast.Constant) and isinstance(e.value, str):
                letters |= set(e.value)
            else:
                ok = False
        return letters, ok
    if isinstance(node, ast.Call):
        fn = node.func
        if isinstance(fn, ast.Name) and fn.id == 'frozenset':
            return _resolve_letters(node.args[0], classdef) if node.args else (set(), True)
        if isinstance(fn, ast.Attribute) and fn.attr == 'join' and node.args:
            return _resolve_letters(node.args[0], classdef)
    if isinstance(node, ast.Attribute):
        # self._ATTR -> resolve a class-level literal assignment.
        if isinstance(node.value, ast.Name) and node.value.id == 'self':
            resolved = _resolve_class_attr(classdef, node.attr)
            if resolved is not None:
                return resolved
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, lok = _resolve_letters(node.left, classdef)
        right, rok = _resolve_letters(node.right, classdef)
        return left | right, lok and rok
    return set(), False


def _resolve_class_attr(classdef, attr_name):
    for node in classdef.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == attr_name:
                    return _resolve_letters(node.value, classdef)
    return None


def extract_spec(cls):
    """Return (letters:frozenset, dynamic:bool, found:bool) for *cls*.

    found is False when the class never calls a parse_flags helper (so the
    builtin is out of this guard's scope). dynamic is True when at least one
    flags/value_flags argument could not be resolved statically."""
    try:
        src = textwrap.dedent(inspect.getsource(cls))
    except (OSError, TypeError):
        return frozenset(), False, False
    classdef = ast.parse(src).body[0]
    found = False
    letters = set()
    dynamic = False
    for node in ast.walk(classdef):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in _PARSE_METHODS
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == 'self'):
            found = True
            for kw in node.keywords:
                if kw.arg in ('flags', 'value_flags'):
                    got, ok = _resolve_letters(kw.value, classdef)
                    letters |= got
                    if not ok:
                        dynamic = True
    return frozenset(letters), dynamic, found


# ---------------------------------------------------------------------------
# Advertised-letter extraction from help/synopsis text.

_SYNOPSIS_FLAG = re.compile(r'-([A-Za-z]+)')
_OPTION_LINE = re.compile(r'^\s{2,}-([A-Za-z])\b', re.M)


def advertised_flags(builtin):
    """Option letters a builtin advertises: those in its synopsis flag groups
    plus those beginning an indented ``Options:`` block line. Prose mentions
    (``case-insensitive``, ``set -o``) are deliberately NOT scanned — an
    ``Options:`` line and the synopsis are where a flag is formally advertised.
    """
    letters = set()
    for m in _SYNOPSIS_FLAG.finditer(builtin.synopsis):
        letters |= set(m.group(1))
    for m in _OPTION_LINE.finditer(builtin.help):
        letters |= set(m.group(1))
    return frozenset(letters)


def _spec_builtins():
    """Yield (name, builtin, letters, dynamic) for every registered builtin
    with a parse_flags spec."""
    for name in sorted(registry.names()):
        b = registry.get(name)
        letters, dynamic, found = extract_spec(type(b))
        if found:
            yield name, b, letters, dynamic


# ---------------------------------------------------------------------------
# The guard.

def test_every_spec_flag_is_advertised():
    """(a) Every spec'd flag letter appears in the builtin's help/synopsis."""
    violations = {}
    for name, b, spec, _dynamic in _spec_builtins():
        missing = spec - advertised_flags(b)
        if missing:
            violations[name] = ''.join(sorted(missing))
    assert not violations, (
        "Builtins whose parse_flags spec advertises option letters absent from "
        f"their help/synopsis text: {violations}. Document the flag in the "
        "builtin's synopsis or Options: block (help text is derived prose; the "
        "spec is the source of truth for what parses).")


def test_no_unspec_flag_advertised():
    """(b) Every advertised ``-x`` is in the spec (or the justified allowlist)."""
    violations = {}
    for name, b, spec, dynamic in _spec_builtins():
        if dynamic:
            continue  # full letter set unknown statically; see _EXPECTED_DYNAMIC
        extra = advertised_flags(b) - spec
        extra -= {letter for (bn, letter) in _ALLOWLIST if bn == name}
        if extra:
            violations[name] = ''.join(sorted(extra))
    assert not violations, (
        "Builtins whose help advertises an option their parse_flags spec does "
        f"not accept: {violations}. Either the help is stale (remove it) or the "
        "flag is handled outside parse_flags (add a justified _ALLOWLIST entry).")


def test_dynamic_spec_builtins_are_expected():
    """The set of dynamic-spec builtins is pinned, so a new one is deliberate."""
    dynamic = {name for name, _b, _spec, dyn in _spec_builtins() if dyn}
    assert dynamic == _EXPECTED_DYNAMIC, (
        f"Dynamic-spec builtins changed: got {dynamic}, expected "
        f"{_EXPECTED_DYNAMIC}. A dynamic spec is SKIPPED by check (b); if this "
        "is intended, update _EXPECTED_DYNAMIC (with a note on why the spec is "
        "runtime-computed), else make the spec statically resolvable.")


def test_allowlist_entries_are_live():
    """Every _ALLOWLIST entry names a letter that IS advertised-but-unspec'd."""
    by_name = {name: (b, spec) for name, b, spec, _d in _spec_builtins()}
    stale = []
    for (name, letter), _reason in _ALLOWLIST.items():
        if name not in by_name:
            stale.append((name, letter, "builtin has no parse_flags spec"))
            continue
        b, spec = by_name[name]
        if letter not in (advertised_flags(b) - spec):
            stale.append((name, letter, "no longer advertised-but-unspec'd"))
    assert not stale, f"Stale _ALLOWLIST entries (prune them): {stale}"


# ---------------------------------------------------------------------------
# Guard-the-guard: synthetic builtins with deliberately mismatched spec/help.
# (Not registered; extract_spec reads their source, advertised_flags reads
# their synopsis/help — neither executes them.)

class _GuardMissingBuiltin(Builtin):
    """Synthetic: spec has -z but the help never advertises it."""

    name = "guardmissing"

    @property
    def synopsis(self) -> str:
        return "guardmissing [-a]"

    def execute(self, args, shell) -> int:  # pragma: no cover - never run
        self.parse_flags(args, shell, flags='az')  # 'z' absent from help
        return 0


class _GuardExtraBuiltin(Builtin):
    """Synthetic: help advertises -q but the spec never accepts it."""

    name = "guardextra"

    @property
    def synopsis(self) -> str:
        return "guardextra [-a] [-q]"  # -q advertised

    def execute(self, args, shell) -> int:  # pragma: no cover - never run
        self.parse_flags(args, shell, flags='a')  # no 'q' in spec
        return 0


def test_guard_flags_missing_direction():
    """Self-test (a): a spec letter absent from help is flagged."""
    spec, dynamic, found = extract_spec(_GuardMissingBuiltin)
    assert found and not dynamic
    assert spec == frozenset('az')
    b = _GuardMissingBuiltin()
    assert (spec - advertised_flags(b)) == frozenset('z')


def test_guard_flags_extra_direction():
    """Self-test (b): a help-advertised flag absent from spec is flagged."""
    spec, dynamic, found = extract_spec(_GuardExtraBuiltin)
    assert found and not dynamic
    assert spec == frozenset('a')
    b = _GuardExtraBuiltin()
    assert (advertised_flags(b) - spec) == frozenset('q')


def test_guard_extracts_join_and_binop_specs():
    """Self-test for the resolver: real builtins exercise the tricky forms."""
    # read: flags=''.join(self._FLAG_OPTS), value_flags=''.join(self._ARG_OPTS)
    read_spec, read_dyn, read_found = extract_spec(type(registry.get('read')))
    assert read_found and not read_dyn
    assert frozenset('rsapdnNtu') <= read_spec
    # ulimit: 'HSap' + <runtime letters>  -> resolvable part static, rest dynamic
    u_spec, u_dyn, u_found = extract_spec(type(registry.get('ulimit')))
    assert u_found and u_dyn
    assert frozenset('HSap') <= u_spec
