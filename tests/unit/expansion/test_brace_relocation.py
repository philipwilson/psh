"""Brace expansion relocated to the token stream (post-tokenization).

These cover the bugs the relocation fixes, plus parity cases that the old
expand-then-re-lex path got right only by accident.
"""

import pytest


def _out(captured_shell, cmd):
    captured_shell.clear_output()
    assert captured_shell.run_command(cmd) == 0
    return captured_shell.get_stdout()


class TestAssignmentRhsNotExpanded:
    """#11: a statement-position assignment RHS is not brace-expanded."""

    def test_scalar_list(self, captured_shell):
        assert _out(captured_shell, 'a={x,y}; echo "[$a]"') == "[{x,y}]\n"

    def test_scalar_range(self, captured_shell):
        assert _out(captured_shell, 'a={1..3}; echo "[$a]"') == "[{1..3}]\n"

    def test_scalar_prefix(self, captured_shell):
        assert _out(captured_shell, 'a=pre{x,y}; echo "[$a]"') == "[pre{x,y}]\n"

    def test_multiple_assignment_prefix(self, captured_shell):
        # Both leading assignments are suppressed; command still runs.
        assert _out(captured_shell, 'a={1,2} b={3,4} echo done') == "done\n"

    def test_argument_position_is_expanded(self, captured_shell):
        # As an argument (not a statement-position assignment), bash DOES expand.
        assert _out(captured_shell, 'echo a={x,y}') == "a=x a=y\n"


class TestMetacharRangeNoCrash:
    """#12: a range generating shell metacharacters no longer re-lexes/crashes."""

    def test_range_crossing_metachars(self, captured_shell):
        # Z..a spans [ \ ] ^ _ ` ; previously this raised a parse error.
        rc = captured_shell.run_command('printf "%s\\n" {Z..a} | tr -d "\\n"')
        # Just assert it runs without a parse error and emits 8 chars.
        assert rc == 0


class TestNestedBraces:
    """The lexer now tokenizes raw nested braces ({{...}}) correctly."""

    def test_nested_list_and_ranges(self, captured_shell):
        assert _out(captured_shell, 'echo {{1..3},{a..c}}') == "1 2 3 a b c\n"

    def test_deeply_nested(self, captured_shell):
        assert _out(captured_shell, 'echo {a,{b,{c,d}}}') == "a b c d\n"


class TestEmptyItemParity:
    """Empty brace results are dropped like bash ({a,,b} -> a b)."""

    def test_empty_middle(self, captured_shell):
        assert _out(captured_shell, 'echo {a,,b}') == "a b\n"

    def test_empty_leading(self, captured_shell):
        assert _out(captured_shell, 'echo {,b}') == "b\n"

    def test_empty_with_prefix_kept(self, captured_shell):
        # The empty item fused with the prefix is non-empty -> kept.
        assert _out(captured_shell, 'echo x{a,,b}') == "xa x xb\n"

    def test_all_empty_yields_nothing(self, captured_shell):
        assert _out(captured_shell, 'set -- {,}; echo $#') == "0\n"


class TestQuotedBraceItems:
    """#20: quoted items in a brace expression (split across adjacent tokens)."""

    def test_quoted_bracket(self, captured_shell):
        assert _out(captured_shell, 'echo {"[",x}') == "[ x\n"

    def test_quoted_glob_stays_literal(self, captured_shell):
        # The quoted * must NOT be globbed.
        assert _out(captured_shell, 'echo {"*",x}') == "* x\n"

    def test_single_quoted_items(self, captured_shell):
        assert _out(captured_shell, "echo {'a','b'}") == "a b\n"

    def test_mixed_quoted_unquoted(self, captured_shell):
        assert _out(captured_shell, 'echo {x,"y"}') == "x y\n"

    def test_prefix_postfix_with_quoted_item(self, captured_shell):
        assert _out(captured_shell, 'echo pre{"a",b}post') == "preapost prebpost\n"

    def test_quoted_space_item_stays_one_word(self, captured_shell):
        # The space inside the quoted item must be preserved (one argument).
        captured_shell.clear_output()
        assert captured_shell.run_command('printf "<%s>" {"a b",x}') == 0
        assert captured_shell.get_stdout() == "<a b><x>"


class TestBraceParity:
    def test_basic_list(self, captured_shell):
        assert _out(captured_shell, 'echo {a,b,c}') == "a b c\n"

    def test_prefix_postfix(self, captured_shell):
        assert _out(captured_shell, 'echo pre{a,b}post') == "preapost prebpost\n"

    def test_array_assignment_content_expands(self, captured_shell):
        assert _out(captured_shell, 'arr=({a,b} c); echo "${arr[@]}"') == "a b c\n"

    def test_brace_group_unaffected(self, captured_shell):
        assert _out(captured_shell, '{ echo hi; }') == "hi\n"
