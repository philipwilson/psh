"""Unit tests for the single authoritative identifier policy.

Reappraisal #18 Tier-3 (T3-5): all name-validation sites (assignment,
``declare``/``export``/``readonly``/``local``, ``read``, ``for``, function
names, ``${...}``) route through ``psh.lexer.unicode_support.is_valid_name``.
This pins that one predicate directly:

* ASCII identifiers ``[A-Za-z_][A-Za-z0-9_]*`` are valid in BOTH modes.
* Names that never start legally (``9x``, ``a-b``, ``a.b``, ``a b``) are
  rejected in BOTH modes.
* With posix mode OFF, Unicode-letter names (``é``, ``naïve``, ``café``) are
  ACCEPTED — psh's documented lenient extension (a divergence from bash).
* With posix mode ON, those same Unicode names are REJECTED — matching bash's
  ASCII-only rule.

``is_valid_name`` is the preferred public name; ``validate_identifier`` is the
original alias for the same object.
"""

from psh.lexer.unicode_support import (
    is_identifier_char,
    is_identifier_start,
    is_valid_name,
    validate_identifier,
)


class TestIsValidNameAlias:
    def test_alias_is_the_same_object(self):
        # One implementation, two names — not two divergent copies.
        assert is_valid_name is validate_identifier


class TestAsciiNamesValidInBothModes:
    ASCII_VALID = ["foo", "_bar", "x9", "_", "A", "CamelCase", "a1b2c3", "__init__"]

    def test_valid_default(self):
        for name in self.ASCII_VALID:
            assert is_valid_name(name, posix_mode=False), name

    def test_valid_posix(self):
        for name in self.ASCII_VALID:
            assert is_valid_name(name, posix_mode=True), name


class TestInvalidInBothModes:
    # Never a legal identifier in bash (either mode) nor under the psh rule.
    INVALID_BOTH = ["9x", "a-b", "a.b", "a b", "", "1", "-x", "x!", "a=b", "@"]

    def test_rejected_default(self):
        for name in self.INVALID_BOTH:
            assert not is_valid_name(name, posix_mode=False), name

    def test_rejected_posix(self):
        for name in self.INVALID_BOTH:
            assert not is_valid_name(name, posix_mode=True), name


class TestUnicodeGatedOnPosix:
    # psh's DELIBERATE, documented divergence: lenient Unicode identifiers when
    # posix mode is OFF; ASCII-only (matching bash) when it is ON.
    UNICODE_NAMES = ["é", "naïve", "café", "Ω", "变量", "π", "ñ"]

    def test_accepted_when_not_posix(self):
        for name in self.UNICODE_NAMES:
            assert is_valid_name(name, posix_mode=False), name

    def test_rejected_under_posix(self):
        for name in self.UNICODE_NAMES:
            assert not is_valid_name(name, posix_mode=True), name


class TestIdentifierStartAndChar:
    def test_start_ascii(self):
        assert is_identifier_start("a")
        assert is_identifier_start("_")
        assert not is_identifier_start("9")
        assert not is_identifier_start("-")

    def test_start_unicode_gated(self):
        assert is_identifier_start("é", posix_mode=False)
        assert not is_identifier_start("é", posix_mode=True)

    def test_char_digits_ok_after_start(self):
        assert is_identifier_char("9")
        assert is_identifier_char("_")
        assert not is_identifier_char("-")

    def test_char_unicode_gated(self):
        assert is_identifier_char("é", posix_mode=False)
        assert not is_identifier_char("é", posix_mode=True)


class TestDefaultParameterIsLenient:
    # Callers that omit posix_mode get the lenient (non-posix) rule, so the
    # non-posix default behavior is preserved everywhere.
    def test_default_is_non_posix(self):
        assert is_valid_name("é")
        assert is_identifier_start("é")
        assert is_identifier_char("é")
