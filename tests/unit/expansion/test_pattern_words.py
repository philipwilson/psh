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


#: Homes whose VALUE carries a pattern metacharacter. Round-1 B1 shipped
#: because every pin used a metacharacter-free home, so no pin could see
#: whether the tilde replacement was escaped. bash makes a tilde replacement
#: LITERAL in a pattern word; these are the values that prove it.
METACHAR_HOMES = ["/a*b", "/a?b", "/a[b]", "/a.b", "/a(b", "/a)b",
                  "/a]b", "/a\\b", "/a b"]


@pytest.fixture()
def pat(captured_shell):
    """Expand a source pattern the way ``case`` does, with HOME pinned.

    HOME is set on the shell rather than in the script (D14: a script that
    assigns HOME before expanding ``~`` measures the assignment, not the
    tilde rule). Pass ``home=`` to vary the VALUE — a corpus that never
    varies it cannot see whether the replacement is escaped (round-1 B1).
    """
    captured_shell.state.set_variable("HOME", HOME)
    manager = captured_shell.expansion_manager

    def expand(source_pattern: str, *, index: int = 0, home=None,
               escape=None) -> str:
        if home is not None:
            captured_shell.state.set_variable("HOME", home)
        return expand_pattern_word(
            _pattern_words(source_pattern)[index],
            manager=manager,
            escape=escape or manager.variable_expander.glob_escape,
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

    @pytest.mark.parametrize("home", METACHAR_HOMES)
    def test_regex_consumer_escapes_the_tilde_replacement(self, pat, home):
        """The ``=~`` consumer escapes the replacement with ``re.escape``.

        Round-1 B2: the raw replacement reached ``re.compile`` as regex
        SOURCE, so ``HOME='/a[b'; [[ '/a[b' =~ ~ ]]`` raised
        ``invalid regex`` (rc 2) where bash matches (rc 0). One hook, per
        consumer — never an ad-hoc escape at the call site.
        """
        assert pat("~", home=home, escape=re.escape) == re.escape(home)
        # And it is a VALID regex that matches the home literally.
        assert re.fullmatch(pat("~", home=home, escape=re.escape), home)


class TestOperandSiblingAgrees:
    """The raw-operand sibling (``${var#pat}``) answers the same tilde forms.

    ``expansion/operands._expand_pattern_operand`` takes a pattern STRING
    (the parser builds no Word for a ``${var#pat}`` operand), so it cannot
    consume the owner. It must still agree on the tilde rule, which both
    reach through ``TildeExpander.prefix_end``/``expand_split`` — INCLUDING
    the escaping of the replacement, which is where round 1 diverged: the
    sibling glob-escaped its tilde prefix (``operands.py``'s
    ``_tilde_prefix`` call site) and the owner did not, so a
    metacharacter-bearing HOME became a live pattern in ``case`` but not in
    ``${v#~}``. The metacharacter rows below are the cells that discriminate.
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

    @pytest.mark.parametrize("home", METACHAR_HOMES)
    @pytest.mark.parametrize("source", ["~", "~/x", "~:x"])
    def test_metachar_home_is_escaped_by_both(self, pat, captured_shell,
                                              home, source):
        """The discriminating cell: the replacement must be LITERAL in both.

        bash: ``HOME='/a*b'; case '/aXb' in ~)`` does NOT match, while
        ``case '/aXb' in $HOME)`` does — a tilde replacement is quoted in a
        pattern word, a parameter expansion is not.
        """
        captured_shell.state.set_variable("HOME", home)
        glob_escape = (captured_shell.expansion_manager
                       .variable_expander.glob_escape)
        expected = glob_escape(home) + source[1:]

        assert pat(source, home=home) == expected
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


class TestTildeWordBoundaryIsLiteral:
    """The whole tilde WORD is escaped, not just the replacement (V2-B1).

    bash's tilde PREFIX ends at the first ``/`` or ``:`` and decides what
    EXPANDS; the tilde WORD — what bash makes LITERAL in a pattern — ends at the
    first ``/``, **except in an assignment-shaped word, where ``:`` ends it too**
    and the remainder stays LIVE (``TestAssignmentColonException`` holds that
    half). ``TildeExpander.word_end`` is the second boundary. Probed against
    bash 5.3.15 with ``HOME=/h/me``::

        case '/h/me:XX'   in ~:*)   esac   # no match, the * is INSIDE
        case '/h/me:*/YY' in ~:*/*) esac   # MATCHES, the 2nd * is OUTSIDE
        case 'x=/h/me:XX' in x=~:*) esac   # MATCHES, assignment-shaped: the ':'
                                           # ended the word, so the * is LIVE

    Note that ``o`` alone proves nothing — a shell that never expanded the
    tilde prints ``o`` as well — so the separation needs four subjects per
    pattern; see ``test_four_subject_separation``.

    Round 2 escaped only the replacement, so `~:*` kept a live `*` and psh
    answered `M` where bash and psh at base `b6ec6f95` answer `o`.
    """

    def test_the_two_boundaries_differ(self):
        """`prefix_end` and `word_end` are different functions, and the
        discriminating input is a `:`-bounded tilde word.

        The PREFIX (what expands) stops at the `:`; the WORD (what becomes
        literal) runs past it to the `/`. If these two ever collapse into one
        call, this row says so.
        """
        from psh.expansion.tilde import TildeExpander
        assert TildeExpander.prefix_end("~:*/y") == 1     # stops at the ':'
        assert TildeExpander.word_end("~:*/y") == 3       # stops at the '/'
        # With no ':' the two agree, which is why the bug hid for a round.
        assert TildeExpander.prefix_end("~/a*") == 1
        assert TildeExpander.word_end("~/a*") == 1
        # With neither, both run to the end.
        assert TildeExpander.prefix_end("~abc") == 4
        assert TildeExpander.word_end("~abc") == 4

    def test_colon_remainder_is_escaped(self, pat):
        assert pat("~:*") == r"/h/me:\*"

    def test_colon_remainder_bracket_is_escaped(self, pat):
        assert pat("~:[a]") == r"/h/me:\[a\]"

    def test_slash_bounds_the_literal_zone(self, pat):
        # Past the tilde word's '/' the source word's glob stays live.
        assert pat("~:*/*") == r"/h/me:\*/*"

    def test_plain_slash_tail_stays_live(self, pat):
        assert pat("~/a*") == "/h/me/a*"

    @pytest.mark.parametrize("home", METACHAR_HOMES)
    def test_metachar_home_and_remainder_both_escaped(self, pat,
                                                      captured_shell, home):
        captured_shell.state.set_variable("HOME", home)
        glob_escape = (captured_shell.expansion_manager
                       .variable_expander.glob_escape)
        assert pat("~:*", home=home) == glob_escape(home + ":*")

    @pytest.mark.parametrize("pattern,lit", [("~:*", "*"), ("~:?", "?"),
                                             ("~:[a]", "[a]")])
    def test_four_subject_separation(self, pat, pattern, lit):
        """Four subjects, because ``o`` alone proves nothing.

        A shell that never expanded the tilde ALSO answers ``o`` to
        ``case '/h/me:XX' in ~:*)``. Only the full row separates "expanded,
        then the whole word made literal" from "never expanded" and from
        "expanded but the metacharacter left live". bash 5.3.15 gives
        M / o / o / o for every pattern here, and the pattern STRING the owner
        produces is what makes that row come out.
        """
        from psh.expansion.pattern import match_shell_pattern
        produced = pat(pattern)
        matches = lambda subj: match_shell_pattern(subj, produced)
        assert matches(f"{HOME}:{lit}")       # 1: expanded, and literal
        assert not matches(f"{HOME}:XX")      # 2: not live
        assert not matches(f"~:{lit}")        # 3: the ~ really did expand
        assert not matches("~:XX")            # 4: and did not stay literal

    def test_regex_consumer_escapes_the_whole_word(self, pat):
        assert pat("~:.", escape=re.escape) == re.escape("/h/me:.")

    def test_multipart_extent_is_escaped_whole(self, pat, captured_shell):
        # `~:$u` is the colon extent spilling into an expansion part: the
        # collapse takes the expansion VERBATIM (bash's tilde_find_word
        # quirk) and the whole tilde word is then literal.
        captured_shell.state.set_variable("u", "Z")
        # `$` is not a GLOB metacharacter, so glob_escape leaves it alone;
        # the `*`s on both sides of it are escaped because both sit inside
        # the tilde word.
        assert pat("~:$u*", home="/a*b") == r"/a\*b:$u\*"

    @pytest.mark.parametrize("home", ["/a*b", "/a[b]", "/a?b"])
    def test_multipart_extent_metachar_home(self, pat, captured_shell, home):
        captured_shell.state.set_variable("u", "Z")
        glob_escape = (captured_shell.expansion_manager
                       .variable_expander.glob_escape)
        assert pat("~:$u", home=home) == glob_escape(home + ":$u")


class TestAssignmentColonException:
    """In an ASSIGNMENT-shaped word bash's tilde word ends at ``:`` too.

    This is the exception to the rule the round is named for, and it is the
    half that nothing held before round 4: a maintainer who "simplifies" the
    two sites onto the unqualified rule (the verifier's M5) makes psh diverge
    from bash on ``case 'x=/h/me:XX' in x=~:*)``. bash 5.3.15, ``HOME=/h/me``::

        case 'x=/h/me:XX'   in x=~:*)   esac   # M -- assignment: ':' ends the
        case 'a=b:/h/me:XX' in a=b:~:*) esac   # M    word, remainder is LIVE
        case 'x+=/h/me:XX'  in x+=~:*)  esac   # M
        case '/h/me:XX'     in ~:*)     esac   # o -- control, not assignment

    psh gets it right by construction:
    ``word_expander._expand_assignment_value_tildes`` splits the value on ``:``
    before calling ``expand_escaped``, so that path only ever sees a colon-free
    segment and the escape cannot reach past the ``:``.
    """

    @pytest.mark.parametrize("prefix", ["x=", "x+=", "a=b:"])
    def test_remainder_after_the_colon_stays_live(self, pat, prefix):
        # The '*' is NOT escaped: it is past the assignment tilde word's ':'.
        assert pat(f"{prefix}~:*") == f"{prefix}/h/me:*"

    def test_non_assignment_control_escapes_the_remainder(self, pat):
        # The same shape without the assignment prefix: the '*' IS escaped.
        assert pat("~:*") == r"/h/me:\*"

    @pytest.mark.parametrize("home", METACHAR_HOMES)
    def test_replacement_still_escaped_in_an_assignment(self, pat,
                                                        captured_shell, home):
        """The exception widens the LIVE zone; it does not stop escaping the
        replacement itself."""
        captured_shell.state.set_variable("HOME", home)
        glob_escape = (captured_shell.expansion_manager
                       .variable_expander.glob_escape)
        assert pat("x=~:*", home=home) == "x=" + glob_escape(home) + ":*"

    def test_regex_consumer_gets_the_exception_too(self, pat):
        assert pat("x=~:.", escape=re.escape) == "x=" + re.escape("/h/me") + ":."


class TestAssignmentSegmentEscape:
    """The assignment colon-segment site escapes its replacement too.

    Round 2 left this site holding on a single golden row; these are its
    unit pins. Only the REPLACEMENT and the rest of its tilde word are
    escaped — the ``NAME=`` / ``NAME+=`` head stays raw, which is the
    over-escaping failure a cruder fix produces.
    """

    @pytest.mark.parametrize("home", METACHAR_HOMES)
    def test_value_tilde_after_equals(self, pat, captured_shell, home):
        captured_shell.state.set_variable("HOME", home)
        glob_escape = (captured_shell.expansion_manager
                       .variable_expander.glob_escape)
        assert pat("x=~", home=home) == "x=" + glob_escape(home)

    @pytest.mark.parametrize("home", METACHAR_HOMES)
    def test_value_tilde_between_colons(self, pat, captured_shell, home):
        captured_shell.state.set_variable("HOME", home)
        glob_escape = (captured_shell.expansion_manager
                       .variable_expander.glob_escape)
        assert pat("x=a:~:b", home=home) == "x=a:" + glob_escape(home) + ":b"

    @pytest.mark.parametrize("home", METACHAR_HOMES)
    def test_append_assignment_head_stays_raw(self, pat, captured_shell, home):
        captured_shell.state.set_variable("HOME", home)
        glob_escape = (captured_shell.expansion_manager
                       .variable_expander.glob_escape)
        # The `x+=` head is NOT escaped: a crude "escape the whole prefix"
        # fix produces `x\+=…` and reddens here.
        assert pat("x+=~", home=home) == "x+=" + glob_escape(home)

    def test_slash_tail_after_a_value_tilde_stays_live(self, pat):
        assert pat("x=~/a*") == "x=/h/me/a*"

    @pytest.mark.parametrize("home", METACHAR_HOMES)
    def test_regex_consumer_value_tilde(self, pat, captured_shell, home):
        captured_shell.state.set_variable("HOME", home)
        assert pat("x=a:~:b", home=home,
                   escape=re.escape) == "x=a:" + re.escape(home) + ":b"
