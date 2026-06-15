"""Unit tests for the alias token-stream transform (AliasManager.expand_aliases).

R8.6b made alias expansion a token-stream transform at the lex->parse
boundary. These tests exercise the transform directly: command-position
detection, the recursion guard, trailing-space chaining, quoted-word
suppression, and the same-stream definition overlay (psh's same-line
expansion). Behavioural parity with bash lives in the conformance suite;
these pin the mechanism.
"""

from psh.expansion.aliases import AliasManager
from psh.lexer import tokenize
from psh.lexer.token_types import TokenType


def _expand(src, **aliases):
    am = AliasManager()
    for name, value in aliases.items():
        am.define_alias(name, value)
    toks = [t for t in tokenize(src) if t.type != TokenType.EOF]
    return ' '.join(t.value for t in am.expand_aliases(toks))


class TestCommandPosition:
    def test_command_position_start(self):
        assert _expand('g hi', g='echo G') == 'echo G hi'

    def test_argument_not_expanded(self):
        assert _expand('echo g', g='echo G') == 'echo g'

    def test_after_separators(self):
        assert _expand('true; g', g='echo G') == 'true ; echo G'
        assert _expand('true && g', g='echo G') == 'true && echo G'
        assert _expand('false || g', g='echo G') == 'false || echo G'
        assert _expand('echo x | g', g='echo G') == 'echo x | echo G'

    def test_inside_compounds(self):
        assert _expand('if true; then g; fi', g='echo G') == \
            'if true ; then echo G ; fi'
        assert _expand('for x in 1; do g; done', g='echo G') == \
            'for x in 1 ; do echo G ; done'
        assert _expand('{ g; }', g='echo G') == '{ echo G ; }'
        assert _expand('( g )', g='echo G') == '( echo G )'

    def test_case_body_expands_selector_and_pattern_do_not(self):
        # selector `g` (after case) and pattern `g` (after in / ;;) are NOT
        # commands; only the body (after `)`) is.
        assert _expand('case g in g) g;; esac', g='echo G') == \
            'case g in g ) echo G ;; esac'

    def test_for_item_after_in_not_expanded(self):
        assert _expand('for x in g; do echo x; done', g='echo G') == \
            'for x in g ; do echo x ; done'


class TestQuotedWord:
    def test_single_quoted_command_word_not_expanded(self):
        # 'g' is a STRING token, not a bare WORD.
        assert _expand("'g' hi", g='echo G') == 'g hi'

    def test_double_quoted_command_word_not_expanded(self):
        assert _expand('"g" hi', g='echo G') == 'g hi'


class TestRecursionGuard:
    def test_self_reference_expands_once(self):
        # `echo` -> `echo wrapped`; the leading `echo` is the alias being
        # expanded, so it is not re-expanded.
        assert _expand('echo hi', echo='echo wrapped') == 'echo wrapped hi'

    def test_mutual_reference(self):
        assert _expand('a', a='b X', b='echo B') == 'echo B X'


class TestTrailingSpaceChaining:
    def test_two_level(self):
        assert _expand('a b', a='echo ', b='B') == 'echo B'

    def test_no_chain_without_space(self):
        assert _expand('a b', a='echo', b='B') == 'echo b'

    def test_three_level(self):
        assert _expand('a b c', a='echo ', b='nice ', c='C') == 'echo nice C'


class TestSameStreamDefinitionOverlay:
    """psh expands an alias defined EARLIER in the same token stream."""

    def test_inline_definition_then_use(self):
        am = AliasManager()  # no pre-existing aliases
        toks = [t for t in tokenize('alias x=echo; x hi')
                if t.type != TokenType.EOF]
        out = ' '.join(t.value for t in am.expand_aliases(toks))
        assert out == 'alias x=echo ; echo hi'
        # The persistent table is NOT mutated by the transform.
        assert not am.has_alias('x')

    def test_quoted_value_definition_then_use(self):
        am = AliasManager()
        toks = [t for t in tokenize("alias ll='echo LL'; ll")
                if t.type != TokenType.EOF]
        out = ' '.join(t.value for t in am.expand_aliases(toks))
        assert out == "alias ll= echo LL ; echo LL"

    def test_unalias_in_stream_removes_overlay(self):
        am = AliasManager()
        am.define_alias('g', 'echo G')
        toks = [t for t in tokenize('unalias g; g')
                if t.type != TokenType.EOF]
        out = ' '.join(t.value for t in am.expand_aliases(toks))
        # After `unalias g` in the same stream, `g` is no longer expanded.
        assert out == 'unalias g ; g'
        # Persistent table untouched by the transform overlay.
        assert am.has_alias('g')


class TestNoAliases:
    def test_empty_manager_returns_input_unchanged(self):
        toks = tokenize('echo hi')
        am = AliasManager()
        assert am.expand_aliases(toks) is toks
