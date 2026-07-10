"""Unit pins for the shared array-init flat-text helper (task #6 (ii))."""

from psh.parser.array_flat_text import process_unquoted_element_escapes


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
