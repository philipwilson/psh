"""
Regression tests for parser issues from implementation review (2026-02-09).

Each test group corresponds to one of the 7 fixes committed as part of
the 2026-02-09 parser implementation review (the review document itself
was never committed; these tests pin the fixes).
"""

import subprocess
import sys

import pytest

from psh.ast_nodes import CaseConditional, SelectLoop
from psh.lexer import tokenize
from psh.parser import Parser
from psh.parser.recursive_descent.helpers import ParseError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse(source: str):
    """Tokenize and parse a shell command, returning the AST."""
    tokens = tokenize(source)
    parser = Parser(tokens, source_text=source)
    return parser.parse()


def _find_nodes(ast, node_type, _visited=None):
    """Recursively find all nodes of a given type in the AST."""
    if _visited is None:
        _visited = set()
    obj_id = id(ast)
    if obj_id in _visited:
        return []
    _visited.add(obj_id)

    results = []
    if isinstance(ast, node_type):
        results.append(ast)
    if hasattr(ast, '__dict__'):
        for attr in vars(ast).values():
            if isinstance(attr, list):
                for item in attr:
                    if hasattr(item, '__dict__'):
                        results.extend(_find_nodes(item, node_type, _visited))
            elif isinstance(attr, tuple):
                for item in attr:
                    if hasattr(item, '__dict__'):
                        results.extend(_find_nodes(item, node_type, _visited))
            elif hasattr(attr, '__dict__'):
                results.extend(_find_nodes(attr, node_type, _visited))
    return results


# ===========================================================================
# Commit 1: Fix non-terminating loop in case parsing (LPAREN)
# ===========================================================================

class TestCaseLeadingParen:
    """Tests for bash's optional (pattern) syntax in case statements."""

    def test_case_leading_paren(self):
        """case x in (foo) echo yes;; esac  -- should parse and produce match."""
        ast = parse('case x in (foo) echo yes;; esac')
        cases = _find_nodes(ast, CaseConditional)
        assert len(cases) == 1
        assert len(cases[0].items) == 1
        assert cases[0].items[0].patterns[0].pattern == 'foo'

    def test_case_mixed_paren_styles(self):
        """Mix of (pat) and pat) in one case statement."""
        source = 'case x in (a) echo a;; b) echo b;; (c|d) echo cd;; esac'
        ast = parse(source)
        cases = _find_nodes(ast, CaseConditional)
        assert len(cases) == 1
        items = cases[0].items
        assert len(items) == 3
        assert items[0].patterns[0].pattern == 'a'
        assert items[1].patterns[0].pattern == 'b'
        assert items[2].patterns[0].pattern == 'c'
        assert items[2].patterns[1].pattern == 'd'

    def test_case_unexpected_token_no_hang(self):
        """Non-progress on unexpected token should raise ParseError, not hang."""
        # The `)` without a pattern should cause an error, not an infinite loop.
        # Use a timeout to guard against infinite loops.
        with pytest.raises(ParseError):
            parse('case x in ) echo bad;; esac')

    def test_case_leading_paren_execution(self):
        """End-to-end: (pattern) syntax should execute correctly."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'case foo in (foo) echo match;; esac'],
            capture_output=True, text=True, timeout=5
        )
        assert result.stdout.strip() == 'match'
        assert result.returncode == 0

    def test_case_leading_paren_wildcard(self):
        """Leading paren with wildcard pattern."""
        ast = parse('case hello in (*) echo any;; esac')
        cases = _find_nodes(ast, CaseConditional)
        assert cases[0].items[0].patterns[0].pattern == '*'


# ===========================================================================
# Commit 2: Preserve case terminator semantics
# ===========================================================================

class TestCaseTerminatorCapture:
    """Tests for ;; vs ;& vs ;;& terminator storage in CaseItem."""

    def test_case_item_double_semicolon_terminator(self):
        """Standard ;; terminator stored in CaseItem."""
        ast = parse('case x in a) echo a;; esac')
        cases = _find_nodes(ast, CaseConditional)
        assert cases[0].items[0].terminator == ';;'

    def test_case_item_fallthrough_terminator(self):
        """;& terminator stored in CaseItem."""
        ast = parse('case x in a) echo a;& b) echo b;; esac')
        cases = _find_nodes(ast, CaseConditional)
        assert cases[0].items[0].terminator == ';&'
        assert cases[0].items[1].terminator == ';;'

    def test_case_item_continue_testing_terminator(self):
        """;;&  terminator stored in CaseItem."""
        ast = parse('case x in a) echo a;;& b) echo b;; esac')
        cases = _find_nodes(ast, CaseConditional)
        assert cases[0].items[0].terminator == ';;&'
        assert cases[0].items[1].terminator == ';;'

    def test_case_fallthrough_execution(self):
        """End-to-end: ;& causes fall-through to next case body."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'case test in test) echo matched;& *) echo also;; esac'],
            capture_output=True, text=True, timeout=5
        )
        assert 'matched' in result.stdout
        assert 'also' in result.stdout

    def test_case_continue_testing_execution(self):
        """End-to-end: ;;& continues testing subsequent patterns."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'case abc in a*) echo first;;& *c) echo second;; *z) echo third;; esac'],
            capture_output=True, text=True, timeout=5
        )
        assert 'first' in result.stdout
        assert 'second' in result.stdout
        assert 'third' not in result.stdout


# ===========================================================================
# Commit 3: Allow leading redirections before command name
# ===========================================================================

class TestLeadingRedirects:
    """Tests for POSIX leading redirections like >out echo hi."""

    def test_leading_redirect(self, tmp_path):
        """'>out echo hi' should produce file with 'hi'."""
        outfile = tmp_path / 'out.txt'
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             f'>{outfile} echo hi'],
            capture_output=True, text=True, timeout=5
        )
        assert result.returncode == 0
        assert outfile.read_text().strip() == 'hi'

    def test_redirect_only_command_parses(self):
        """>file with no command should parse without error."""
        # POSIX allows redirect-only commands like >file
        ast = parse('>/dev/null')
        assert ast is not None

    def test_redirect_only_command_creates_file(self, tmp_path):
        """>file with no command should create/truncate the file."""
        outfile = tmp_path / 'empty.txt'
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             f'>{outfile}'],
            capture_output=True, text=True, timeout=5
        )
        assert result.returncode == 0
        assert outfile.exists()
        assert outfile.read_text() == ''

    def test_stderr_redirect_before_cmd(self):
        """2>err cmd syntax should parse without error."""
        # Just verify it parses -- the redirect is valid syntax
        ast = parse('2>/dev/null echo hello')
        assert ast is not None


# ===========================================================================
# Commit 4: Fix [[ ]] operand concatenation (adjacency check)
# ===========================================================================

class TestDoubleBracketAdjacency:
    """Tests for [[ ]] operand adjacency checking."""

    def test_double_bracket_rejects_bare_words(self):
        """[[ a b ]] with whitespace between a and b should raise ParseError."""
        with pytest.raises(ParseError):
            parse('[[ a b ]]')

    def test_double_bracket_valid_unary(self):
        """[[ -f file ]] should still work correctly."""
        ast = parse('[[ -f /etc/hosts ]]')
        assert ast is not None

    def test_double_bracket_string_comparison(self):
        """[[ a == b ]] should work correctly."""
        ast = parse('[[ hello == world ]]')
        assert ast is not None

    def test_double_bracket_negation(self):
        """[[ ! -f file ]] should work correctly."""
        ast = parse('[[ ! -f /nonexistent ]]')
        assert ast is not None


# ===========================================================================
# Commit 5: Allow select without in
# ===========================================================================

class TestSelectWithoutIn:
    """Tests for select name; do ... done (no 'in' clause)."""

    def test_select_without_in_parses(self):
        """select x; do echo $x; done should parse with items=['$@']."""
        ast = parse('select x; do echo $x; done')
        selects = _find_nodes(ast, SelectLoop)
        assert len(selects) == 1
        assert selects[0].variable == 'x'
        assert selects[0].items == ['$@']

    def test_select_with_in_still_works(self):
        """select x in a b c; do echo $x; done should still parse normally."""
        ast = parse('select x in a b c; do echo $x; done')
        selects = _find_nodes(ast, SelectLoop)
        assert len(selects) == 1
        assert selects[0].variable == 'x'
        assert 'a' in selects[0].items
        assert 'b' in selects[0].items
        assert 'c' in selects[0].items


# ===========================================================================
# Commit 6: Fix parse_with_heredocs() dict handling
# ===========================================================================

class TestParseWithHeredocs:
    """Tests for parse_with_heredocs() dict and string content formats.

    Targets the module-level function (the production path); the duplicate
    Parser.parse_with_heredocs method was removed in v0.256.0.
    """

    def _first_heredoc_redirect(self, ast):
        from psh.ast_nodes import Redirect
        reds = [r for r in _find_nodes(ast, Redirect) if r.type in ('<<', '<<-')]
        assert len(reds) == 1
        return reds[0]

    def test_parse_with_heredocs_dict_format(self):
        """Dict-format map attaches content (and quoted) at construction."""
        from psh.lexer import tokenize_with_heredocs
        from psh.parser import parse_with_heredocs
        # tokenize_with_heredocs sets each `<<` token's heredoc_key — the
        # production path. (Attachment is now key-driven; there is no
        # delimiter-suffix fallback for keyless hand-built tokens.)
        tokens, heredoc_map = tokenize_with_heredocs('cat <<EOF\nhello world\nEOF')
        ast = parse_with_heredocs(tokens, heredoc_map)
        red = self._first_heredoc_redirect(ast)
        assert red.heredoc_content == 'hello world\n'
        assert red.heredoc_quoted is False

    def test_parse_with_heredocs_string_format(self):
        """String-valued map entries (legacy, non-dict) still attach as content."""
        from psh.lexer import tokenize_with_heredocs
        from psh.parser import parse_with_heredocs
        tokens, heredoc_map = tokenize_with_heredocs('cat <<EOF\nhello world\nEOF')
        # Replace the dict entry with a bare string under the same key.
        key = next(iter(heredoc_map))
        string_map = {key: 'hello world\n'}
        ast = parse_with_heredocs(tokens, string_map)
        red = self._first_heredoc_redirect(ast)
        assert red.heredoc_content == 'hello world\n'

    def test_missing_map_entry_fails_loudly(self):
        """A heredoc redirect whose key is absent from the map is a hard error.

        (F9: no silent None / delimiter-suffix guessing — attachment is
        key-driven and a missing collected body raises during the parse.)
        """
        from psh.lexer import tokenize_with_heredocs
        from psh.parser import parse_with_heredocs
        tokens, _ = tokenize_with_heredocs('cat <<EOF\nhello\nEOF')
        with pytest.raises(ParseError):
            parse_with_heredocs(tokens, {})  # key present on token, absent from map


# ===========================================================================
# Codex Review Finding 4: ParserConfig.clone() config mutation
# ===========================================================================

class TestParserConfigCloneNoMutation:
    """clone() returns an independent copy and never mutates the original.

    (Formerly guarded create_configured_parser(), a test-only helper removed
    with the parser-config façade; clone() — now a dataclasses.replace wrapper
    over an empty config — is the surviving API.)
    """

    def test_clone_returns_independent_instance(self):
        """clone() returns a new object, never the same instance."""
        from psh.parser import ParserConfig

        parent = ParserConfig()
        child = parent.clone()

        assert child == parent
        assert child is not parent


# ===========================================================================
# Appraisal Finding 3: error collection removed — a syntax error never yields
# an executable AST (the old collect_errors mode returned a completed
# IfConditional for `if true; then echo x`, then let it execute).
# ===========================================================================

class TestSyntaxErrorNeverExecutes:
    """A parse error must raise, never produce a runnable Program."""

    def test_incomplete_if_raises_not_returns_program(self):
        """`if true; then echo x` (no fi) raises instead of a partial AST."""
        with pytest.raises(ParseError):
            parse("if true; then echo x")

    def test_incomplete_if_executes_nothing_in_command_mode(self):
        """-c: exit 2 and the body command must NOT run."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c', 'if true; then echo RAN'],
            capture_output=True, text=True, timeout=30)
        assert result.returncode == 2
        assert 'RAN' not in result.stdout

    def test_incomplete_if_executes_nothing_in_validate_mode(self):
        """--validate: exit 2 and nothing runs."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '--validate', '-c', 'if true; then echo RAN'],
            capture_output=True, text=True, timeout=30)
        assert result.returncode == 2
        assert 'RAN' not in result.stdout


# ===========================================================================
# Codex Review Finding 6: can_parse() EOF false negatives
# ===========================================================================

class TestCanParseEof:
    """Tests that can_parse() handles trailing EOF tokens."""

    def test_can_parse_with_eof(self):
        """can_parse() should return True for valid input with trailing EOF."""
        from psh.parser.combinators.parser import ParserCombinatorShellParser
        tokens = tokenize('echo hello')
        parser = ParserCombinatorShellParser()
        assert parser.can_parse(tokens) is True
