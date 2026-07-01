"""Bracket-expression edge cases must match quietly, never crash (bash).

Regression for reappraisal #15 H2: valid bash patterns crashed psh with
an uncaught ``re.error`` ("bad character range" / "unterminated character
set" / "incomplete escape") in every pattern-matching construct. Bash 5.2
semantics, all probe-verified:

- an invalid set (reversed range ``[z-a]``) matches NOTHING;
- a NEGATED invalid set (``[!z-a]``) matches any one character;
- backslash escapes are honored inside a set: ``[a\\]b]`` is the
  three-member set a ] b, ``[\\x]`` is the set {x}.
"""


class TestReversedRangeMatchesNothing:
    def test_dstest_no_match(self, captured_shell):
        assert captured_shell.run_command('[[ b == [z-a] ]]') == 1
        assert captured_shell.get_stderr() == ""

    def test_dstest_endpoint_no_match(self, captured_shell):
        # Even the range endpoints do not match.
        assert captured_shell.run_command('[[ z == [z-a] ]]') == 1
        assert captured_shell.get_stderr() == ""

    def test_case_falls_through(self, captured_shell):
        rc = captured_shell.run_command(
            'case b in [z-a]) echo m;; *) echo n;; esac')
        assert rc == 0
        assert captured_shell.get_stdout() == "n\n"
        assert captured_shell.get_stderr() == ""

    def test_prefix_removal_no_strip(self, captured_shell):
        captured_shell.run_command('v=b; echo "${v#[z-a]}"')
        assert captured_shell.get_stdout() == "b\n"
        assert captured_shell.get_stderr() == ""

    def test_patsub_no_replace(self, captured_shell):
        captured_shell.run_command('v=abc; echo "${v/[z-a]/X}"')
        assert captured_shell.get_stdout() == "abc\n"
        assert captured_shell.get_stderr() == ""

    def test_inside_extglob_group(self, captured_shell):
        captured_shell.run_command('shopt -s extglob')
        assert captured_shell.run_command('[[ b == @([z-a]) ]]') == 1
        assert captured_shell.get_stderr() == ""

    def test_inside_extglob_negation(self, captured_shell):
        captured_shell.run_command('shopt -s extglob')
        # !(<matches nothing>) matches everything.
        assert captured_shell.run_command('[[ z == !([z-a]) ]]') == 0
        assert captured_shell.get_stderr() == ""

    def test_nocasematch(self, captured_shell):
        captured_shell.run_command('shopt -s nocasematch')
        assert captured_shell.run_command('[[ B == [z-a] ]]') == 1
        assert captured_shell.get_stderr() == ""


class TestNegatedInvalidSetMatchesAnyChar:
    def test_dstest_matches(self, captured_shell):
        assert captured_shell.run_command('[[ b == [!z-a] ]]') == 0
        assert captured_shell.get_stderr() == ""

    def test_endpoint_matches(self, captured_shell):
        assert captured_shell.run_command('[[ z == [!z-a] ]]') == 0

    def test_with_suffix(self, captured_shell):
        assert captured_shell.run_command('[[ bx == [!z-a]x ]]') == 0
        assert captured_shell.run_command('[[ bx == [z-a]x ]]') == 1

    def test_prefix_removal_strips_one_char(self, captured_shell):
        captured_shell.run_command('v=bx; echo "${v#[!z-a]}"')
        assert captured_shell.get_stdout() == "x\n"

    def test_case_matches(self, captured_shell):
        captured_shell.run_command(
            'case q in [!z-a]) echo m;; *) echo n;; esac')
        assert captured_shell.get_stdout() == "m\n"


class TestEscapedMembersInSet:
    def test_escaped_rbracket_members(self, captured_shell):
        # [a\]b] is the three-member set {a, ], b}.
        assert captured_shell.run_command('[[ a == [a\\]b] ]]') == 0
        assert captured_shell.run_command('[[ "]" == [a\\]b] ]]') == 0
        assert captured_shell.run_command('[[ b == [a\\]b] ]]') == 0
        assert captured_shell.run_command('[[ c == [a\\]b] ]]') == 1
        assert captured_shell.get_stderr() == ""

    def test_escaped_ordinary_char(self, captured_shell):
        # [\x] is the set {x}; Python's re would reject the incomplete \x.
        assert captured_shell.run_command('[[ x == [\\x] ]]') == 0
        assert captured_shell.run_command('[[ y == [\\x] ]]') == 1
        assert captured_shell.get_stderr() == ""

    def test_escaped_dash_is_literal(self, captured_shell):
        # [a\-c] is {a, -, c}, not the range a-c.
        assert captured_shell.run_command('[[ - == [a\\-c] ]]') == 0
        assert captured_shell.run_command('[[ b == [a\\-c] ]]') == 1

    def test_escaped_rbracket_in_case(self, captured_shell):
        captured_shell.run_command(
            'case "]" in [a\\]b]) echo m;; *) echo n;; esac')
        assert captured_shell.get_stdout() == "m\n"

    def test_escaped_rbracket_in_prefix_removal(self, captured_shell):
        captured_shell.run_command('v=]x; echo "${v#[a\\]b]}"')
        assert captured_shell.get_stdout() == "x\n"


class TestOrdinarySetsStillWork:
    def test_normal_range(self, captured_shell):
        assert captured_shell.run_command('[[ 3 == [1-5] ]]') == 0
        assert captured_shell.run_command('[[ 7 == [1-5] ]]') == 1

    def test_posix_class(self, captured_shell):
        assert captured_shell.run_command('[[ q == [[:alpha:]] ]]') == 0
        assert captured_shell.run_command('[[ 7 == [[:alpha:]] ]]') == 1

    def test_leading_rbracket_member(self, captured_shell):
        # []a] is the set {], a}.
        assert captured_shell.run_command('[[ "]" == []a] ]]') == 0
        assert captured_shell.run_command('[[ a == []a] ]]') == 0
        assert captured_shell.run_command('[[ b == []a] ]]') == 1
