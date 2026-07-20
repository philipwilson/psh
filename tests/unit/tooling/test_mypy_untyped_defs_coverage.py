"""Meta-test: every psh module resolves to a check_untyped_defs=true override.

TESTINF-1 (reappraisal #21): ``test_mypy_scope.py`` guards the mypy *files*
scope, but the ``check_untyped_defs`` *coverage* had no guard — and the bare
``psh.parser`` override entry matched only the package ``__init__``, not its
submodules, so ``psh/parser/array_flat_text.py`` silently fell back to the
global ``check_untyped_defs = false`` while the config comment claimed
completeness (demonstrated red-on-base at d1b8ef35:
tmp/boundary-ledgers/E1-probes/02-mypy-override-gap-red-on-base.txt).

This guard parses pyproject.toml and applies mypy's DOCUMENTED per-module
option resolution — exact-name sections beat wildcard sections; among matching
wildcard sections, later in the file overrides earlier — then asserts every
``psh/**/*.py`` module resolves to ``check_untyped_defs = true``. The
verifier's empirical proof that a bare-module entry does NOT reach submodule
bodies is reproduced below with a real mypy subprocess run
(``test_bare_module_override_does_not_reach_submodules_empirically``).

Guard-the-guard: a fabricated module name that no override covers must make
the checker report an escape (synthetic-offender self-test), per the tooling
directory's idiom (TESTINF-5 context).
"""

import pathlib
import subprocess
import sys
import textwrap
import tomllib
import warnings

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]


# Campaign Q3 (WP5): the git self-checks below verify the hardcoded module lists
# against the actual campaign-created set. When git or the base tag is
# unavailable (a shallow/tarball checkout) the check cannot run — but it must
# not SKIP SILENTLY, or drift in the list goes undetected with no signal. Emit a
# warning naming exactly what protection is lost, THEN skip. Green-repo behavior
# (git + base tag present) is unchanged: the assertion runs.
_SELFCHECK_UNVERIFIED = (
    "SELF-CHECK SKIPPED: cannot verify {name} against the git enumeration "
    "(git log --diff-filter=A v0.724.0..75ab5625 -- psh/): {reason}. The "
    "hardcoded list is TRUSTED UNVERIFIED here — drift between it and the "
    "actual campaign-created set will go UNDETECTED until this test runs in a "
    "full checkout with the base tag present."
)


def _created_modules_from_git():
    """Dotted campaign-created ``psh`` modules from the git enumeration, or
    ``(None, reason)`` when git or the base tag/range is unavailable."""
    try:
        out = subprocess.run(
            ["git", "log", "--diff-filter=A", "--pretty=format:",
             "--name-only", "v0.724.0..75ab5625", "--", "psh/"],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return None, f"git unavailable ({type(e).__name__})"
    if out.returncode != 0:
        return None, "base tag/range v0.724.0..75ab5625 not present in this checkout"
    created = set()
    for ln in out.stdout.splitlines():
        ln = ln.strip()
        if ln.endswith(".py"):
            dotted = ln[:-3].replace("/", ".")
            if dotted.endswith(".__init__"):
                dotted = dotted[:-len(".__init__")]
            created.add(dotted)
    return created, None


def _warn_selfcheck_unverified(list_name, reason):
    """Emit the loud 'protection lost' warning (Q3 WP5). Kept separate from the
    ``pytest.skip`` so it is unit-testable without catching Skipped."""
    warnings.warn(
        _SELFCHECK_UNVERIFIED.format(name=list_name, reason=reason),
        stacklevel=2,
    )


# --- mypy override-resolution model -------------------------------------------

def _load_pyproject():
    with open(ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)


def override_entries(cfg, flag="check_untyped_defs"):
    """``[(pattern, <flag>)]`` in file order, from every override section that
    sets ``flag``. Sections not setting it are skipped."""
    entries = []
    for section in cfg["tool"]["mypy"].get("overrides", []):
        if flag not in section:
            continue
        modules = section["module"]
        if isinstance(modules, str):
            modules = [modules]
        for pattern in modules:
            entries.append((pattern, bool(section[flag])))
    return entries


def _wildcard_matches(pattern, module):
    """Trailing-star pattern semantics: ``foo.bar.*`` matches ``foo.bar`` and
    any submodule. Any OTHER wildcard shape in the config is rejected loudly
    (this guard would need extending) rather than silently mis-resolved."""
    if "*" not in pattern:
        return False
    assert pattern.endswith(".*") and "*" not in pattern[:-2], (
        f"unsupported mypy override wildcard shape {pattern!r}; extend "
        "_wildcard_matches before using it")
    base = pattern[:-2]
    return module == base or module.startswith(base + ".")


def resolve_check_untyped_defs(module, entries, default):
    """mypy's documented per-module option resolution (config docs): concrete
    module names take precedence over wildcard patterns; among wildcard
    patterns, sections later in the file override earlier ones."""
    exact = None
    value = default
    for pattern, flag in entries:
        if pattern == module:
            exact = flag
        elif _wildcard_matches(pattern, module):
            value = flag
    return exact if exact is not None else value


def psh_modules():
    modules = []
    for py in sorted((ROOT / "psh").rglob("*.py")):
        if "__pycache__" in py.parts:
            continue
        parts = list(py.relative_to(ROOT).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        modules.append(".".join(parts))
    return modules


def escaped_modules(modules, entries, default):
    return [m for m in modules
            if not resolve_check_untyped_defs(m, entries, default)]


# --- The guard ----------------------------------------------------------------

def test_every_psh_module_has_check_untyped_defs():
    cfg = _load_pyproject()
    default = bool(cfg["tool"]["mypy"].get("check_untyped_defs", False))
    entries = override_entries(cfg)
    escaped = escaped_modules(psh_modules(), entries, default)
    assert not escaped, (
        "These psh modules resolve to check_untyped_defs = false — their "
        "un-annotated function BODIES are not type-checked. Cover them with a "
        "`.*` override in pyproject.toml (a bare package name does NOT reach "
        "submodules):\n  " + "\n  ".join(escaped)
    )


# --- Guard-the-guard ----------------------------------------------------------

def test_synthetic_offender_is_flagged():
    """A fabricated module that no override covers MUST be reported — proves
    the guard is alive, not vacuous."""
    cfg = _load_pyproject()
    default = bool(cfg["tool"]["mypy"].get("check_untyped_defs", False))
    entries = override_entries(cfg)
    offender = "psh.zzz_snuck_package.zzz_snuck_module"
    assert resolve_check_untyped_defs(offender, entries, default) is False
    escaped = escaped_modules(psh_modules() + [offender], entries, default)
    assert offender in escaped, (
        "the guard failed to flag a module outside every override — it could "
        "not catch a real escape either")


def test_resolution_semantics_bare_vs_star():
    """The TESTINF-1 semantics, stated as pure resolution facts: a bare
    module entry covers ONLY that module; a trailing-star entry covers the
    base module AND its submodules; exact beats wildcard; later wildcard
    beats earlier."""
    entries = [("pkg.sub", True)]
    assert resolve_check_untyped_defs("pkg.sub", entries, False) is True
    assert resolve_check_untyped_defs("pkg.sub.deep", entries, False) is False

    entries = [("pkg.sub.*", True)]
    assert resolve_check_untyped_defs("pkg.sub", entries, False) is True
    assert resolve_check_untyped_defs("pkg.sub.deep", entries, False) is True
    assert resolve_check_untyped_defs("pkg.other", entries, False) is False

    # Exact beats wildcard regardless of file order.
    entries = [("pkg.sub.deep", False), ("pkg.sub.*", True)]
    assert resolve_check_untyped_defs("pkg.sub.deep", entries, False) is False
    # Later wildcard overrides earlier wildcard.
    entries = [("pkg.sub.*", False), ("pkg.*", True)]
    assert resolve_check_untyped_defs("pkg.sub.deep", entries, False) is True


@pytest.mark.slow
def test_bare_module_override_does_not_reach_submodules_empirically(tmp_path):
    """Reproduce the TESTINF-1 verifier's dispositive proof with a REAL mypy
    run: an untyped def whose body contains a type error in ``pkg/sub/deep.py``
    is missed under ``module = "pkg.sub"`` and caught under ``"pkg.sub.*"``.
    This anchors the pure model above to mypy's actual behavior."""
    pytest.importorskip("mypy")
    pkg = tmp_path / "pkg"
    (pkg / "sub").mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "sub" / "__init__.py").write_text("")
    (pkg / "sub" / "deep.py").write_text(
        'def f():\n    return "a" + 1\n')  # body error, untyped def

    def run_mypy(pattern):
        (tmp_path / "pyproject.toml").write_text(textwrap.dedent(f"""
            [tool.mypy]
            files = ["pkg"]
            check_untyped_defs = false

            [[tool.mypy.overrides]]
            module = "{pattern}"
            check_untyped_defs = true
        """))
        return subprocess.run(
            [sys.executable, "-m", "mypy", "--no-error-summary",
             "--cache-dir", str(tmp_path / ".mypy_cache"), "pkg"],
            cwd=tmp_path, capture_output=True, text=True, timeout=300)

    bare = run_mypy("pkg.sub")
    assert bare.returncode == 0, (
        "expected the BARE override to miss the submodule body error, got:\n"
        + bare.stdout + bare.stderr)

    star = run_mypy("pkg.sub.*")
    assert star.returncode != 0 and "deep.py" in star.stdout, (
        "expected the .* override to catch the submodule body error, got:\n"
        + star.stdout + star.stderr)


# === Q2 family 9: incomplete public signatures in migrated packages ==========
#
# The boundary campaign CREATED/migrated these modules; each must carry COMPLETE
# typed signatures — mypy `disallow_untyped_defs` (no fully-untyped def) AND
# `disallow_incomplete_defs` (no partially-annotated def) — matching the lexer
# package precedent. This ratchet freezes THAT discipline: every migrated module
# must resolve to BOTH flags true, the migrated set is the git-derived
# campaign-created set (self-checked), and the set of full-signature modules may
# only GROW. A synthetic offender (a migrated module with no covering override)
# is flagged.
#
# Source of truth (Q1 CREATED_MODULES, git --diff-filter=A v0.724.0..75ab5625 --
# psh/) + psh.protocols; dotted module names.
MIGRATED_MODULES = [
    "psh.ast_nodes.syntax_templates",
    "psh.core.process_lease",
    "psh.core.variable_lookup",
    "psh.executor.command_resolution",
    "psh.executor.foreground_session",
    "psh.expansion.subscript",
    "psh.interactive.history_result",
    "psh.invocation",
    "psh.io_redirect.input_cursor",
    "psh.io_redirect.redirect_program",
    "psh.parser.parse_inputs",
    "psh.parser.parse_outcome",
    "psh.parser.recursive_descent.support.syntax_templates",
    "psh.parser.session",
    "psh.parser.unclosed_expansion",
    "psh.scripting.program_source",
    "psh.protocols",
]


def _resolves_flag(module, flag):
    cfg = _load_pyproject()
    default = bool(cfg["tool"]["mypy"].get(flag, False))
    entries = override_entries(cfg, flag)
    return resolve_check_untyped_defs(module, entries, default)


def test_migrated_modules_have_complete_signatures():
    """Every migrated module resolves to disallow_untyped_defs = true AND
    disallow_incomplete_defs = true — complete typed public signatures."""
    missing = []
    for module in MIGRATED_MODULES:
        if not _resolves_flag(module, "disallow_untyped_defs"):
            missing.append(f"{module}: disallow_untyped_defs not true")
        if not _resolves_flag(module, "disallow_incomplete_defs"):
            missing.append(f"{module}: disallow_incomplete_defs not true")
    assert not missing, (
        "migrated boundary modules without full-signature discipline — add a "
        "pyproject override (disallow_untyped_defs + disallow_incomplete_defs) "
        "and complete the signatures, do not loosen:\n  " + "\n  ".join(missing))


def test_migrated_modules_are_the_campaign_created_set():
    """MIGRATED_MODULES is exactly the git-derived campaign-created set (+
    protocols) — verified against git when the base tag is present. When git or
    the tag is absent the self-check WARNS loudly (Q3 WP5) before skipping, so
    the lost verification is visible rather than silent."""
    created, reason = _created_modules_from_git()
    if created is None:
        _warn_selfcheck_unverified("MIGRATED_MODULES", reason)
        pytest.skip(reason)
    # protocols is the one migrated package created as psh/protocols/__init__.py.
    created.add("psh.protocols")
    assert set(MIGRATED_MODULES) == created, (
        "MIGRATED_MODULES drifted from the git-created set:\n"
        f"  only in git: {sorted(created - set(MIGRATED_MODULES))}\n"
        f"  only in list: {sorted(set(MIGRATED_MODULES) - created)}")


def test_selfcheck_warns_loudly_when_git_unavailable(monkeypatch):
    """Q3 WP5: the campaign-created-set self-check must WARN (naming the lost
    protection) rather than skip silently when git/the base tag is unavailable —
    otherwise list drift goes undetected with zero signal in shallow checkouts."""
    def _boom(*args, **kwargs):
        raise OSError("git not available")
    monkeypatch.setattr(subprocess, "run", _boom)
    created, reason = _created_modules_from_git()
    assert created is None and "git unavailable" in reason
    with pytest.warns(UserWarning, match="TRUSTED UNVERIFIED"):
        _warn_selfcheck_unverified("MIGRATED_MODULES", reason)


def test_full_signature_discipline_only_grows():
    """The set of psh modules under disallow_untyped_defs may only GROW — a
    module that HAD the discipline (lexer package + the migrated set) must keep
    it. Frozen baseline of covered PACKAGES/modules."""
    cfg = _load_pyproject()
    entries = override_entries(cfg, "disallow_untyped_defs")
    default = bool(cfg["tool"]["mypy"].get("disallow_untyped_defs", False))
    covered = {m for m in (psh_modules() + MIGRATED_MODULES)
               if resolve_check_untyped_defs(m, entries, default)}
    # Everything currently disciplined must stay disciplined (grow-only).
    frozen_min = set(MIGRATED_MODULES) | {
        m for m in psh_modules() if m == "psh.lexer" or m.startswith("psh.lexer.")}
    regressed = sorted(frozen_min - covered)
    assert not regressed, (
        "these modules LOST disallow_untyped_defs discipline — the ratchet only "
        f"grows; restore their override:\n  {regressed}")


def test_synthetic_migrated_module_without_override_is_flagged():
    """A fabricated migrated module that no disallow override covers is caught —
    proving the ratchet is not vacuous."""
    offender = "psh.zzz_migrated_but_uncovered"
    assert _resolves_flag(offender, "disallow_untyped_defs") is False
    assert _resolves_flag(offender, "disallow_incomplete_defs") is False
