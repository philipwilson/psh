"""Tests for the centralized assignment-word / shell-name regex family.

These patterns live in :mod:`psh.core.assignment_utils` (the single home for
the shell's ASCII ``NAME=value`` / ``NAME[sub]=value`` / ``NAME+=value`` shapes).
This module pins their match/reject behavior AND guards the call sites that were
de-duplicated to route through them, so a future edit cannot silently let a
site's copy diverge again.

Note the deliberate distinction (see the module docstring in assignment_utils):
these regexes are the ASCII lexer/parser-time *shape* of a name; the runtime
identifier *policy* (Unicode-aware unless ``set -o posix``) is
``psh.lexer.unicode_support.is_valid_name`` and is intentionally separate.
"""

from psh.core.assignment_utils import (
    ASSIGNMENT_PREFIX_RE,
    ASSIGNMENT_WORD_RE,
    NAME_RE,
    SHELL_NAME,
)


class TestNameRe:
    """NAME_RE: a whole string that is exactly a bare ASCII shell name."""

    def test_accepts_plain_names(self):
        for name in ("a", "_", "foo", "FOO", "_x9", "abc_123", "A1B2"):
            assert NAME_RE.match(name), name

    def test_rejects_non_names(self):
        for bad in ("", "1a", "9", "a-b", "a.b", "a b", "a=", "a[0]", "é"):
            assert not NAME_RE.match(bad), bad

    def test_dollar_anchor_accepts_trailing_newline(self):
        # NAME_RE is `$`-anchored (byte-for-byte the pre-refactor
        # _SIMPLE_NAME_RE / _IDENTIFIER_RE), so `$` matches before a trailing
        # newline. This is exactly why ast_nodes.words keeps a separate
        # \Z-anchored _BARE_VAR_NAME: the two are NOT interchangeable and were
        # deliberately not merged.
        from psh.ast_nodes.words import _BARE_VAR_NAME
        assert NAME_RE.match("a\n")           # `$` before the newline
        assert not _BARE_VAR_NAME.match("a\n")  # `\Z` requires absolute end


class TestAssignmentWordRe:
    """ASSIGNMENT_WORD_RE: NAME, optional [subscript] (may be empty), optional
    '+', then '='. This is what bash's lexer reads as an assignment word."""

    def test_scalar_and_append(self):
        for word in ("a=", "a=1", "foo=bar", "_x=", "a+=", "a+=x"):
            assert ASSIGNMENT_WORD_RE.match(word), word

    def test_subscripted_element(self):
        # Subscript may hold anything but ']' — including an expansion — and
        # may even be empty (bash's lexer shape; the runtime rejects `a[]=`).
        for word in ("a[0]=", "a[$i]=", "a[k]=v", "a[]=", "a[i+1]+=x"):
            assert ASSIGNMENT_WORD_RE.match(word), word

    def test_rejects_non_assignments(self):
        for bad in ("=x", "1a=", "a.b=", "a-b=", "a =", "notanassignment",
                    "a", "[0]=x"):
            assert not ASSIGNMENT_WORD_RE.match(bad), bad


class TestAssignmentPrefixRe:
    """ASSIGNMENT_PREFIX_RE: NAME, optional '+', then '=' — NO subscript.

    Deliberately distinct from ASSIGNMENT_WORD_RE: the declaration-builtin value
    handler recognises only ``NAME=`` / ``NAME+=`` prefixes.
    """

    def test_scalar_and_append(self):
        for word in ("a=", "a=1", "foo=bar", "a+=", "a+=x"):
            assert ASSIGNMENT_PREFIX_RE.match(word), word

    def test_does_not_match_subscripted_form(self):
        # This is the intentional divergence from ASSIGNMENT_WORD_RE.
        for word in ("a[0]=", "a[$i]=", "a[]="):
            assert not ASSIGNMENT_PREFIX_RE.match(word), word

    def test_rejects_non_assignments(self):
        for bad in ("=x", "1a=", "a.b=", "a"):
            assert not ASSIGNMENT_PREFIX_RE.match(bad), bad


class TestFragmentIsAsciiOnly:
    """SHELL_NAME is ASCII-only by design (distinct from is_valid_name)."""

    def test_shell_name_value(self):
        assert SHELL_NAME == r"[A-Za-z_][A-Za-z0-9_]*"

    def test_patterns_are_built_from_the_fragment(self):
        assert NAME_RE.pattern == rf"^{SHELL_NAME}$"
        assert ASSIGNMENT_WORD_RE.pattern == rf"^{SHELL_NAME}(\[[^\]]*\])?\+?="
        assert ASSIGNMENT_PREFIX_RE.pattern == rf"^{SHELL_NAME}\+?="


class TestCallSitesRouteToCanonical:
    """Guard: the de-duplicated sites must keep using the canonical patterns
    (identity for merged sites; byte-identical pattern for fragment-sourced or
    deliberately-local sites), so nobody silently re-introduces a divergent copy.
    """

    def test_function_parser_uses_canonical_assignment_word(self):
        from psh.parser.recursive_descent.parsers import functions
        assert functions.ASSIGNMENT_WORD_RE is ASSIGNMENT_WORD_RE

    def test_word_brace_expander_uses_canonical(self):
        # Brace expansion moved to the Word stage (v0.678); the fusion of a
        # trailing name-char run into a bare $name uses the canonical NAME_RE.
        from psh.expansion import brace_expansion_words as bew
        assert bew.NAME_RE is NAME_RE

    def test_expansion_manager_uses_canonical_prefix(self):
        from psh.expansion import manager
        assert manager.ASSIGNMENT_PREFIX_RE is ASSIGNMENT_PREFIX_RE

    def test_word_builder_simple_var_sourced_from_fragment(self):
        from psh.parser.recursive_descent.support import word_builder
        assert word_builder._SIMPLE_VAR_RE.pattern == rf"^{SHELL_NAME}(\[.+?\])?$"

    def test_printf_identifier_mirrors_name_re(self):
        # printf_formatter is intentionally shell-dependency-free, so it keeps a
        # local copy; pin it byte-identical to NAME_RE so the two stay in sync.
        from psh.utils import printf_formatter
        assert printf_formatter._IDENTIFIER_RE.pattern == NAME_RE.pattern

    def test_bare_var_name_uses_fragment_with_absolute_end(self):
        # ast_nodes.words keeps a local \Z-anchored copy (deliberately distinct
        # from NAME_RE's `$`, and in a low-level module to avoid an import cycle).
        from psh.ast_nodes import words
        assert words._BARE_VAR_NAME.pattern == SHELL_NAME + r"\Z"
