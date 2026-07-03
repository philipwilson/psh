"""nocasematch in ``[[ == ]]`` and ``case`` — POSIX classes (reappraisal #16
ledger item b).

``shopt -s nocasematch`` folds literals, ranges (``[A-Z]``) and sets
(``[abc]``) case-insensitively, but bash leaves the ``[[:upper:]]`` /
``[[:lower:]]`` classes case-SENSITIVE — they keep meaning "an
actually-uppercase / -lowercase character". H6 (v0.585) taught the shared
pattern engine (``shell_pattern_to_regex``) to protect those two classes when
``ignorecase`` is set, but the ``[[`` / ``case`` matcher
(``match_shell_pattern``) applied ``re.IGNORECASE`` WITHOUT forwarding the
flag to the builder, so ``[[ h == [[:upper:]] ]]`` wrongly matched under
nocasematch. Every expected value is pinned to bash 5.2.26 (C locale).
"""


class TestUpperLowerStayCaseSensitive:
    def test_lower_char_not_upper_class(self, captured_shell):
        # THE bug: h is not uppercase, even under nocasematch.
        assert captured_shell.run_command(
            'shopt -s nocasematch; [[ h == [[:upper:]] ]]') == 1
        assert captured_shell.get_stderr() == ""

    def test_upper_char_is_upper_class(self, captured_shell):
        assert captured_shell.run_command(
            'shopt -s nocasematch; [[ H == [[:upper:]] ]]') == 0

    def test_upper_char_not_lower_class(self, captured_shell):
        assert captured_shell.run_command(
            'shopt -s nocasematch; [[ H == [[:lower:]] ]]') == 1

    def test_lower_char_is_lower_class(self, captured_shell):
        assert captured_shell.run_command(
            'shopt -s nocasematch; [[ h == [[:lower:]] ]]') == 0

    def test_case_upper_class_case_sensitive(self, captured_shell):
        captured_shell.run_command(
            'shopt -s nocasematch; case h in [[:upper:]]) echo M;; *) echo N;; esac')
        assert captured_shell.get_stdout() == "N\n"
        assert captured_shell.get_stderr() == ""

    def test_case_lower_class_case_sensitive(self, captured_shell):
        captured_shell.run_command(
            'shopt -s nocasematch; case H in [[:lower:]]) echo M;; *) echo N;; esac')
        assert captured_shell.get_stdout() == "N\n"


class TestFoldingStillWorksUnderNocasematch:
    """Literals, ranges and sets DO fold under nocasematch (unlike the two
    case-classes) — the fix must not over-protect."""

    def test_literal_folds(self, captured_shell):
        assert captured_shell.run_command(
            'shopt -s nocasematch; [[ a == A ]]') == 0

    def test_range_folds(self, captured_shell):
        assert captured_shell.run_command(
            'shopt -s nocasematch; [[ a == [A-Z] ]]') == 0
        assert captured_shell.run_command(
            'shopt -s nocasematch; [[ A == [a-z] ]]') == 0

    def test_set_folds(self, captured_shell):
        assert captured_shell.run_command(
            'shopt -s nocasematch; [[ a == [ABC] ]]') == 0

    def test_glob_star_folds(self, captured_shell):
        assert captured_shell.run_command(
            'shopt -s nocasematch; [[ HELLO == hel* ]]') == 0

    def test_case_range_folds(self, captured_shell):
        captured_shell.run_command(
            'shopt -s nocasematch; case A in [a-z]) echo M;; *) echo N;; esac')
        assert captured_shell.get_stdout() == "M\n"

    def test_composite_class_plus_digit(self, captured_shell):
        # [[:upper:]0-9]: uppercase stays upper-only, digit matches.
        assert captured_shell.run_command(
            'shopt -s nocasematch; [[ h == [[:upper:]0-9] ]]') == 1
        assert captured_shell.run_command(
            'shopt -s nocasematch; [[ H == [[:upper:]0-9] ]]') == 0
        assert captured_shell.run_command(
            'shopt -s nocasematch; [[ 5 == [[:upper:]0-9] ]]') == 0


class TestClassesUnchangedWithoutNocasematch:
    def test_upper_class_default(self, captured_shell):
        assert captured_shell.run_command('[[ h == [[:upper:]] ]]') == 1
        assert captured_shell.run_command('[[ H == [[:upper:]] ]]') == 0

    def test_no_stderr_leak(self, captured_shell):
        captured_shell.run_command('shopt -s nocasematch; [[ h == [[:upper:]] ]]')
        assert captured_shell.get_stderr() == ""
