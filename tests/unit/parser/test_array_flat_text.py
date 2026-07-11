"""Unit pins for the shared array-init flat-text helper (task #6 (ii))."""

from psh.expansion.word_expander import WordExpander
from psh.parser.array_flat_text import (
    array_init_argv_key,
    process_unquoted_element_escapes,
)


class TestProcessUnquotedElementEscapes:
    def test_escaped_dollar_collapses_to_fixed_point(self):
        # \$ -> $ ; the result has no backslash, so it equals the argv the
        # declaration builtin looks its structured init up by.
        assert process_unquoted_element_escapes('arr=(a\\$b c)') == 'arr=(a$b c)'

    def test_escaped_tab_letter_drops_backslash(self):
        assert process_unquoted_element_escapes('arr=(a\\tb c)') == 'arr=(atb c)'

    def test_quoted_element_collapses_uniformly(self):
        # The whole flat text is one unquoted literal to argv expansion, so the
        # embedded quotes are literal chars and \$ collapses regardless.
        assert process_unquoted_element_escapes('arr=("a\\$b" c)') == 'arr=("a$b" c)'

    def test_residual_backslash_keeps_verbatim(self):
        # \\ collapses to a single '\' which is NOT a fixed point (argv would
        # collapse it again), so no escape-free key exists — keep the verbatim
        # text rather than diverge from the raw form.
        assert process_unquoted_element_escapes('arr=(a\\\\b c)') == 'arr=(a\\\\b c)'

    def test_no_backslash_is_identity(self):
        assert process_unquoted_element_escapes('arr=(a b c)') == 'arr=(a b c)'

    def test_lone_trailing_backslash_kept(self):
        assert process_unquoted_element_escapes('x\\') == 'x\\'


class TestArrayInitArgvKey:
    """The declaration-builtin lookup key must equal the runtime argv (task #38).

    The residual-backslash case is why keying by the verbatim flat text missed:
    the guarded flat text keeps ``a\\b`` (2 bs) so the LiteralPart still expands
    to ``a\b`` (1 bs) — but the KEY must be that 1-bs argv, not the 2-bs text.
    """

    def test_residual_backslash_collapses_to_argv(self):
        # guarded flat text (2 bs) -> the argv the builtin actually receives
        # (1 bs, one unquoted-escape collapse). This is the residual (i) fix.
        assert array_init_argv_key('arr=(a\\\\b c)') == 'arr=(a\\b c)'

    def test_escape_free_is_identity(self):
        # ordinary arrays are byte-identical through the new keying (idempotent).
        assert array_init_argv_key('arr=(1 2 3)') == 'arr=(1 2 3)'
        assert array_init_argv_key('arr=(a$b c)') == 'arr=(a$b c)'
        assert array_init_argv_key('h=([k]=v)') == 'h=([k]=v)'

    def test_key_equals_the_expansion_transform(self):
        # It IS the canonical expansion transform (no fork): for any flat text,
        # the key equals WordExpander._process_unquoted_escapes of it.
        for t in ('arr=(a\\\\b c)', 'arr=(a\\$b)', 'arr=(x)', 'a=([i]=1 j)'):
            assert array_init_argv_key(t) == WordExpander._process_unquoted_escapes(t)[0]
