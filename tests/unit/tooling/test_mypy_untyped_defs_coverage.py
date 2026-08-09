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
#
# The message carries the RANGE it could not verify, matching the shape of the
# twin in ``test_shell_consumer_ratchet_q1.py``. The two copies are deliberately
# NOT deduplicated into a shared helper (remediation 5C.1): each guard's
# warn-path self-test must be able to fail on its own module's source, and a
# shared helper would make one guard's green depend on the other's file. Uniform
# in SHAPE, not coupled in CODE.
_SELFCHECK_UNVERIFIED = (
    "SELF-CHECK SKIPPED: cannot verify {name} against the git enumeration "
    "(git log --diff-filter=A {range} -- psh/): {reason}. The "
    "hardcoded list is TRUSTED UNVERIFIED here — drift between it and the "
    "actual campaign-created set will go UNDETECTED until this test runs in a "
    "full checkout with the base tag present."
)

#: The pinned scope endpoint, and why this guard has one at all.
#:
#: SCOPE CURRENCY (remediation 5C.1, successor row D-5B.1-s2). This guard is the
#: consumer ratchet's TWIN and it had drifted the same way: the range was pinned
#: at ``v0.724.0..75ab5625``, an endpoint from the PREVIOUS campaign, so every
#: module born after it was invisible to the enumeration. The drift was not even
#: latent — ``psh/protocols/__init__.py`` was created AFTER that endpoint, and
#: the self-check had been hand-patched to inject it
#: (``created.add("psh.protocols")``) so the assertion would still pass. A
#: currency structure exists precisely to eliminate that class of workaround, so
#: the injection is GONE: ``psh.protocols`` is derived from git like every other
#: entry.
#:
#: Advancing the endpoint is a deliberate, reviewed edit — it re-baselines what
#: "new" means, so it moves only together with ``MIGRATED_MODULES`` and the two
#: post-endpoint registers below.
SCOPE_BASE = "v0.724.0"
SCOPE_ENDPOINT = "d0956bed"
SCOPE_RANGE = f"{SCOPE_BASE}..{SCOPE_ENDPOINT}"


def _enumerate_added(rng):
    """Dotted ``psh`` modules added in *rng*, or ``(None, reason)`` when git or
    the range is unavailable."""
    try:
        out = subprocess.run(
            ["git", "log", "--diff-filter=A", "--pretty=format:",
             "--name-only", rng, "--", "psh/"],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return None, f"git unavailable ({type(e).__name__})"
    if out.returncode != 0:
        return None, f"base tag/range {rng} not present in this checkout"
    created = set()
    for ln in out.stdout.splitlines():
        ln = ln.strip()
        if ln.endswith(".py"):
            dotted = ln[:-3].replace("/", ".")
            if dotted.endswith(".__init__"):
                dotted = dotted[:-len(".__init__")]
            created.add(dotted)
    return created, None


def _created_modules_from_git():
    """Dotted campaign-created ``psh`` modules over the PINNED range, or
    ``(None, reason)`` when git or the base tag/range is unavailable.

    Nothing is injected here. ``psh.protocols`` used to be added by hand because
    it postdated the stale endpoint; at a current endpoint it is simply part of
    the enumeration.
    """
    return _enumerate_added(SCOPE_RANGE)


def _warn_selfcheck_unverified(list_name, reason, rng=None):
    """Emit the loud 'protection lost' warning (Q3 WP5). Kept separate from the
    ``pytest.skip`` so it is unit-testable without catching Skipped."""
    warnings.warn(
        _SELFCHECK_UNVERIFIED.format(
            name=list_name, reason=reason, range=rng or SCOPE_RANGE),
        stacklevel=2,
    )


def _endpoint_is_ancestor_of_head():
    """True/False if git can answer, None if git cannot be consulted."""
    try:
        out = subprocess.run(
            ["git", "merge-base", "--is-ancestor", SCOPE_ENDPOINT, "HEAD"],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode == 0:
        return True
    if out.returncode == 1:
        return False
    return None   # not a repo / unknown rev — indistinguishable from absent


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
# Source of truth: the git enumeration over SCOPE_RANGE, asserted below. Dotted
# module names, sorted. Grew 17 -> 20 in remediation 5C.1 when the endpoint
# advanced: the three remediation-campaign-created modules joined, and
# psh.protocols stopped being a hand-injected special case.
MIGRATED_MODULES = [
    "psh.ast_nodes.syntax_templates",
    "psh.core.process_lease",
    "psh.core.variable_lookup",
    "psh.executor.command_resolution",
    "psh.executor.foreground_session",
    "psh.expansion.procsub_render",
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
    "psh.protocols",
    "psh.scripting.analysis_session",
    "psh.scripting.program_source",
    # Zero function definitions today — it is a pure data table. The override
    # coverage is NOT pointless: it is there for the FIRST def anyone adds, so
    # the discipline applies from that def rather than being noticed afterwards.
    "psh.utils.posix_classes",
]

#: Modules born AFTER SCOPE_ENDPOINT that carry the full-signature discipline
#: anyway. They cannot live in MIGRATED_MODULES: that list is asserted EQUAL to
#: the pinned git enumeration, which by construction cannot contain them.
POST_ENDPOINT_MIGRATED: list = []

#: Modules born after SCOPE_ENDPOINT deliberately NOT under the discipline
#: (path -> why). Kept honest by the coverage assertion: a new module lands in
#: one register or the other, never in neither.
POST_ENDPOINT_OUT_OF_SCOPE: dict = {}


def uncovered_post_endpoint_modules(created_after_endpoint, migrated,
                                    out_of_scope):
    """Post-endpoint modules in NEITHER register — the ones that would silently
    fall outside this guard.

    Pure, so the coverage assertion's logic is self-tested against an INJECTED
    enumeration rather than against real commits (which would move under the
    test). Same structure as the consumer ratchet's twin of this function.
    """
    return sorted(set(created_after_endpoint) - set(migrated)
                  - set(out_of_scope))


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
    """MIGRATED_MODULES is EXACTLY the git-derived created set over SCOPE_RANGE
    — no injected entries.

    Remediation 5C.1 removed a hand-patched ``created.add("psh.protocols")``
    here. That injection existed only because the pinned endpoint predated the
    module, so the derivation had quietly stopped being a derivation. If this
    assertion ever needs another injection to pass, the endpoint is stale
    again — advance it, do not patch around it.
    """
    created, reason = _created_modules_from_git()
    if created is None:
        _warn_selfcheck_unverified("MIGRATED_MODULES", reason)
        pytest.skip(reason)
    assert set(MIGRATED_MODULES) == created, (
        "MIGRATED_MODULES drifted from the git-created set:\n"
        f"  only in git: {sorted(created - set(MIGRATED_MODULES))}\n"
        f"  only in list: {sorted(set(MIGRATED_MODULES) - created)}")


def test_post_endpoint_modules_are_all_dispositioned():
    """COVERAGE (5C.1): every psh module born after SCOPE_ENDPOINT is either
    under the full-signature discipline or explicitly declared out of scope.

    Without this, the guard's scope silently stops covering new code the moment
    the endpoint is pinned — which is exactly how this guard came to need a
    hand-injected ``psh.protocols`` entry.

    ANCESTOR CHECK FIRST. ``SCOPE_ENDPOINT..HEAD`` is EMPTY — and this test
    therefore vacuously green — whenever the endpoint is not an ancestor of
    HEAD: a branch predating it, rewritten history, a shallow clone. That is
    the same silent-rot failure one level up, so it WARNS loudly rather than
    passing quietly.
    """
    ancestry = _endpoint_is_ancestor_of_head()
    if ancestry is False:
        _warn_selfcheck_unverified(
            "POST_ENDPOINT coverage",
            f"SCOPE_ENDPOINT {SCOPE_ENDPOINT} is NOT an ancestor of HEAD, so "
            "the range is empty and this coverage check would pass VACUOUSLY",
            f"{SCOPE_ENDPOINT}..HEAD")
        pytest.skip(f"{SCOPE_ENDPOINT} is not an ancestor of HEAD")
    created, reason = _enumerate_added(f"{SCOPE_ENDPOINT}..HEAD")
    if created is None or ancestry is None:
        pytest.skip(reason or "git/endpoint range unavailable in this checkout")
    live = {m for m in created
            if (ROOT / pathlib.Path(*m.split("."))).with_suffix(".py").exists()
            or (ROOT / pathlib.Path(*m.split("."))
                / "__init__.py").exists()}
    uncovered = uncovered_post_endpoint_modules(
        live, MIGRATED_MODULES + POST_ENDPOINT_MIGRATED,
        POST_ENDPOINT_OUT_OF_SCOPE)
    assert not uncovered, (
        "psh module(s) created after the pinned scope endpoint "
        f"({SCOPE_ENDPOINT}) with NO disposition: {uncovered}. Either add each "
        "to POST_ENDPOINT_MIGRATED (with a pyproject override giving it both "
        "disallow flags) or to POST_ENDPOINT_OUT_OF_SCOPE with a "
        "justification. Leaving it in neither is how the scope silently rots.")


def test_a_non_ancestor_endpoint_warns_with_its_reason():
    """The vacuous-pass window is LOUD, and the warning says WHY.

    A RED arm that only checked "something was raised" would be satisfied by
    any failure at all — the wrong-reason trap.
    """
    with pytest.warns(UserWarning, match="VACUOUSLY") as caught:
        _warn_selfcheck_unverified(
            "POST_ENDPOINT coverage",
            f"SCOPE_ENDPOINT {SCOPE_ENDPOINT} is NOT an ancestor of HEAD, so "
            "the range is empty and this coverage check would pass VACUOUSLY",
            f"{SCOPE_ENDPOINT}..HEAD")
    text = str(caught[0].message)
    assert "TRUSTED UNVERIFIED" in text        # the shared loud-warning shape
    assert "NOT an ancestor" in text           # the specific cause
    assert SCOPE_ENDPOINT in text              # which endpoint


def test_ancestor_check_answers_true_for_the_pinned_endpoint():
    """Control for the arm above: on a normal checkout the endpoint IS an
    ancestor, so the coverage test runs for real rather than skipping."""
    ancestry = _endpoint_is_ancestor_of_head()
    if ancestry is None:
        pytest.skip("git unavailable")
    assert ancestry is True, (
        f"{SCOPE_ENDPOINT} is not an ancestor of HEAD — the coverage "
        "assertion is skipping, not checking")


def test_coverage_flags_an_undispositioned_post_endpoint_module():
    assert uncovered_post_endpoint_modules(
        {"psh.newpkg.newborn"}, migrated=[], out_of_scope={}) == [
        "psh.newpkg.newborn"]


def test_coverage_accepts_a_dispositioned_post_endpoint_module():
    assert uncovered_post_endpoint_modules(
        {"psh.newpkg.newborn"}, migrated=["psh.newpkg.newborn"],
        out_of_scope={}) == []
    assert uncovered_post_endpoint_modules(
        {"psh.newpkg.newborn"}, migrated=[],
        out_of_scope={"psh.newpkg.newborn": "generated stub, no defs"}) == []


def test_coverage_reports_only_the_undispositioned_one():
    """Mixed input: a passing coverage assertion cannot be passing vacuously."""
    assert uncovered_post_endpoint_modules(
        {"psh.a", "psh.b", "psh.c"}, migrated=["psh.a"],
        out_of_scope={"psh.b": "declared"}) == ["psh.c"]


def test_every_out_of_scope_entry_has_justification():
    for path, reason in POST_ENDPOINT_OUT_OF_SCOPE.items():
        assert isinstance(reason, str) and len(reason.strip()) >= 20, (
            f"out-of-scope entry {path} needs a real justification")


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


# === The bare-vs-star hole (remediation 5C.1) ================================
#
# TESTINF-1 is the defect this whole module exists to police: a BARE module
# entry in a mypy override covers only the package ``__init__``, never its
# submodules. That defect was living INSIDE this guard's own subject. pyproject
# covered the protocols package twice with different spellings — starred at the
# check_untyped_defs override, BARE in the disallow block — so
# ``psh.protocols.<anything>`` resolved to disallow_untyped_defs = False and
# disallow_incomplete_defs = False, and nothing here would have noticed: the
# assertions above resolve the hardcoded dotted names only, never a submodule.
#
# The CONFIG was fixed (the disallow entry is starred). This cell generalizes
# it: any MIGRATED_MODULES entry that is a real PACKAGE must cover its
# submodules too, so the next migrated package cannot repeat the hole.
#
# Deliberately NOT done: teaching the resolver to treat a bare package entry as
# covering submodules. That would encode a model of coverage mypy does not
# have — the config would still be wrong, and the guard would agree with it.

def _is_package(dotted):
    return (ROOT / pathlib.Path(*dotted.split("."))
            / "__init__.py").is_file()


def migrated_packages_with_submodule_holes(modules):
    """Migrated entries that are PACKAGES whose hypothetical submodule loses a
    disallow flag the parent has. Pure, so it is self-testable."""
    holes = []
    for module in modules:
        if not _is_package(module):
            continue
        probe = f"{module}.zzz_future_submodule"
        for flag in ("disallow_untyped_defs", "disallow_incomplete_defs"):
            if _resolves_flag(module, flag) and not _resolves_flag(probe, flag):
                holes.append(f"{module}: a submodule loses {flag}")
    return holes


def test_migrated_packages_cover_their_submodules():
    holes = migrated_packages_with_submodule_holes(MIGRATED_MODULES)
    assert not holes, (
        "migrated PACKAGE(s) whose override is spelled BARE, so a future "
        "submodule escapes the full-signature discipline (TESTINF-1, the exact "
        "defect this module polices). Star the module entry in pyproject "
        "(`\"pkg\"` -> `\"pkg.*\"`), do not loosen the guard:\n  "
        + "\n  ".join(holes))


def test_submodule_hole_detector_bites_on_the_bare_spelling():
    """OFFENDER ARM, red at the pre-fix config shape and green at the fixed one.

    Rather than reproducing the whole pyproject, this drives the same
    resolution model the guard uses over a synthetic entry table: BARE covers
    only the package, STARRED covers the submodule. If this arm ever passes for
    the bare shape, the detector has stopped detecting.
    """
    bare = [("psh.demo", True)]
    starred = [("psh.demo.*", True)]
    # The precise semantics the hole rests on:
    assert resolve_check_untyped_defs("psh.demo", bare, False) is True
    assert resolve_check_untyped_defs("psh.demo.sub", bare, False) is False
    # ...and the fix:
    assert resolve_check_untyped_defs("psh.demo", starred, False) is True
    assert resolve_check_untyped_defs("psh.demo.sub", starred, False) is True


def test_submodule_hole_control_a_covered_package_is_silent():
    """CONTROL: the live protocols package (starred since 5C.1) reports NO
    hole, so a green run above is green for the right reason."""
    assert migrated_packages_with_submodule_holes(["psh.protocols"]) == []
    assert _resolves_flag("psh.protocols.zzz_future_submodule",
                          "disallow_untyped_defs") is True
    assert _resolves_flag("psh.protocols.zzz_future_submodule",
                          "disallow_incomplete_defs") is True


def test_non_package_migrated_modules_are_not_flagged():
    """CONTROL: a plain module has no submodules, so it can never hole."""
    assert migrated_packages_with_submodule_holes(["psh.invocation"]) == []
