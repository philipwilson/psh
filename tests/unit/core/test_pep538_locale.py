"""PEP 538 C-locale coercion handling (Locale Stage 4, sub-task ii).

CPython 3.7+ rewrites ``os.environ['LC_CTYPE']`` to a UTF-8 target when it starts
under an effectively-C environment (bare, or ``LANG=C`` with no ``LC_ALL``),
setting ``sys.flags.utf8_mode``. bash never sees that phantom. psh strips it at
startup (``ShellState._strip_coerced_lc_ctype``), so under those environments it
matches bash's C locale: é is not ``[[:alpha:]]``, ``$LC_CTYPE`` is empty, and no
``LC_CTYPE`` is passed to children. A genuinely user-set value is preserved
(``utf8_mode`` is 0 unless CPython coerced/was forced).

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
