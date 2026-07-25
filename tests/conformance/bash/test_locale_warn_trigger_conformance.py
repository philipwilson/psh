"""WHICH locale variable changed decides whether a failed setlocale is announced.

bash is not symmetric about this, and psh used to be. Probed against live bash
5.2.26 (macOS, homebrew) and 5.2.21 (Linux, ubuntu 24.04) with a locale name
invalid on BOTH platforms -- the two versions agree row for row:

    LC_ALL=<bad>              warns        LC_CTYPE=<bad>            warns
    LC_ALL=      (empty)      SILENT       LC_CTYPE=  (empty)        warns
    unset LC_ALL              SILENT       unset LC_CTYPE            warns
    startup LC_ALL=<bad>      warns        startup LC_CTYPE=<bad>    SILENT

Assigning a bad LC_ALL is a direct setlocale bash reports. Emptying or unsetting
it puts bash on its RESET path, which re-applies every category from the
remaining variables WITHOUT warning -- even when what becomes effective is
invalid. So the discriminator is the TRIGGER, not assignment-versus-unset:
``LC_ALL=`` is textually an assignment and is still silent.

psh warned on every re-application, which made ``unset LC_ALL`` noisy on any
host where the inherited LC_CTYPE names a locale libc does not have. That is
every Linux box (hence the nightly), and on macOS the ``UTF-8`` alias Terminal.app
exports -- the row in test_locale_conformance.py this fix also greens.

The two directions are pinned SEPARATELY and on purpose:

* the SILENCE rows compare psh against live bash (both produce empty stderr), so
  deleting the fix reds them;
* the KEEP-WARNING rows pin psh's own diagnostic, so a blanket "never warn"
  over-correction reds THEM. Neither mutation can pass both halves.

Every row drives a real ``psh -c`` / ``bash -c`` subprocess through the shared
oracle -- never a direct ``LocaleService.reinit()`` call -- because the trigger
is the shell's variable-observer path, which a unit call bypasses entirely.
"""

import pytest
from conformance_framework import ConformanceTest
from shell_oracle import is_comparable, run_psh

# Invalid on macOS AND on glibc, so the rows mean the same thing on both.
BOGUS = "xx_BOGUS.UTF-8"


def _psh_stderr(script, env=None):
    r = run_psh(["-c", script], env=env, timeout=30)
    assert is_comparable(r), r
    return r.stderr


class TestLcAllResetPathIsSilent(ConformanceTest):
    """bash's LC_ALL reset path applies the fallback WITHOUT announcing it."""

    def test_unset_lc_all_exposing_invalid_ctype_is_silent(self):
        # The nightly's shape: LC_ALL hides an LC_CTYPE libc cannot honour.
        self.assert_identical_behavior(
            'unset LC_ALL; echo done',
            env={'LC_ALL': 'C', 'LC_CTYPE': BOGUS})

    def test_unset_lc_all_exposing_invalid_lang_is_silent(self):
        self.assert_identical_behavior(
            'unset LC_ALL; echo done',
            env={'LC_ALL': 'C', 'LANG': BOGUS})

    def test_emptying_lc_all_is_silent_too(self):
        # Textually an ASSIGNMENT, still silent: the trigger decides, not the
        # syntax. This is the row that refutes "assignment warns, unset does not".
        self.assert_identical_behavior(
            'LC_ALL=; echo done',
            env={'LC_ALL': 'C', 'LC_CTYPE': BOGUS})

    def test_startup_invalid_ctype_is_silent(self):
        # Nothing is re-applied, so nothing is announced -- and psh already
        # agreed here. Pinned so the fix cannot regress it into noise.
        self.assert_identical_behavior('echo done', env={'LC_CTYPE': BOGUS})


class TestDirectFailuresStillWarn:
    """The other direction: a blanket "stop warning" must red these.

    psh's wording is its own (bash prefixes ``bash: line N:`` and appends the
    strerror text), so these pin psh's diagnostic rather than comparing it.
    """

    @pytest.mark.parametrize("script,env,category", [
        # C: assigning a bad value directly to a category variable.
        (f'LC_CTYPE={BOGUS}; echo done', None, 'LC_CTYPE'),
        (f'LC_COLLATE={BOGUS}; echo done', None, 'LC_COLLATE'),
        # G: the temp-env prefix form.
        (f'LC_CTYPE={BOGUS} true', None, 'LC_CTYPE'),
        # D: a bad LC_ALL is a direct setlocale, at startup and by assignment.
        ('echo done', {'LC_ALL': BOGUS}, 'LC_CTYPE'),
        (f'LC_ALL={BOGUS}; echo done', None, 'LC_CTYPE'),
    ])
    def test_failed_setlocale_is_announced(self, script, env, category):
        err = _psh_stderr(script, env)
        assert 'cannot change locale' in err, (
            f"psh went silent for {script!r}: a setlocale failure the shell "
            f"caused directly must still be announced, not swallowed with "
            f"bash's LC_ALL reset path.\nstderr={err!r}")
        assert category in err, (
            f"expected the {category} category named in psh's warning; "
            f"got {err!r}")
