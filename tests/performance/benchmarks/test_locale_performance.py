"""Performance guards for the locale service's POSIX character classes.

Two properties matter:

1. **C locale: no regression.** Under LC_ALL=C (the suite default and psh's
   default) character-class matching stays on the ASCII fast path and never
   sweeps — many class matches must remain cheap.

2. **UTF-8 locale: bounded first-use cost, free thereafter.** The first use of a
   class in a UTF-8 locale sweeps the codepoint space via the host libc's
   iswctype (~0.3s measured); it is cached per (locale, class), so every later
   use is a dict hit. This guards against the sweep becoming pathological (e.g.
   an accidental per-match re-sweep).

Thresholds are generous (guards, not tight benchmarks) to avoid flaking under
load; a genuine algorithmic regression (per-match sweep) blows past them.
"""
import locale as _locale
import time

import pytest

from psh.core.locale_service import LocaleMode, LocaleService
from psh.shell import Shell


class TestLocaleClassPerformance:
    def test_c_locale_class_matching_is_cheap(self):
        """C-locale class matching never sweeps: 500 matches well under 1s."""
        sh = Shell()
        assert sh.state.locale.profile.ctype_mode is LocaleMode.C
        start = time.perf_counter()
        for _ in range(500):
            sh.run_command('[[ abc == [[:alpha:]][[:alpha:]][[:alpha:]] ]]')
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"C-locale class matching regressed: {elapsed:.3f}s"

    def test_utf8_first_use_bounded_then_cached(self):
        """UTF-8 first-use sweep is bounded; subsequent matches are cache hits."""
        import psh.core.locale_service as ls
        saved = _locale.setlocale(_locale.LC_ALL)
        try:
            sh = Shell()
            sh.state.locale = LocaleService({"LC_ALL": "en_US.UTF-8"},
                                            apply=True, warn=False)
            if sh.state.locale.profile.ctype_mode is not LocaleMode.UTF8:
                pytest.skip("en_US.UTF-8 unavailable on this host")
            # Force a cold sweep for this measurement.
            ls._RANGE_CACHE.clear()

            t0 = time.perf_counter()
            sh.run_command('[[ é == [[:alpha:]] ]]')      # cold: sweeps alpha
            first = time.perf_counter() - t0

            t1 = time.perf_counter()
            for _ in range(200):
                sh.run_command('[[ à == [[:alpha:]] ]]')   # cache hits
            cached = time.perf_counter() - t1

            assert first < 2.0, f"first-use sweep too slow: {first:.3f}s"
            assert cached < 0.5, f"cached class matching too slow: {cached:.3f}s"
        finally:
            _locale.setlocale(_locale.LC_ALL, saved)
