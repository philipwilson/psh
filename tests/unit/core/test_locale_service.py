"""Unit tests for psh.core.locale_service.

These test the pure locale-resolution logic (precedence, mode classification,
empty/invalid handling) with ``apply=False`` so no test touches the process's
global ``setlocale`` state, plus the collation primitives against the C locale
(the suite's pinned locale, so ``setlocale`` is a no-op here).
"""
import locale as _locale

from psh.core.locale_service import (
    LocaleMode,
    LocaleService,
    _classify,
    _effective,
    active_locale,
)


class TestModeClassification:
    def test_c_and_posix_are_c_mode(self):
        assert _classify("C") is LocaleMode.C
        assert _classify("POSIX") is LocaleMode.C
        assert _classify("") is LocaleMode.C

    def test_utf8_variants(self):
        assert _classify("en_US.UTF-8") is LocaleMode.UTF8
        assert _classify("C.UTF-8") is LocaleMode.UTF8
        assert _classify("en_GB.utf8") is LocaleMode.UTF8

    def test_other_mode(self):
        assert _classify("en_US.ISO8859-1") is LocaleMode.OTHER
        assert _classify("de_DE.ISO8859-15") is LocaleMode.OTHER


class TestPrecedence:
    """bash: LC_ALL > LC_{CTYPE,COLLATE} > LANG > C; empty values are skipped."""

    def test_lc_all_wins(self):
        env = {"LC_ALL": "C", "LC_CTYPE": "en_US.UTF-8", "LANG": "en_US.UTF-8"}
        assert _effective(env, ("LC_ALL", "LC_CTYPE", "LANG")) == "C"

    def test_category_beats_lang(self):
        env = {"LC_CTYPE": "en_US.UTF-8", "LANG": "C"}
        assert _effective(env, ("LC_ALL", "LC_CTYPE", "LANG")) == "en_US.UTF-8"

    def test_lang_fallback(self):
        env = {"LANG": "en_US.UTF-8"}
        assert _effective(env, ("LC_ALL", "LC_CTYPE", "LANG")) == "en_US.UTF-8"

    def test_empty_lc_all_is_skipped(self):
        # bash: an empty LC_ALL does NOT win; LANG is used.
        env = {"LC_ALL": "", "LANG": "en_US.UTF-8"}
        assert _effective(env, ("LC_ALL", "LC_CTYPE", "LANG")) == "en_US.UTF-8"

    def test_empty_category_is_skipped(self):
        env = {"LC_CTYPE": "", "LANG": "en_US.UTF-8"}
        assert _effective(env, ("LC_ALL", "LC_CTYPE", "LANG")) == "en_US.UTF-8"

    def test_nothing_set_is_c(self):
        assert _effective({}, ("LC_ALL", "LC_CTYPE", "LANG")) == "C"


class TestProfileComputation:
    """Profile resolution WITHOUT applying setlocale (no global side effects)."""

    def test_ctype_and_collate_independent(self):
        env = {"LC_CTYPE": "en_US.UTF-8", "LC_COLLATE": "C"}
        svc = LocaleService(env, apply=False)
        assert svc.profile.ctype_mode is LocaleMode.UTF8
        assert svc.profile.collate_mode is LocaleMode.C

    def test_lc_all_overrides_both(self):
        env = {"LC_ALL": "C", "LC_CTYPE": "en_US.UTF-8", "LANG": "en_US.UTF-8"}
        svc = LocaleService(env, apply=False)
        assert svc.profile.ctype_mode is LocaleMode.C
        assert svc.profile.collate_mode is LocaleMode.C

    def test_default_c(self):
        svc = LocaleService({}, apply=False)
        assert svc.profile.ctype_name == "C"
        assert svc.profile.collate_name == "C"
        assert svc.profile.ctype_mode is LocaleMode.C


class TestInvalidLocaleFallsBackToC:
    def test_invalid_name_warns_and_falls_back(self, capsys):
        # A bogus locale that setlocale will reject -> warn + fall back to C.
        # setlocale is process-global, so snapshot and restore the ORIGINAL
        # locale (forcing "C" would flip getpreferredencoding to ASCII and
        # break later in-process tests that write non-ASCII to files).
        saved = _locale.setlocale(_locale.LC_ALL)
        try:
            svc = LocaleService({"LC_ALL": "bogus.locale.xyz"}, apply=True,
                                warn=True)
            assert svc.profile.collate_mode is LocaleMode.C
            assert svc.profile.ctype_mode is LocaleMode.C
            err = capsys.readouterr().err
            assert "cannot change locale" in err
        finally:
            _locale.setlocale(_locale.LC_ALL, saved)


class TestCollationCModeIsCodepoint:
    """Under the suite's C locale, collation == codepoint (byte) order."""

    def test_collate_key_identity(self):
        svc = LocaleService({"LC_ALL": "C"}, apply=True)
        assert svc.profile.collate_mode is LocaleMode.C
        data = ["b", "A", "a", "B", "é", "3"]
        assert sorted(data, key=svc.collate_key) == sorted(data)

    def test_compare_codepoint(self):
        svc = LocaleService({"LC_ALL": "C"}, apply=True)
        assert svc.compare("a", "B") > 0   # 'a'(97) > 'B'(66)
        assert svc.compare("B", "a") < 0
        assert svc.compare("a", "a") == 0


class TestCaseGating:
    """upper/lower/toggle: ASCII-only in C mode, Unicode (length-safe) in UTF8.

    apply=False keeps these side-effect free — case mapping never needs
    setlocale (it uses the length-safe simple_* Python mappings).
    """

    def _svc(self, name):
        return LocaleService({"LC_ALL": name}, apply=False)

    def test_c_mode_upper_ascii_only(self):
        svc = self._svc("C")
        assert svc.upper("café") == "CAFé"       # é untouched (bash-C)
        assert svc.upper("ß") == "ß"

    def test_utf8_mode_upper_unicode(self):
        svc = self._svc("en_US.UTF-8")
        assert svc.upper("café") == "CAFÉ"        # é mapped
        assert svc.upper("ß") == "ß"              # length-safe, not "SS"

    def test_c_mode_lower_ascii_only(self):
        svc = self._svc("C")
        assert svc.lower("CAFÉ") == "cafÉ"

    def test_utf8_mode_lower_unicode(self):
        assert self._svc("en_US.UTF-8").lower("CAFÉ") == "café"

    def test_c_mode_toggle_ascii_only(self):
        # aßB -> AßB toggled ASCII-only: a->A, ß->ß, B->b == "Aßb"
        assert self._svc("C").toggle("aßB") == "Aßb"

    def test_utf8_mode_toggle(self):
        assert self._svc("en_US.UTF-8").toggle("Café") == "cAFÉ"

    def test_other_mode_treated_ascii(self):
        # non-UTF-8 8-bit locale: documented ASCII fallback for case.
        svc = self._svc("en_US.ISO8859-1")
        assert svc.profile.ctype_mode is LocaleMode.OTHER
        assert svc.upper("café") == "CAFé"


class TestClassMembership:
    """POSIX class membership + the range machinery.

    UTF-8 membership uses the host libc's iswctype (needs setlocale), so those
    checks snapshot/restore the process locale. C-mode checks are side-effect
    free (apply=False, ASCII tables).
    """

    def test_c_mode_in_class_ascii(self):
        svc = LocaleService({"LC_ALL": "C"}, apply=False)
        assert svc.in_class("a", "alpha") is True
        assert svc.in_class("é", "alpha") is False   # ASCII-only in C
        assert svc.in_class("5", "digit") is True
        assert svc.in_class("٣", "digit") is False

    def test_posix_class_ranges_c_mode_is_ascii_table(self):
        from psh.core.locale_service import posix_class_ranges
        from psh.expansion.glob import _POSIX_CLASSES
        LocaleService({"LC_ALL": "C"}, apply=False)  # activate C
        assert posix_class_ranges("alpha") == _POSIX_CLASSES["alpha"]
        assert posix_class_ranges("digit") == _POSIX_CLASSES["digit"]
        assert posix_class_ranges("not_a_class") is None

    def test_range_token_format(self):
        from psh.core.locale_service import _range_token
        assert _range_token(0x61, 0x61) == "\\U00000061"
        assert _range_token(0x61, 0x7a) == "\\U00000061-\\U0000007a"

    def test_sweep_ranges_compresses(self):
        from psh.core.locale_service import _sweep_ranges
        # members {0x41..0x43, 0x61} -> "\U..41-\U..43\U..61"
        members = {0x41, 0x42, 0x43, 0x61}
        body = _sweep_ranges(lambda cp: cp in members)
        assert body == "\\U00000041-\\U00000043\\U00000061"

    def test_utf8_in_class_host_faithful(self):
        # ctypes iswctype under a UTF-8 locale — snapshot/restore the process
        # locale (setlocale is global).
        saved = _locale.setlocale(_locale.LC_ALL)
        try:
            svc = LocaleService({"LC_ALL": "en_US.UTF-8"}, apply=True, warn=False)
            if svc.profile.ctype_mode is not LocaleMode.UTF8:
                return  # locale unavailable on this host; conformance covers it
            assert svc.in_class("é", "alpha") is True
            assert svc.in_class("é", "digit") is False
            assert svc.in_class("É", "upper") is True
        finally:
            _locale.setlocale(_locale.LC_ALL, saved)


class TestGlobasciirangesRegistered:
    def test_registered_default_on(self):
        from psh.core.option_registry import OPTION_REGISTRY, SHOPT_OPTION_NAMES
        assert "globasciiranges" in SHOPT_OPTION_NAMES
        assert OPTION_REGISTRY["globasciiranges"].default is True


class TestActiveRegistration:
    def test_construction_registers_active(self):
        svc = LocaleService({"LC_ALL": "C"}, apply=False)
        assert active_locale() is svc


class TestReinit:
    """Stage 4: reinit recomputes and re-applies the profile from a fresh env so
    a live LC_*/LANG change takes effect. This pins the object-level contract
    (profile is no longer frozen-for-life, and reinit re-activates); the
    end-to-end reactivity is pinned live in tests/conformance/bash/
    test_locale_conformance.py::TestDynamicLocaleReactivity. The UTF-8 rows
    snapshot/restore the process locale (setlocale is global) and no-op on a host
    lacking en_US.UTF-8."""

    def test_reinit_c_to_utf8_changes_ctype_and_case(self):
        saved = _locale.setlocale(_locale.LC_ALL)
        try:
            svc = LocaleService({"LC_ALL": "C"}, apply=False)
            assert svc.profile.ctype_mode is LocaleMode.C
            assert svc.upper("é") == "é"                 # ASCII-only in C
            svc.reinit({"LC_ALL": "en_US.UTF-8"}, warn=False)
            if svc.profile.ctype_mode is not LocaleMode.UTF8:
                return  # locale unavailable on this host; conformance covers it
            assert svc.upper("é") == "É"                 # now Unicode-mapped
        finally:
            _locale.setlocale(_locale.LC_ALL, saved)

    def test_reinit_utf8_to_c_reverts(self):
        saved = _locale.setlocale(_locale.LC_ALL)
        try:
            svc = LocaleService({"LC_ALL": "en_US.UTF-8"}, apply=True, warn=False)
            if svc.profile.ctype_mode is not LocaleMode.UTF8:
                return
            svc.reinit({"LC_ALL": "C"}, warn=False)
            assert svc.profile.ctype_mode is LocaleMode.C
            assert svc.upper("é") == "é"                 # ASCII-only again
        finally:
            _locale.setlocale(_locale.LC_ALL, saved)

    def test_reinit_respects_precedence(self):
        # LC_ALL=C wins over an LC_CTYPE=en_US.UTF-8 — resolves to C-family, so
        # no setlocale side effect.
        svc = LocaleService({"LC_ALL": "C"}, apply=False)
        svc.reinit({"LC_CTYPE": "en_US.UTF-8", "LC_ALL": "C"}, warn=False)
        assert svc.profile.ctype_mode is LocaleMode.C

    def test_reinit_empty_value_skipped(self):
        svc = LocaleService({"LC_ALL": "C"}, apply=False)
        svc.reinit({"LC_ALL": "", "LANG": "C"}, warn=False)
        assert svc.profile.ctype_mode is LocaleMode.C

    def test_reinit_reactivates(self):
        svc = LocaleService({"LC_ALL": "C"}, apply=False)
        newer = LocaleService({"LC_ALL": "C"}, apply=False)
        assert active_locale() is newer            # most-recently-built wins
        svc.reinit({"LC_ALL": "C"}, warn=False)
        assert active_locale() is svc              # reinit re-registers
