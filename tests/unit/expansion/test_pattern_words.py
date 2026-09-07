"""The ONE pattern-word owner: ``expansion/pattern_words.expand_pattern_word``.

Closes C042 (Improvement Program 2026-09, Wave 1 slot 1.11): a ``case``
pattern did not tilde-expand, so bash matched a branch psh silently skipped::

    env HOME=/h/me bash -c 'case $HOME in ~) echo tilde;; *) echo other;; esac'
    # bash 5.3.15: tilde     psh <= v0.786.0: other

These are UNIT pins on the owner itself — they call ``expand_pattern_word``
with a real parsed pattern Word and read the pattern STRING it produces, so a
regression names the rule that broke rather than only the branch that moved.
The observable behaviour (which branch runs, which substring is removed) is
pinned in ``tests/conformance/bash/test_pattern_word_tilde_conformance.py``
and the ``pattern-word-tilde-*`` golden rows.

Every tilde expectation here was probed against bash 5.3.15 on 2026-09-07
(empirical, 5.3.15 — no CHANGES item: the behaviour is long-standing, it was
psh that lacked it).
"""

import re

import pytest

from psh.ast_nodes import CaseConditional, Program
from psh.expansion.pattern_words import expand_pattern_word
from psh.lexer import tokenize
from psh.parser import parse

HOME = "/h/me"


def _pattern_words(source_pattern: str):
    """The Word list of ``case x in <source_pattern>) :;; esac``."""
    ast = parse(list(tokenize(f"case x in {source_pattern}) :;; esac")))
    assert isinstance(ast, Program)
    case_stmt = ast.statements[0].pipelines[0].commands[0]
    assert isinstance(case_stmt, CaseConditional)
    return [p.word for p in case_stmt.items[0].patterns]


@pytest.fixture()
def pat(captured_shell):
    """Expand a source pattern the way ``case`` does, with HOME pinned.

    HOME is set on the shell rather than in the script (D14: a script that
    assigns HOME before expanding ``~`` measures the assignment, not the
    tilde rule).
    """
    captured_shell.state.set_variable("HOME", HOME)
    manager = captured_shell.expansion_manager

    def expand(source_pattern: str, *, index: int = 0) -> str:
        return expand_pattern_word(
            _pattern_words(source_pattern)[index],
            manager=manager,
            escape=manager.variable_expander.glob_escape,
            procsub_literal=True,
        )

    return expand


class TestLeadingTildeForms:
    """The word-leading tilde prefix, bounded at the first ``/`` or ``:``."""

    def test_bare_tilde_becomes_home(self, pat):
        assert pat("~") == HOME

    def test_tilde_slash_path(self, pat):
        assert pat("~/x") == f"{HOME}/x"

    def test_tilde_colon_rest_is_verbatim(self, pat):
        # The prefix ends at ':'; the rest is pasted on unexpanded.
        assert pat("~:x") == f"{HOME}:x"

    def test_tilde_keeps_following_glob_live(self, pat):
        assert pat("~/a*") == f"{HOME}/a*"

    def test_tilde_plus_is_pwd(self, pat, captured_shell):
        captured_shell.state.set_variable("PWD", "/somewhere")
        assert pat("~+") == "/somewhere"

    def test_tilde_minus_is_oldpwd(self, pat, captured_shell):
        captured_shell.state.set_variable("OLDPWD", "/previous")
        assert pat("~-") == "/previous"

    def test_unknown_user_stays_literal(self, pat):
        assert pat("~nosuchuser-zz") == "~nosuchuser-zz"

    def test_every_pattern_of_an_alternation_expands(self, pat):
        words = _pattern_words("foo|~|~/x")
        assert len(words) == 3
        assert pat("foo|~|~/x", index=1) == HOME
        assert pat("foo|~|~/x", index=2) == f"{HOME}/x"


class TestQuotingSuppressesTilde:
    """Quoted or escaped tilde text is a literal pattern character."""

    @pytest.mark.parametrize("source", ["'~'", '"~"'])
    def test_quoted_tilde_is_literal(self, pat, source):
        assert pat(source) == "~"

    def test_backslash_escaped_tilde_is_literal(self, pat):
        # The escape survives into the pattern string; the matching engine
        # (expansion/pattern.match_shell_pattern) honours it, so `case '~' in
        # \\~)` matches in both shells.
        assert pat("\\~") == "\\~"

    def test_tilde_word_running_into_a_quoted_part_stays_literal(self, pat):
        # bash: the tilde WORD must be wholly unquoted literal, and `~'*'`
        # has no '/' bound, so nothing expands (the quoted '*' is escaped).
        assert pat("~'*'") == r"~\*"

    def test_slash_bounds_the_tilde_word_before_a_quoted_part(self, pat):
        # A '/' closes the tilde word inside the literal, so the following
        # quoted part is irrelevant to the tilde decision.
        assert pat("~/'*'") == rf"{HOME}/\*"

    def test_tilde_before_an_expansion_stays_literal(self, pat, captured_shell):
        captured_shell.state.set_variable("u", "x")
        assert pat("~$u") == "~x"


class TestTildePosition:
    """Only word-leading and assignment-value positions expand."""

    def test_mid_word_tilde_is_literal(self, pat):
        assert pat("a~") == "a~"

    def test_after_assignment_equals(self, pat):
        assert pat("x=~") == f"x={HOME}"

    def test_after_assignment_equals_with_path(self, pat):
        assert pat("x=~/y") == f"x={HOME}/y"

    def test_after_each_colon_in_an_assignment_value(self, pat):
        assert pat("x=a:~:b") == f"x=a:{HOME}:b"

    def test_append_assignment_shape(self, pat):
        assert pat("x+=~") == f"x+={HOME}"

    def test_colon_without_an_assignment_does_not_trigger(self, pat):
        # No '=' in the word, so ':' is an ordinary character.
        assert pat("x:~") == "x:~"

    def test_invalid_identifier_is_not_assignment_shaped(self, pat):
        assert pat("1x=~") == "1x=~"

    def test_bare_equals_is_not_assignment_shaped(self, pat):
        assert pat("=~") == "=~"

    def test_leading_tilde_expands_but_later_colon_does_not(self, pat):
        # Leading '~' expands; the second is not in an assignment value.
        assert pat("~:~") == f"{HOME}:~"


class TestExpansionParts:
    """Parameter/command/arithmetic parts, and the quoting rule on them."""

    def test_unquoted_expansion_keeps_glob_power(self, pat, captured_shell):
        captured_shell.state.set_variable("p", "a*")
        assert pat("$p") == "a*"

    def test_quoted_expansion_matches_literally(self, pat, captured_shell):
        captured_shell.state.set_variable("p", "a*")
        assert pat('"$p"') == r"a\*"

    def test_arithmetic_part(self, pat):
        assert pat("$((1+1))") == "2"

    def test_tilde_then_expansion(self, pat, captured_shell):
        captured_shell.state.set_variable("u", "x")
        assert pat("~/$u") == f"{HOME}/x"


class TestEscapeHookIsTheOnlyLiteralRule:
    """``escape`` is what makes quoted text literal — swap it, and the same
    walker produces a regex source (the ``[[ =~ ]]`` consumer)."""

    def test_regex_escape_produces_a_regex_source(self, captured_shell):
        captured_shell.state.set_variable("HOME", HOME)
        manager = captured_shell.expansion_manager
        word = _pattern_words("~/'a.c'")[0]
        assert expand_pattern_word(
            word, manager=manager, escape=re.escape) == f"{HOME}/" + re.escape("a.c")


class TestOperandSiblingAgrees:
    """The raw-operand sibling (``${var#pat}``) answers the same tilde forms.

    ``expansion/operands._expand_pattern_operand`` takes a pattern STRING
    (the parser builds no Word for a ``${var#pat}`` operand), so it cannot
    consume the owner. It must still agree on the tilde rule, which both
    reach through ``TildeExpander.prefix_end``/``expand``.
    """

    @pytest.mark.parametrize("source,expected", [
        ("~", HOME),
        ("~/x", f"{HOME}/x"),
        ("~:x", f"{HOME}:x"),
        ("a~", "a~"),
        ("x:~", "x:~"),
        ("~nosuchuser-zz", "~nosuchuser-zz"),
    ])
    def test_same_answer_as_the_word_owner(self, pat, captured_shell,
                                           source, expected):
        assert pat(source) == expected
        operand = captured_shell.expansion_manager.variable_expander
        assert operand._expand_pattern_operand(source) == expected

    def test_assignment_value_tilde_is_a_word_only_rule(self, pat,
                                                        captured_shell):
        # bash 5.3.15 probed both ways: `case "x=$HOME" in x=~)` matches,
        # but `v='x=/h/me/y'; ${v#x=~}` does NOT strip — the ${…} operand
        # gets the leading-tilde rule only. The two sites legitimately differ
        # here, so the agreement suite above excludes this shape.
        assert pat("x=~") == f"x={HOME}"
        operand = captured_shell.expansion_manager.variable_expander
        assert operand._expand_pattern_operand("x=~") == "x=~"
