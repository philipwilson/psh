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


# --- Invariant 1b: consumer reads of PATH/CDPATH use the VARIABLE (CV2) ------
#
# PATH/CDPATH carry VARIABLE semantics: a consumer that decides command search
# or CD search by reading the child-env PROJECTION (`shell.env`/`state.env`)
# resurrects an outer exported value under a declared-unset `local PATH`/
# `local CDPATH` (the H13 class again). The CV2 fix routed the three closing-
# verifier faces (cd's CDPATH search, the external PATH search, and the
# empty-PATH 127-message discriminator) through `state.get_variable`. This
# scanner locks that: any `env.get('PATH'|'CDPATH')` / `env['PATH'|'CDPATH']`
# read must be in the justified allowlist below (a NEW consumer read fails).

# regex: `<...>env.get('PATH'` / `env['CDPATH']` (single or double quotes).
_ENV_NAME_READ = re.compile(
    r"""\benv\s*(?:\.get\(\s*|\[\s*)['"](PATH|CDPATH)['"]""")

# file (repo-relative) -> why an env read of PATH/CDPATH there is LEGITIMATE.
# Only genuinely-legitimate projection reads belong here — a known-divergent
# consumer read is fixed (routed through get_variable), never allowlisted (the
# CV2 integrator ruling: converge the class, no carve-outs). Every CV2 face
# (cd/CDPATH, external search, empty-PATH 127-message, AND hash/exec/source)
# now uses variable-truth, so NONE of them appear below.
_ENV_NAME_READ_ALLOWLIST = {
    # The command-SEARCH decision uses variable-truth (resolve_for_exec + the
    # get_variable-based empty_path). The two env reads that remain here are NOT
    # search decisions:
    #  - the ENOEXEC re-resolution runs in the FORKED CHILD, reading the child's
    #    own env after execvpe already found+started the file (a bare-name miss
    #    is force_not_found in the PARENT before any fork, so this never
    #    re-searches under a `local PATH` shadow);
    #  - the --debug-exec line only DISPLAYS the child env PATH.
    'psh/executor/strategies.py':
        'ENOEXEC child re-resolution (post-fork) + --debug-exec display',
}


def _env_name_reads():
    """Every `env.get('PATH'|'CDPATH')` / `env['...']` read in psh/, as a list
    of (repo-relative-path, lineno, stripped-line)."""
    hits = []
    for path in sorted(PSH.rglob('*.py')):
        if '__pycache__' in path.parts:
            continue
        rel = str(path.relative_to(ROOT))
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if _ENV_NAME_READ.search(line):
                hits.append((rel, i, line.strip()))
    return hits


def test_path_cdpath_env_reads_are_allowlisted():
    offenders = [(rel, ln, txt) for rel, ln, txt in _env_name_reads()
                 if rel not in _ENV_NAME_READ_ALLOWLIST]
    assert not offenders, (
        "A consumer reads PATH/CDPATH from the child-env projection instead of "
        "the variable-truth lookup (state.get_variable) — a declared-unset "
        "`local PATH`/`local CDPATH` would RESURRECT the outer export (#20 H13 / "
        f"CV2). Route it through get_variable, or justify it in the allowlist: "
        f"{offenders}")


def test_path_env_read_scanner_detects_offender():
    """Self-test: a synthetic consumer env read is matched; get_variable is not."""
    assert _ENV_NAME_READ.search("p = shell.env.get('PATH', '')")
    assert _ENV_NAME_READ.search('d = self.shell.env["CDPATH"]')
    assert not _ENV_NAME_READ.search("p = shell.state.get_variable('PATH', '')")
    assert not _ENV_NAME_READ.search("x = env.get('HOME', '')")


# --- Invariant 2: _param_is_set routes plain names through lookup ------------

def test_param_is_set_uses_the_tri_state_authority():
    src = _method_source((PSH / 'expansion/operators.py').read_text(),
                         'def _param_is_set(self, var_name')
    assert re.search(r'scope_manager\.lookup\(', src), (
        "_param_is_set must decide plain-name set-ness through the tri-state "
        "ScopeManager.lookup (no env-fallback path).")


# --- Invariant 3: every dynamic-special interception is masking-aware --------

# Machinery methods are exempt from the "must consult the mask" rule:
# is_dynamic_special exposes has_lifecycle as the public predicate;
# _local_shadows_special guards on it; _get_special_variable is the compute
# engine (its CALLERS mask — it is reached only through masked gates);
# resolve_nameref_name uses is_computed for a side-effect-free NAME inspection
# only (a shadowing plain local is never a nameref, so its resolve-to-self
# answer is identical masked or unmasked).
_EXEMPT_METHODS = ('def is_dynamic_special', 'def _local_shadows_special',
                   'def _get_special_variable', 'def resolve_nameref_name')

# Both spellings gate a special interception: the lifecycle-only sites use
# has_lifecycle(name); the read path uses the wider is_computed(name).
_GATE_TOKENS = ('has_lifecycle(name)', 'is_computed(name)')


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
        if not any(tok in line for tok in _GATE_TOKENS):
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
    bad_read = (
        "        if self._special.is_computed(name):\n"
        "            return self._get_special_variable(name)\n"
    )
    good = (
        "        if self._special.has_lifecycle(name) and not self._local_shadows_special(name):\n"
        "            self._special.assign(name, value)\n"
    )
    good_read = (
        "        if self._special.is_computed(name) and not self._local_shadows_special(name):\n"
        "            return self._get_special_variable(name)\n"
    )
    assert _unmasked_interceptions(bad), "scanner must catch the unmasked gate"
    assert _unmasked_interceptions(bad_read), "scanner must catch an unmasked is_computed read gate"
    assert not _unmasked_interceptions(good), "a masked gate must pass"
    assert not _unmasked_interceptions(good_read), "a masked read gate must pass"
