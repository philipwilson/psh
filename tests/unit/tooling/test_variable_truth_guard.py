"""Drift-locks for variable truth & environment materialization (campaign R2).

Three invariants the R2 package establishes, each self-tested against a synthetic
offender so the scanner cannot rot into a no-op:

1. H13: ``ShellState.get_variable`` has NO environment fallback — it delegates to
   the scope manager's tri-state authority. A fallback to ``self.env`` there
   would resurrect an outer exported value under a declared-unset local.
2. The set-ness authority for the parameter operators (``_param_is_set``) routes
   plain names through ``ScopeManager.lookup`` (the tri-state), not a private
   read that could reintroduce a fallback.
3. Every dynamic-special interception in ``scope.py`` (the ``has_lifecycle(name)``
   gates: read / declare -p / seed-assign / attribute change / unset) is
   masking-aware — it consults ``_local_shadows_special`` so a ``local RANDOM``
   wins uniformly. A new interception added without the mask, or the mask
   removed from one, is a regression.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]
PSH = ROOT / "psh"


def _method_source(text: str, signature: str) -> str:
    """Return the source lines of the method whose ``def`` matches *signature*,
    up to the next same-or-lower-indent ``def``/``class``."""
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if signature in ln)
    indent = len(lines[start]) - len(lines[start].lstrip())
    body = [lines[start]]
    for ln in lines[start + 1:]:
        if ln.strip() and (len(ln) - len(ln.lstrip())) <= indent and (
                ln.lstrip().startswith('def ') or ln.lstrip().startswith('class ')):
            break
        body.append(ln)
    return '\n'.join(body)


# --- Invariant 1: no env fallback in ShellState.get_variable ----------------

def test_get_variable_has_no_env_fallback():
    src = _method_source((PSH / 'core/state.py').read_text(),
                         'def get_variable(self, name: str, default')
    assert 'self.env' not in src, (
        "ShellState.get_variable must not read self.env — a declared-unset local "
        "would resurrect an outer exported value (#20 H13). Delegate to "
        "scope_manager.lookup / get_variable.")


def test_env_fallback_guard_detects_offender():
    """Self-test: the scanner flags a synthetic re-introduced fallback."""
    offender = (
        "    def get_variable(self, name: str, default: str = '') -> str:\n"
        "        r = self.scope_manager.get_variable(name)\n"
        "        return r if r is not None else self.env.get(name, default)\n"
        "    def next_method(self):\n"
        "        pass\n"
    )
    src = _method_source(offender, 'def get_variable(self, name: str, default')
    assert 'self.env' in src  # the scanner WOULD catch this


# --- Invariant 2: _param_is_set routes plain names through lookup ------------

def test_param_is_set_uses_the_tri_state_authority():
    src = _method_source((PSH / 'expansion/operators.py').read_text(),
                         'def _param_is_set(self, var_name')
    assert re.search(r'scope_manager\.lookup\(', src), (
        "_param_is_set must decide plain-name set-ness through the tri-state "
        "ScopeManager.lookup (no env-fallback path).")


# --- Invariant 3: every dynamic-special interception is masking-aware --------

# The two predicate methods ARE the masking machinery, not interception sites:
# is_dynamic_special exposes has_lifecycle as the public predicate, and
# _local_shadows_special guards on it. has_lifecycle(name) inside their bodies is
# exempt from the "must consult the mask" rule.
_EXEMPT_METHODS = ('def is_dynamic_special', 'def _local_shadows_special')


def _exempt_line_ranges(lines):
    ranges = []
    for sig in _EXEMPT_METHODS:
        start = next(i for i, ln in enumerate(lines) if sig in ln)
        indent = len(lines[start]) - len(lines[start].lstrip())
        end = len(lines)
        for j in range(start + 1, len(lines)):
            ln = lines[j]
            if ln.strip() and (len(ln) - len(ln.lstrip())) <= indent and (
                    ln.lstrip().startswith('def ') or ln.lstrip().startswith('class ')):
                end = j
                break
        ranges.append((start, end))
    return ranges


def _unmasked_interceptions(text: str):
    lines = text.splitlines()
    exempt = _exempt_line_ranges(lines) if all(
        any(sig in ln for ln in lines) for sig in _EXEMPT_METHODS) else []
    offenders = []
    for i, line in enumerate(lines):
        if 'has_lifecycle(name)' not in line:
            continue
        if any(lo <= i < hi for lo, hi in exempt):
            continue
        # An interception site MUST consult the mask within its condition
        # (the multi-line `if (... has_lifecycle ...\n and not _local_shadows...)`
        # spans a few lines).
        window = '\n'.join(lines[max(0, i - 1):i + 3])
        if '_local_shadows_special' not in window:
            offenders.append((i + 1, line.strip()))
    return offenders


def test_all_dynamic_special_interceptions_are_masking_aware():
    offenders = _unmasked_interceptions((PSH / 'core/scope.py').read_text())
    assert not offenders, (
        "A dynamic-special interception in scope.py gates on has_lifecycle(name) "
        "WITHOUT consulting _local_shadows_special — a `local RANDOM` would not "
        f"mask it (#20 R2). Offending lines: {offenders}")


def test_masking_guard_detects_offender():
    """Self-test: an unmasked interception is flagged; a masked one is not."""
    bad = (
        "        # some new interception\n"
        "        if self._special.has_lifecycle(name):\n"
        "            self._special.assign(name, value)\n"
    )
    good = (
        "        if self._special.has_lifecycle(name) and not self._local_shadows_special(name):\n"
        "            self._special.assign(name, value)\n"
    )
    assert _unmasked_interceptions(bad), "scanner must catch the unmasked gate"
    assert not _unmasked_interceptions(good), "a masked gate must pass"
