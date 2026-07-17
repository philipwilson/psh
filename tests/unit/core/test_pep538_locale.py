"""PEP 538 C-locale coercion handling (Locale Stage 4, sub-task ii).

CPython 3.7+ rewrites ``os.environ['LC_CTYPE']`` to a UTF-8 target when it starts
under an effectively-C environment (bare, or ``LANG=C`` with no ``LC_ALL``),
setting ``sys.flags.utf8_mode``. bash never sees that phantom. psh strips it at
startup (``ShellState._strip_coerced_lc_ctype``), so under those environments it
matches bash's C locale: é is not ``[[:alpha:]]``, ``$LC_CTYPE`` is empty, and no
``LC_CTYPE`` is passed to children. The strip follows a CONSERVATIVE PROVENANCE
RULE (campaign E3): it fires only when the coercion is provable — a nonempty
``LC_ALL`` (which disables CPython's coercion), ``PYTHONCOERCECLOCALE=0``, or
an explicit ``PYTHONUTF8``/``-X utf8`` request each prove/allow the inherited
value genuine, and it is then KEPT (see ``TestProvenanceRule``).

These MUST control the process environment precisely (the coercion only happens
in an effectively-C env), so they run psh in a subprocess with an explicit env —
the behavioral golden / conformance harnesses can't express a bare env (they pin
``LC_ALL=C``, which itself disables coercion). psh's outputs here are
deterministic and platform-stable (C-mode classification is pure-Python ASCII;
é-as-a-letter under en_US.UTF-8 holds on macOS and glibc). bash-equivalence for
every row was verified live and recorded in tmp/locale_ledger.md.
"""
import os
import subprocess
import sys

import pytest

# psh package root (…/tests/unit/core/this → repo root); used as cwd so
# `python -m psh -c` imports THIS tree (its -c form prepends cwd to sys.path).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
# A real PATH so `env`/`grep` and psh's own subprocesses resolve.
_PATH = os.environ.get("PATH", "/usr/bin:/bin")


def _run_psh(script, locale_env):
    """Run `python -m psh -c script` under a minimal env plus *locale_env*
    (the ONLY LC_*/LANG entries), returning stdout. No LC_ALL/LC_CTYPE/LANG
    leaks in from the parent — the coercion outcome depends on exactly these."""
    env = {"PATH": _PATH}
    env.update(locale_env)
    p = subprocess.run(
        [sys.executable, "-m", "psh", "-c", script],
        capture_output=True, text=True, env=env, cwd=_REPO_ROOT, timeout=30)
    return p.stdout

CLASSIFY = "[[ é == [[:alpha:]] ]] && echo yes || echo no"

# Environments where CPython coerces LC_CTYPE -> the phantom must be stripped so
# psh presents bash's C locale.
COERCING_ENVS = [
    pytest.param({}, id="bare"),
    pytest.param({"LANG": "C"}, id="lang_c"),
]


class TestPhantomStrippedInCoercingEnvs:
    @pytest.mark.parametrize("locale_env", COERCING_ENVS)
    def test_eacute_not_alpha(self, locale_env):
        # bash under the same env uses C: é is not [[:alpha:]].
        assert _run_psh(CLASSIFY, locale_env) == "no\n"

    @pytest.mark.parametrize("locale_env", COERCING_ENVS)
    def test_lc_ctype_variable_is_empty(self, locale_env):
        # bash shows an empty $LC_CTYPE; psh must not surface the phantom.
        assert _run_psh('echo "[$LC_CTYPE]"', locale_env) == "[]\n"

    @pytest.mark.parametrize("locale_env", COERCING_ENVS)
    def test_lc_ctype_not_leaked_to_child(self, locale_env):
        # bash passes no LC_CTYPE to children; the phantom must not either.
        assert _run_psh('env | grep -c "^LC_CTYPE=" || true', locale_env) == "0\n"

    def test_case_map_stays_ascii_only(self):
        # bare env is C: ${x^^} on é leaves it unchanged (ASCII-only case map).
        assert _run_psh('x=é; echo "${x^^}"', {}) == "é\n"


class TestGenuineValuesPreserved:
    def test_lc_all_c_no_coercion(self):
        # LC_ALL=C disables coercion entirely; nothing to strip, C behavior.
        assert _run_psh(CLASSIFY, {"LC_ALL": "C"}) == "no\n"

    def test_genuine_lc_ctype_utf8_kept(self):
        # A real en_US.UTF-8 (not a coercion target, utf8_mode 0) is untouched:
        # é classifies as a letter, like bash under the same env.
        assert _run_psh(CLASSIFY, {"LC_CTYPE": "en_US.UTF-8"}) == "yes\n"

    def test_genuine_c_utf8_kept_discriminator(self):
        # The discriminator: a genuinely-set C.UTF-8 leaves utf8_mode 0, so it is
        # KEPT (visible in $LC_CTYPE) — unlike the coerced C.UTF-8 of a bare env,
        # which pairs with utf8_mode 1 and is stripped. Echoing the variable is
        # platform-stable (avoids the macOS-vs-glibc C.UTF-8 ctype question).
        assert _run_psh('echo "[$LC_CTYPE]"', {"LC_CTYPE": "C.UTF-8"}) == "[C.UTF-8]\n"


class TestStripComposesWithReactivity:
    def test_bare_then_assign_utf8_reacts(self):
        # After the phantom strip the shell starts in C; a mid-session
        # LC_CTYPE=en_US.UTF-8 then reacts (é becomes a letter) — strip and
        # Stage-4 reactivity compose.
        assert _run_psh(f"LC_CTYPE=en_US.UTF-8; {CLASSIFY}", {}) == "yes\n"

    def test_bare_stays_c_without_assignment(self):
        # Control: with no assignment the bare env stays C (guards against the
        # strip being a no-op that only "works" because of a later reaction).
        assert _run_psh(CLASSIFY, {}) == "no\n"


VISIBILITY = 'echo "[$LC_CTYPE]"'


class TestProvenanceRule:
    """The strip fires ONLY when PEP 538 coercion is provable (campaign E3,
    continuation finding H). Every row was pre-registered against bash 5.2 and
    CPython 3.14 in the boundary-ledger probe matrix (E23-probes/
    lc_ctype_provenance_matrix.sh); the keep rows here were RED on v0.724.
    """

    # --- keep: a nonempty LC_ALL disables CPython's coercion, so the
    #     inherited LC_CTYPE is genuine. bash keeps it visible and a later
    #     `unset LC_ALL` falls back to it. (THE v0.724 gate-failure trio's
    #     root cause: the host terminal's LC_CTYPE reached the harness, psh
    #     stripped it, bash kept it.) ---
    def test_lc_all_c_keeps_inherited_c_utf8(self):
        env = {"LC_ALL": "C", "LC_CTYPE": "C.UTF-8"}
        assert _run_psh(VISIBILITY, env) == "[C.UTF-8]\n"

    def test_lc_all_c_keeps_inherited_utf8_terminal_row(self):
        # macOS Terminal.app exports LC_CTYPE=UTF-8 — the exact host value
        # that made three conformance results host-sensitive.
        env = {"LC_ALL": "C", "LC_CTYPE": "UTF-8"}
        assert _run_psh(VISIBILITY, env) == "[UTF-8]\n"

    def test_unset_lc_all_falls_back_to_kept_ctype(self):
        env = {"LC_ALL": "C", "LC_CTYPE": "en_US.UTF-8"}
        assert _run_psh(f"unset LC_ALL; {CLASSIFY}", env) == "yes\n"

    def test_kept_ctype_reaches_children(self):
        env = {"LC_ALL": "C", "LC_CTYPE": "C.UTF-8"}
        assert _run_psh('env | grep -c "^LC_CTYPE=" || true', env) == "1\n"

    # --- keep: an explicit UTF-8-mode request (PYTHONUTF8 / -X utf8)
    #     explains utf8_mode by itself, so the pairing no longer proves
    #     coercion; the genuine value is kept (was the OLD stripped
    #     "documented corner" — now correct). ---
    def test_pythonutf8_with_genuine_c_utf8_keeps(self):
        env = {"PYTHONUTF8": "1", "LC_CTYPE": "C.UTF-8"}
        assert _run_psh(VISIBILITY, env) == "[C.UTF-8]\n"

    # --- keep: PYTHONCOERCECLOCALE=0 disables coercion entirely. ---
    def test_coercion_disabled_keeps_value(self):
        env = {"PYTHONCOERCECLOCALE": "0", "LC_CTYPE": "C.UTF-8"}
        assert _run_psh(VISIBILITY, env) == "[C.UTF-8]\n"

    # --- strip branch stays intact: without LC_ALL / explicit request the
    #     coercion IS provable and the phantom is still dropped. ---
    @pytest.mark.parametrize("locale_env", COERCING_ENVS)
    def test_provable_coercion_still_stripped(self, locale_env):
        assert _run_psh(VISIBILITY, locale_env) == "[]\n"

    def test_empty_lc_all_does_not_block_strip(self):
        # CPython treats an EMPTY LC_ALL as unset for the coercion check; so
        # does the provenance rule (the strip conditions consider only a
        # NONEMPTY LC_ALL as disproof). In this env CPython does not coerce
        # at all on platforms resolving C.UTF-8 (utf8_mode stays 0), so the
        # genuine value is kept — the row pins that the empty-LC_ALL branch
        # never misclassifies it as provably coerced and behaves like bash.
        env = {"LC_ALL": "", "LC_CTYPE": "C.UTF-8"}
        assert _run_psh(VISIBILITY, env) == "[C.UTF-8]\n"

    # --- the residual corner, pinned as DOCUMENTED divergence: explicit
    #     PYTHONUTF8=1 in an otherwise effectively-C env still coerces, and
    #     keep-when-unknowable keeps that phantom (bash shows nothing). If
    #     this row ever starts printing [] the rule changed — update
    #     docs/user_guide/17_differences_from_bash.md in the same commit. ---
    def test_residual_corner_pythonutf8_alone_keeps_phantom(self):
        # The coercion target's exact spelling is platform-dependent
        # (C.UTF-8 on glibc and modern macOS; UTF-8 on older macOS).
        out = _run_psh(VISIBILITY, {"PYTHONUTF8": "1"})
        assert out in ("[C.UTF-8]\n", "[C.utf8]\n", "[UTF-8]\n"), out
