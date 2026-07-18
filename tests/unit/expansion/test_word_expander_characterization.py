"""Characterization harness for the word-expansion engine.

This is a SAFETY NET, not a behavior spec. It freezes the EXACT observable
output of the field engine (``WordExpander.expand_to_word(word, policy)``
materialized through ``WordExpander.materialize`` — collapsed to the
historical one-field-is-a-scalar shape by the ``_expand`` helper) across a
large corpus, so an engine refactor can be proven non-regressing.

Each case:
  * parses a real shell fragment so the Word AST is realistic
    (``_word(src, idx)`` parses ``src`` and returns ``cmd.words[idx]``;
    index 0 is the command name, so target words are at index >= 1),
  * sets up shell state (variables / arrays / positional params / IFS /
    options) via real ``run_command`` calls,
  * calls ``expand()`` directly under a named policy,
  * asserts an exact expected value (str OR list — the public contract).

The expected values were frozen from the engine on 2026-06-13 BEFORE the
B5 refactor (parallel-array accumulator → ExpandedSegment IR). If a case
here ever fails after a refactor, the refactor changed behavior.

Axes covered (see the per-section comments):
  unquoted / double / single / ANSI-C words; composite quoted+unquoted;
  $@ / $* / ${a[@]} / ${a[*]} quoted+unquoted, with/without affixes,
  0/1/many elements; IFS splitting under default / ':' / empty / multichar
  with leading/trailing/consecutive separators; globbing (match / no-match
  literal / quoted-suppressed / noglob / escaped \\*); tilde (leading,
  assignment-value after '='/':', escaped); assignment-shaped words under
  all four field policies; empty/unset expansions; backslash escapes;
  process-substitution path splicing.
"""

import os

import pytest

from psh.expansion.word_expansion_types import (
    ARRAY_INIT_ELEMENT,
    ASSOC_INIT_ELEMENT,
    COMMAND_ARGUMENT,
    DECLARATION_ASSIGNMENT,
)
from psh.lexer import tokenize
from psh.parser import Parser, ParserConfig

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _word(src: str, idx: int = 1):
    """Parse ``src`` and return cmd.words[idx] (0 = command name)."""
    toks = tokenize(src)
    ast = Parser(toks, config=ParserConfig()).parse()
    cmd = ast.statements[0].pipelines[0].commands[0]
    return cmd.words[idx]


def _expand(shell, src, policy, idx=1):
    """Materialize a word to its observable argv shape.

    The engine now returns an ``ExpandedWord`` (``expand_to_word``) that
    ``materialize`` turns into ``List[str]`` fields; this helper collapses that
    to the historical observable shape these characterization cases pin — one
    field is the scalar string, zero or many fields is a list — so the
    behavioral assertions stay meaningful across the field-IR refactor.
    """
    we = shell.expansion_manager.word_expander
    fields = we.materialize(we.expand_to_word(_word(src, idx), policy), policy)
    return fields[0] if len(fields) == 1 else fields


# --------------------------------------------------------------------------
# 1. Plain literals and quote types (no expansion)
# --------------------------------------------------------------------------

class TestLiteralsAndQuoteTypes:
    def test_unquoted_literal(self, captured_shell):
        assert _expand(captured_shell, "echo hello", COMMAND_ARGUMENT) == "hello"

    def test_double_quoted_literal(self, captured_shell):
        assert _expand(captured_shell, 'echo "hello world"',
                       COMMAND_ARGUMENT) == "hello world"

    def test_single_quoted_literal(self, captured_shell):
        assert _expand(captured_shell, "echo 'hello $x world'",
                       COMMAND_ARGUMENT) == "hello $x world"

    def test_ansi_c_literal(self, captured_shell):
        assert _expand(captured_shell, r"echo $'a\tb\nc'",
                       COMMAND_ARGUMENT) == "a\tb\nc"

    def test_single_quoted_keeps_glob(self, captured_shell):
        assert _expand(captured_shell, "echo '*.nomatch'",
                       COMMAND_ARGUMENT) == "*.nomatch"

    def test_empty_double_quote(self, captured_shell):
        assert _expand(captured_shell, 'echo ""', COMMAND_ARGUMENT) == ""

    def test_empty_single_quote(self, captured_shell):
        assert _expand(captured_shell, "echo ''", COMMAND_ARGUMENT) == ""


# --------------------------------------------------------------------------
# 2. Simple variable expansion (quoted/unquoted/empty/unset)
# --------------------------------------------------------------------------

class TestSimpleVariables:
    def test_unquoted_scalar(self, captured_shell):
        captured_shell.run_command("x=value")
        assert _expand(captured_shell, "echo $x", COMMAND_ARGUMENT) == "value"

    def test_double_quoted_scalar(self, captured_shell):
        captured_shell.run_command("x=value")
        assert _expand(captured_shell, 'echo "$x"',
                       COMMAND_ARGUMENT) == "value"

    def test_braced_scalar(self, captured_shell):
        captured_shell.run_command("x=value")
        assert _expand(captured_shell, "echo ${x}", COMMAND_ARGUMENT) == "value"

    def test_unquoted_unset_is_zero_fields(self, captured_shell):
        captured_shell.run_command("unset novar")
        assert _expand(captured_shell, "echo $novar", COMMAND_ARGUMENT) == []

    def test_quoted_unset_is_empty_string(self, captured_shell):
        captured_shell.run_command("unset novar")
        assert _expand(captured_shell, 'echo "$novar"',
                       COMMAND_ARGUMENT) == ""

    def test_unquoted_empty_value_is_zero_fields(self, captured_shell):
        captured_shell.run_command("e=''")
        assert _expand(captured_shell, "echo $e", COMMAND_ARGUMENT) == []

    def test_quoted_empty_value_is_empty_string(self, captured_shell):
        captured_shell.run_command("e=''")
        assert _expand(captured_shell, 'echo "$e"', COMMAND_ARGUMENT) == ""

    def test_default_operator_unset(self, captured_shell):
        captured_shell.run_command("unset novar")
        assert _expand(captured_shell, "echo ${novar:-fallback}",
                       COMMAND_ARGUMENT) == "fallback"

    def test_length_operator(self, captured_shell):
        captured_shell.run_command("x=abcde")
        assert _expand(captured_shell, "echo ${#x}", COMMAND_ARGUMENT) == "5"


# --------------------------------------------------------------------------
# 3. Composite words (quoted + unquoted + literal joining)
# --------------------------------------------------------------------------

class TestCompositeWords:
    def test_literal_quoted_literal(self, captured_shell):
        captured_shell.run_command("x=MID")
        assert _expand(captured_shell, 'echo a"$x"b',
                       COMMAND_ARGUMENT) == "aMIDb"

    def test_literal_unquoted_literal(self, captured_shell):
        captured_shell.run_command("x=MID")
        assert _expand(captured_shell, "echo a${x}b",
                       COMMAND_ARGUMENT) == "aMIDb"

    def test_composite_with_split_value_joins_edges(self, captured_shell):
        # a"$x"b where x splits -> quoted text joins onto adjacent fields
        captured_shell.run_command("x='1 2'")
        # x is quoted here, so no split: literal join
        assert _expand(captured_shell, 'echo a"$x"b',
                       COMMAND_ARGUMENT) == "a1 2b"

    def test_composite_unquoted_split_joins_edges(self, captured_shell):
        # a$x b where x='1 2' (unquoted) -> a1, 2 then 'b' separate word
        captured_shell.run_command("x='1 2'")
        assert _expand(captured_shell, "echo a${x}",
                       COMMAND_ARGUMENT) == ["a1", "2"]

    def test_composite_edge_join_both_sides(self, captured_shell):
        captured_shell.run_command("x='1 2'")
        assert _expand(captured_shell, "echo pre${x}post",
                       COMMAND_ARGUMENT) == ["pre1", "2post"]

    def test_two_unquoted_vars_adjacent(self, captured_shell):
        captured_shell.run_command("x='a b'; y='c d'")
        assert _expand(captured_shell, "echo $x$y",
                       COMMAND_ARGUMENT) == ["a", "bc", "d"]


# --------------------------------------------------------------------------
# 4. $@ / $* (positional params), quoted/unquoted, affixes, 0/1/many
# --------------------------------------------------------------------------

class TestAtStar:
    def test_quoted_at_many(self, captured_shell):
        captured_shell.run_command('set -- "a b" c')
        assert _expand(captured_shell, 'echo "$@"',
                       COMMAND_ARGUMENT) == ["a b", "c"]

    def test_quoted_at_one(self, captured_shell):
        captured_shell.run_command('set -- solo')
        assert _expand(captured_shell, 'echo "$@"',
                       COMMAND_ARGUMENT) == "solo"

    def test_quoted_at_zero(self, captured_shell):
        captured_shell.run_command('set --')
        assert _expand(captured_shell, 'echo "$@"', COMMAND_ARGUMENT) == []

    def test_unquoted_at_many(self, captured_shell):
        captured_shell.run_command('set -- "a b" c')
        assert _expand(captured_shell, "echo $@",
                       COMMAND_ARGUMENT) == ["a", "b", "c"]

    def test_unquoted_at_zero(self, captured_shell):
        captured_shell.run_command('set --')
        assert _expand(captured_shell, "echo $@", COMMAND_ARGUMENT) == []

    def test_quoted_at_with_prefix(self, captured_shell):
        captured_shell.run_command('set -- a b c')
        assert _expand(captured_shell, 'echo "pre$@"',
                       COMMAND_ARGUMENT) == ["prea", "b", "c"]

    def test_quoted_at_with_suffix(self, captured_shell):
        captured_shell.run_command('set -- a b c')
        assert _expand(captured_shell, 'echo "$@post"',
                       COMMAND_ARGUMENT) == ["a", "b", "cpost"]

    def test_quoted_at_with_both_affixes(self, captured_shell):
        captured_shell.run_command('set -- a b c')
        assert _expand(captured_shell, 'echo "pre$@post"',
                       COMMAND_ARGUMENT) == ["prea", "b", "cpost"]

    def test_unquoted_at_with_affixes_composite(self, captured_shell):
        captured_shell.run_command('set -- a b c')
        assert _expand(captured_shell, "echo pre$@post",
                       COMMAND_ARGUMENT) == ["prea", "b", "cpost"]

    def test_quoted_at_affix_single_param(self, captured_shell):
        captured_shell.run_command('set -- only')
        assert _expand(captured_shell, 'echo "pre$@post"',
                       COMMAND_ARGUMENT) == "preonlypost"

    def test_quoted_at_affix_zero_params(self, captured_shell):
        captured_shell.run_command('set --')
        # "pre$@post" with no params -> "prepost" (literal joins)
        assert _expand(captured_shell, 'echo "pre$@post"',
                       COMMAND_ARGUMENT) == "prepost"

    def test_quoted_star_many(self, captured_shell):
        captured_shell.run_command('set -- a b c')
        # "$*" joins with first IFS char (space by default) -> one field
        assert _expand(captured_shell, 'echo "$*"',
                       COMMAND_ARGUMENT) == "a b c"

    def test_quoted_star_custom_ifs(self, captured_shell):
        captured_shell.run_command('set -- a b c; IFS=:')
        assert _expand(captured_shell, 'echo "$*"',
                       COMMAND_ARGUMENT) == "a:b:c"

    def test_unquoted_star_splits(self, captured_shell):
        captured_shell.run_command('set -- a b c')
        assert _expand(captured_shell, "echo $*",
                       COMMAND_ARGUMENT) == ["a", "b", "c"]

    def test_double_at_in_one_word(self, captured_shell):
        captured_shell.run_command('set -- 1 2')
        assert _expand(captured_shell, 'echo "a$@b$@c"',
                       COMMAND_ARGUMENT) == ["a1", "2b1", "2c"]


# --------------------------------------------------------------------------
# 5. Arrays ${a[@]} / ${a[*]}, quoted/unquoted, affixes
# --------------------------------------------------------------------------

class TestArrays:
    def test_quoted_array_at(self, captured_shell):
        captured_shell.run_command("a=(p1 'p 2' p3)")
        assert _expand(captured_shell, 'echo "${a[@]}"',
                       COMMAND_ARGUMENT) == ["p1", "p 2", "p3"]

    def test_unquoted_array_at(self, captured_shell):
        captured_shell.run_command("a=(p1 'p 2' p3)")
        assert _expand(captured_shell, "echo ${a[@]}",
                       COMMAND_ARGUMENT) == ["p1", "p", "2", "p3"]

    def test_quoted_array_at_with_suffix(self, captured_shell):
        captured_shell.run_command("a=(p1 p2)")
        assert _expand(captured_shell, 'echo "${a[@]}"post',
                       COMMAND_ARGUMENT) == ["p1", "p2post"]

    def test_quoted_array_star_default_ifs(self, captured_shell):
        captured_shell.run_command("a=(p1 p2 p3)")
        assert _expand(captured_shell, 'echo "${a[*]}"',
                       COMMAND_ARGUMENT) == "p1 p2 p3"

    def test_quoted_array_star_custom_ifs(self, captured_shell):
        captured_shell.run_command("a=(p1 p2 p3); IFS=,")
        assert _expand(captured_shell, 'echo "${a[*]}"',
                       COMMAND_ARGUMENT) == "p1,p2,p3"

    def test_array_single_element(self, captured_shell):
        captured_shell.run_command("a=(solo)")
        assert _expand(captured_shell, "echo ${a[0]}",
                       COMMAND_ARGUMENT) == "solo"

    def test_array_empty(self, captured_shell):
        captured_shell.run_command("a=()")
        assert _expand(captured_shell, 'echo "${a[@]}"',
                       COMMAND_ARGUMENT) == []

    def test_array_index_count(self, captured_shell):
        captured_shell.run_command("a=(x y z)")
        assert _expand(captured_shell, "echo ${#a[@]}",
                       COMMAND_ARGUMENT) == "3"


# --------------------------------------------------------------------------
# 6. IFS word splitting (default / ':' / empty / multichar; edges)
# --------------------------------------------------------------------------

class TestIFSSplitting:
    def test_default_ifs_collapses_runs(self, captured_shell):
        captured_shell.run_command("x='a   b   c'")
        assert _expand(captured_shell, "echo $x",
                       COMMAND_ARGUMENT) == ["a", "b", "c"]

    def test_default_ifs_leading_trailing_ws(self, captured_shell):
        captured_shell.run_command("x='  a b  '")
        assert _expand(captured_shell, "echo $x",
                       COMMAND_ARGUMENT) == ["a", "b"]

    def test_colon_ifs_keeps_empty_fields(self, captured_shell):
        captured_shell.run_command("IFS=:; x='a::b'")
        assert _expand(captured_shell, "echo $x",
                       COMMAND_ARGUMENT) == ["a", "", "b"]

    def test_colon_ifs_leading(self, captured_shell):
        captured_shell.run_command("IFS=:; x=':a:b'")
        assert _expand(captured_shell, "echo $x",
                       COMMAND_ARGUMENT) == ["", "a", "b"]

    def test_colon_ifs_trailing(self, captured_shell):
        captured_shell.run_command("IFS=:; x='a:b:'")
        assert _expand(captured_shell, "echo $x",
                       COMMAND_ARGUMENT) == ["a", "b"]

    def test_empty_ifs_no_split(self, captured_shell):
        captured_shell.run_command("IFS=''; x='a b c'")
        assert _expand(captured_shell, "echo $x",
                       COMMAND_ARGUMENT) == "a b c"

    def test_multichar_ifs(self, captured_shell):
        captured_shell.run_command("IFS=':,'; x='a:b,c'")
        assert _expand(captured_shell, "echo $x",
                       COMMAND_ARGUMENT) == ["a", "b", "c"]

    def test_ifs_whitespace_plus_explicit(self, captured_shell):
        # IFS with space AND ':' -> ws collapses, ':' is explicit delim
        captured_shell.run_command("IFS=' :'; x='a : b'")
        assert _expand(captured_shell, "echo $x",
                       COMMAND_ARGUMENT) == ["a", "b"]

    def test_split_then_composite_edge(self, captured_shell):
        captured_shell.run_command("IFS=:; x='a:b'")
        assert _expand(captured_shell, "echo pre${x}",
                       COMMAND_ARGUMENT) == ["prea", "b"]


# --------------------------------------------------------------------------
# 7. Globbing (match / no-match literal / quoted-suppressed / noglob /
#    escaped \\*)
# --------------------------------------------------------------------------

class TestGlobbing:
    def test_glob_match(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        d = shell.state.variables['PWD']
        for name in ("aa.txt", "bb.txt"):
            open(os.path.join(d, name), "w").close()
        assert _expand(shell, "echo *.txt", COMMAND_ARGUMENT) == \
            ["aa.txt", "bb.txt"]

    def test_glob_no_match_literal(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        assert _expand(shell, "echo zz-no-such-*.txt",
                       COMMAND_ARGUMENT) == "zz-no-such-*.txt"

    def test_glob_quoted_suppressed(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        d = shell.state.variables['PWD']
        open(os.path.join(d, "aa.txt"), "w").close()
        assert _expand(shell, 'echo "*.txt"', COMMAND_ARGUMENT) == "*.txt"

    def test_glob_noglob_option(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        d = shell.state.variables['PWD']
        open(os.path.join(d, "aa.txt"), "w").close()
        shell.run_command("set -f")
        assert _expand(shell, "echo *.txt", COMMAND_ARGUMENT) == "*.txt"

    def test_glob_escaped_star(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        d = shell.state.variables['PWD']
        open(os.path.join(d, "aa.txt"), "w").close()
        assert _expand(shell, r"echo \*.txt", COMMAND_ARGUMENT) == "*.txt"

    def test_glob_from_unquoted_var(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        d = shell.state.variables['PWD']
        open(os.path.join(d, "aa.txt"), "w").close()
        shell.run_command("g='*.txt'")
        # A single glob match collapses to one field (str), not a 1-list.
        assert _expand(shell, "echo $g", COMMAND_ARGUMENT) == "aa.txt"

    def test_glob_from_quoted_var_suppressed(
            self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        d = shell.state.variables['PWD']
        open(os.path.join(d, "aa.txt"), "w").close()
        shell.run_command("g='*.txt'")
        assert _expand(shell, 'echo "$g"', COMMAND_ARGUMENT) == "*.txt"

    def test_glob_question_mark(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        d = shell.state.variables['PWD']
        for name in ("a.c", "b.c"):
            open(os.path.join(d, name), "w").close()
        assert _expand(shell, "echo ?.c", COMMAND_ARGUMENT) == ["a.c", "b.c"]

    def test_glob_bracket(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        d = shell.state.variables['PWD']
        for name in ("a1", "a2"):
            open(os.path.join(d, name), "w").close()
        assert _expand(shell, "echo a[12]", COMMAND_ARGUMENT) == ["a1", "a2"]


# --------------------------------------------------------------------------
# 8. Tilde expansion (leading, assignment-value, escaped)
# --------------------------------------------------------------------------

class TestTilde:
    def test_leading_tilde(self, captured_shell):
        captured_shell.run_command("HOME=/home/me")
        assert _expand(captured_shell, "echo ~/dir",
                       COMMAND_ARGUMENT) == "/home/me/dir"

    def test_bare_tilde(self, captured_shell):
        captured_shell.run_command("HOME=/home/me")
        assert _expand(captured_shell, "echo ~",
                       COMMAND_ARGUMENT) == "/home/me"

    def test_escaped_tilde_literal(self, captured_shell):
        captured_shell.run_command("HOME=/home/me")
        assert _expand(captured_shell, r"echo \~/dir",
                       COMMAND_ARGUMENT) == "~/dir"

    def test_assignment_value_tilde_after_eq(self, captured_shell):
        captured_shell.run_command("HOME=/H")
        assert _expand(captured_shell, "echo P=~/x",
                       COMMAND_ARGUMENT) == "P=/H/x"

    def test_assignment_value_tilde_after_colon(self, captured_shell):
        captured_shell.run_command("HOME=/H")
        assert _expand(captured_shell, "echo P=a:~/x",
                       COMMAND_ARGUMENT) == "P=a:/H/x"

    def test_assignment_value_multiple_tildes(self, captured_shell):
        captured_shell.run_command("HOME=/H")
        assert _expand(captured_shell, "echo P=~:~/y",
                       COMMAND_ARGUMENT) == "P=/H:/H/y"

    def test_tilde_not_first_no_expand(self, captured_shell):
        captured_shell.run_command("HOME=/H")
        assert _expand(captured_shell, "echo x~",
                       COMMAND_ARGUMENT) == "x~"


# --------------------------------------------------------------------------
# 9. Assignment-shaped words under the four field policies
# --------------------------------------------------------------------------

class TestAssignmentPolicies:
    def test_command_arg_splits_assignment_value(self, captured_shell):
        captured_shell.run_command("x='1 2'")
        assert _expand(captured_shell, "echo foo=$x",
                       COMMAND_ARGUMENT) == ["foo=1", "2"]

    def test_declaration_keeps_value_whole(self, captured_shell):
        captured_shell.run_command("x='1 2'")
        assert _expand(captured_shell, "echo foo=$x",
                       DECLARATION_ASSIGNMENT) == "foo=1 2"

    def test_declaration_no_glob(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        d = shell.state.variables['PWD']
        open(os.path.join(d, "aa.txt"), "w").close()
        assert _expand(shell, "echo foo=*.txt",
                       DECLARATION_ASSIGNMENT) == "foo=*.txt"

    def test_array_init_element_splits(self, captured_shell):
        captured_shell.run_command("x='p q'")
        assert _expand(captured_shell, "echo $x",
                       ARRAY_INIT_ELEMENT) == ["p", "q"]

    def test_array_init_no_value_tilde(self, captured_shell):
        captured_shell.run_command("HOME=/H")
        assert _expand(captured_shell, "echo P=~/x",
                       ARRAY_INIT_ELEMENT) == "P=~/x"

    def test_assoc_init_keeps_whole(self, captured_shell):
        captured_shell.run_command("x='k v'")
        assert _expand(captured_shell, "echo $x",
                       ASSOC_INIT_ELEMENT) == "k v"

    def test_assoc_init_no_value_tilde(self, captured_shell):
        captured_shell.run_command("HOME=/H")
        assert _expand(captured_shell, "echo P=~/x",
                       ASSOC_INIT_ELEMENT) == "P=~/x"

    def test_assoc_init_unquoted_at_joins(self, captured_shell):
        captured_shell.run_command('set -- "a b" c')
        assert _expand(captured_shell, "echo $@",
                       ASSOC_INIT_ELEMENT) == "a b c"

    def test_declaration_quoted_at_joins(self, captured_shell):
        captured_shell.run_command('set -- "a b" c')
        assert _expand(captured_shell, 'echo "$@"',
                       DECLARATION_ASSIGNMENT) == "a b c"

    def test_array_init_at_still_fields(self, captured_shell):
        captured_shell.run_command('set -- "a b" c')
        assert _expand(captured_shell, 'echo "$@"',
                       ARRAY_INIT_ELEMENT) == ["a b", "c"]


# --------------------------------------------------------------------------
# 10. Backslash escapes (\\$ \\\\ \\" \\` and unquoted)
# --------------------------------------------------------------------------

class TestEscapes:
    def test_dquote_escaped_dollar(self, captured_shell):
        captured_shell.run_command("x=VAL")
        assert _expand(captured_shell, r'echo "\$x"',
                       COMMAND_ARGUMENT) == "$x"

    def test_dquote_escaped_backslash(self, captured_shell):
        assert _expand(captured_shell, r'echo "a\\b"',
                       COMMAND_ARGUMENT) == r"a\b"

    def test_dquote_escaped_quote(self, captured_shell):
        assert _expand(captured_shell, r'echo "a\"b"',
                       COMMAND_ARGUMENT) == 'a"b'

    def test_dquote_escaped_backtick(self, captured_shell):
        assert _expand(captured_shell, r'echo "a\`b"',
                       COMMAND_ARGUMENT) == "a`b"

    def test_unquoted_escaped_dollar(self, captured_shell):
        captured_shell.run_command("x=VAL")
        assert _expand(captured_shell, r"echo \$x", COMMAND_ARGUMENT) == "$x"

    def test_unquoted_escaped_space(self, captured_shell):
        assert _expand(captured_shell, r"echo a\ b", COMMAND_ARGUMENT) == "a b"

    def test_unquoted_escaped_space_no_split(self, captured_shell):
        # escaped space inside literal does not create a field boundary
        captured_shell.run_command("x=VAL")
        assert _expand(captured_shell, r"echo a\ $x",
                       COMMAND_ARGUMENT) == "a VAL"


# --------------------------------------------------------------------------
# 11. Command substitution and arithmetic (engine just splices/splits)
# --------------------------------------------------------------------------

class TestCommandSubAndArith:
    def test_unquoted_cmdsub_splits(self, captured_shell):
        assert _expand(captured_shell, "echo $(echo a b c)",
                       COMMAND_ARGUMENT) == ["a", "b", "c"]

    def test_quoted_cmdsub_no_split(self, captured_shell):
        assert _expand(captured_shell, 'echo "$(echo a b c)"',
                       COMMAND_ARGUMENT) == "a b c"

    def test_arithmetic(self, captured_shell):
        assert _expand(captured_shell, "echo $((2 + 3))",
                       COMMAND_ARGUMENT) == "5"

    def test_cmdsub_composite(self, captured_shell):
        assert _expand(captured_shell, "echo pre$(echo X)post",
                       COMMAND_ARGUMENT) == "preXpost"


# --------------------------------------------------------------------------
# 12. Process substitution path splicing (path is not split/globbed)
# --------------------------------------------------------------------------

@pytest.mark.serial
class TestProcessSubstitution:
    def test_process_sub_path(self, captured_shell):
        result = _expand(captured_shell, "cat <(echo hi)", COMMAND_ARGUMENT)
        # The path is /dev/fd/N (or a named pipe) — not split, single string.
        assert isinstance(result, str)
        assert result.startswith("/dev/fd/") or "/" in result


# --------------------------------------------------------------------------
# 13. End-to-end smoke via expand_arguments (full public path)
# --------------------------------------------------------------------------

class TestEndToEndArguments:
    def test_mixed_arguments(self, captured_shell):
        captured_shell.run_command("x='1 2'; set -- p q")
        assert captured_shell.run_command(r"""printf '[%s]' a "$x" $x "$@" """) \
            == 0
        assert captured_shell.get_stdout() == "[a][1 2][1][2][p][q]"

    def test_glob_and_literal(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        d = shell.state.variables['PWD']
        for name in ("m1.dat", "m2.dat"):
            open(os.path.join(d, name), "w").close()
        # Expand each argument through the engine and flatten.
        out = []
        for src in ("printf *.dat", "printf lit"):
            r = _expand(shell, src, COMMAND_ARGUMENT)
            out.extend(r if isinstance(r, list) else [r])
        assert out == ["m1.dat", "m2.dat", "lit"]
