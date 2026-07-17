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

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]


# --- mypy override-resolution model -------------------------------------------

def _load_pyproject():
    with open(ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)


def override_entries(cfg):
    """``[(pattern, check_untyped_defs)]`` in file order, from every override
    section that sets the flag. Sections not setting it are irrelevant to this
    resolution and are skipped."""
    entries = []
    for section in cfg["tool"]["mypy"].get("overrides", []):
        if "check_untyped_defs" not in section:
            continue
        modules = section["module"]
        if isinstance(modules, str):
            modules = [modules]
        for pattern in modules:
            entries.append((pattern, bool(section["check_untyped_defs"])))
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
