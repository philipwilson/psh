"""Unit tests for grammar-aware command-substitution extent scanning.

The extent of ``$(...)`` cannot be found by counting parentheses: case
patterns contain an unmatched ``)``, and parens inside quotes, comments,
and heredoc bodies are not delimiters. ``find_command_substitution_end``
(psh/lexer/pure_helpers.py) is the scanner that understands just enough
shell grammar to find the real closer; these tests pin its behavior both
directly and through the lexer's COMMAND_SUB token values.
"""

import pytest

from psh.lexer import tokenize
from psh.lexer.pure_helpers import find_command_substitution_end
from psh.lexer.token_types import TokenType


def scan(text_after_dollar_paren):
    """Scan text as the content following '$(' and return (content, found)."""
    end, found = find_command_substitution_end(text_after_dollar_paren, 0)
    return text_after_dollar_paren[:end - 1] if found else None, found


class TestScannerBasics:
    """Plain extents, quotes, escapes."""

    def test_simple_command(self):
        content, found = scan('echo hello)')
        assert found and content == 'echo hello'

    def test_nested_parens_balance(self):
        content, found = scan('echo (nested) word) tail')
        assert found and content == 'echo (nested) word'

    def test_unclosed_returns_not_found(self):
        end, found = find_command_substitution_end('echo hello', 0)
        assert not found and end == len('echo hello')

    def test_paren_in_single_quotes_ignored(self):
        content, found = scan("echo ')' x)")
        assert found and content == "echo ')' x"

    def test_paren_in_double_quotes_ignored(self):
        content, found = scan('echo ")" x)')
        assert found and content == 'echo ")" x'

    def test_escaped_paren_ignored(self):
        content, found = scan('echo \\) x)')
        assert found and content == 'echo \\) x'

    def test_paren_in_backticks_ignored(self):
        content, found = scan('echo `echo ")"` x)')
        assert found and content == 'echo `echo ")"` x'

    def test_paren_in_ansi_c_quotes_ignored(self):
        content, found = scan("echo $'a)b' x)")
        assert found and content == "echo $'a)b' x"

    def test_unclosed_single_quote(self):
        _, found = scan("echo 'oops)")
        assert not found

    def test_unclosed_double_quote(self):
        _, found = scan('echo "oops)')
        assert not found


class TestScannerCasePatterns:
    """The headline fix: bare `pattern)` inside case statements."""

    def test_headline_case_pattern(self):
        content, found = scan('case x in x) echo inner;; esac)')
        assert found and content == 'case x in x) echo inner;; esac'

    def test_multi_branch_case(self):
        content, found = scan('case b in a) echo A;; b) echo B;; c) echo C;; esac)')
        assert found
        assert content == 'case b in a) echo A;; b) echo B;; c) echo C;; esac'

    def test_alternation_pattern(self):
        content, found = scan('case y in x|y) echo XY;; esac)')
        assert found and content == 'case y in x|y) echo XY;; esac'

    def test_leading_paren_pattern_form(self):
        content, found = scan('case x in (x) echo inner;; esac)')
        assert found and content == 'case x in (x) echo inner;; esac'

    def test_fallthrough_operators(self):
        for op in (';;', ';&', ';;&'):
            content, found = scan(f'case x in x) echo one{op} y) echo two;; esac)')
            assert found, op
            assert content == f'case x in x) echo one{op} y) echo two;; esac'

    def test_esac_then_more_commands(self):
        content, found = scan('case x in x) echo a;; esac; echo b)')
        assert found and content == 'case x in x) echo a;; esac; echo b'

    def test_esac_at_body_command_position(self):
        # last branch may omit ';;' — esac is then at command position
        content, found = scan('case x in x) echo a; esac)')
        assert found and content == 'case x in x) echo a; esac'

    def test_esac_as_argument_is_not_keyword(self):
        content, found = scan('case x in x) echo esac;; esac)')
        assert found and content == 'case x in x) echo esac;; esac'

    def test_nested_case_in_body(self):
        content, found = scan('case x in x) case y in y) echo n;; esac;; esac)')
        assert found
        assert content == 'case x in x) case y in y) echo n;; esac;; esac'

    def test_case_not_keyword_after_word(self):
        # `case` is an argument of echo, not a case statement; the first
        # bare ')' closes the substitution (bash agrees).
        content, found = scan('echo case in x)')
        assert found and content == 'echo case in x'

    def test_quoted_subject_and_pattern(self):
        content, found = scan('case "x" in "x") echo q;; esac)')
        assert found and content == 'case "x" in "x") echo q;; esac'

    def test_cmdsub_as_case_subject(self):
        content, found = scan('case $(echo x) in x) echo subj;; esac)')
        assert found and content == 'case $(echo x) in x) echo subj;; esac'

    def test_extglob_parens_in_pattern_balance(self):
        content, found = scan('case abc in a@(b|c)c) echo ext;; esac)')
        assert found and content == 'case abc in a@(b|c)c) echo ext;; esac'

    def test_glob_star_pattern(self):
        content, found = scan('case foo in f*) echo glob;; esac)')
        assert found and content == 'case foo in f*) echo glob;; esac'

    def test_empty_case_branch(self):
        content, found = scan('case x in x) ;; esac; echo after)')
        assert found and content == 'case x in x) ;; esac; echo after'

    def test_case_across_newlines(self):
        text = 'case x in\nx) echo nl;;\nesac)'
        content, found = scan(text)
        assert found and content == text[:-1]

    def test_no_space_before_esac(self):
        content, found = scan('case x in x) echo n;;esac)')
        assert found and content == 'case x in x) echo n;;esac'

    def test_case_keyword_after_reserved_words(self):
        content, found = scan('if true; then case x in x) echo y;; esac; fi)')
        assert found
        assert content == 'if true; then case x in x) echo y;; esac; fi'

    def test_case_in_subshell_group(self):
        content, found = scan(' (case x in x) echo grp;; esac) )')
        assert found and content == ' (case x in x) echo grp;; esac) '


class TestScannerCommentsAndHeredocs:
    """Parens hidden by comments and heredoc bodies."""

    def test_comment_hides_paren(self):
        content, found = scan('# comment with )\necho hi)')
        assert found and content == '# comment with )\necho hi'

    def test_comment_to_end_of_input_is_unclosed(self):
        _, found = scan('echo hi # not-a-paren )')
        assert not found

    def test_hash_mid_word_is_not_comment(self):
        content, found = scan('echo a#b)')
        assert found and content == 'echo a#b'

    def test_heredoc_body_paren_ignored(self):
        text = 'cat <<EOF\n)\nEOF\n)'
        content, found = scan(text)
        assert found and content == 'cat <<EOF\n)\nEOF\n'

    def test_quoted_heredoc_delimiter(self):
        text = 'cat <<"EOF"\na ) b\nEOF\n)'
        content, found = scan(text)
        assert found and content == 'cat <<"EOF"\na ) b\nEOF\n'

    def test_heredoc_strip_tabs(self):
        text = 'cat <<-EOF\n\t)\n\tEOF\n)'
        content, found = scan(text)
        assert found and content == 'cat <<-EOF\n\t)\n\tEOF\n'

    def test_two_heredocs_in_order(self):
        text = 'cat <<A <<B\n)\nA\nx )\nB\n)'
        content, found = scan(text)
        assert found and content == 'cat <<A <<B\n)\nA\nx )\nB\n'

    def test_unterminated_heredoc_body_is_unclosed(self):
        _, found = scan('cat <<EOF\nbody line\n')
        assert not found

    def test_herestring_is_not_heredoc(self):
        content, found = scan('cat <<< "abc")')
        assert found and content == 'cat <<< "abc"'


class TestScannerNesting:
    """Nested expansions and arithmetic."""

    def test_nested_cmdsub_with_case(self):
        content, found = scan('echo $(case x in x) echo i;; esac))')
        assert found and content == 'echo $(case x in x) echo i;; esac)'

    def test_arithmetic_inside(self):
        content, found = scan('echo $((1 + 2)))')
        assert found and content == 'echo $((1 + 2))'

    def test_case_in_double_quoted_nested_cmdsub(self):
        content, found = scan('echo "$(case x in x) echo dq;; esac)")')
        assert found and content == 'echo "$(case x in x) echo dq;; esac)"'

    def test_brace_expansion_with_paren_default(self):
        content, found = scan('echo ${v:-)} x)')
        assert found and content == 'echo ${v:-)} x'

    def test_arithmetic_command_at_command_position(self):
        content, found = scan('((x > 0)); echo done)')
        assert found and content == '((x > 0)); echo done'


class TestLexerTokenExtents:
    """The lexer's COMMAND_SUB tokens use the scanner."""

    def cmdsub_token(self, source):
        tokens = tokenize(source)
        subs = [t for t in tokens if t.type == TokenType.COMMAND_SUB]
        assert len(subs) == 1, [t.type for t in tokens]
        return subs[0]

    def test_headline_token_value(self):
        tok = self.cmdsub_token('echo $(case x in x) echo inner;; esac)')
        assert tok.value == '$(case x in x) echo inner;; esac)'

    def test_token_value_with_comment(self):
        tok = self.cmdsub_token('echo $(# comment with )\necho hi)')
        assert tok.value == '$(# comment with )\necho hi)'

    def test_token_value_with_heredoc(self):
        tok = self.cmdsub_token('echo $(cat <<EOF\n)\nEOF\n)')
        assert tok.value == '$(cat <<EOF\n)\nEOF\n)'

    def test_process_substitution_with_case(self):
        tokens = tokenize('cat <(case x in x) echo psub;; esac)')
        psubs = [t for t in tokens if t.type == TokenType.PROCESS_SUB_IN]
        assert len(psubs) == 1
        assert psubs[0].value == '<(case x in x) echo psub;; esac)'

    def test_unclosed_cmdsub_marked_via_parts(self):
        # `$(# comment )` swallows the rest of the line, so the truncated
        # token text still ends with ')' — the unclosed marker must survive
        # in the token parts for incomplete-input detection.
        tokens = tokenize('echo $(# comment with )')
        sub = [t for t in tokens if t.type == TokenType.COMMAND_SUB][0]
        parts = getattr(sub, 'parts', None)
        assert parts and any(
            p.expansion_type == 'command_unclosed' for p in parts)


class TestUnclosedIsIncompleteInput:
    """Unclosed expansions raise ParseError with at_eof=True so multiline
    gathering (scripts, -c, interactive PS2) keeps reading lines."""

    def parse_error(self, source):
        from psh.parser import Parser
        from psh.parser.recursive_descent.helpers import ParseError
        tokens = tokenize(source)
        with pytest.raises(ParseError) as exc:
            Parser(tokens, source_text=source).parse()
        return exc.value

    def test_unclosed_cmdsub_at_eof(self):
        assert self.parse_error('echo $(case x in').at_eof

    def test_unclosed_cmdsub_via_comment_at_eof(self):
        assert self.parse_error('echo $(# comment )').at_eof

    def test_unclosed_heredoc_in_cmdsub_at_eof(self):
        assert self.parse_error('echo $(cat <<EOF').at_eof
