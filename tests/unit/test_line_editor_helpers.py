"""Tests for psh.interactive.line_editor_helpers.convert_multiline_to_single.

Every expected string below is pinned to what interactive bash 5.2 records
in its history for the same multi-line input (probed via ``bash --norc -i``
+ ``fc -ln``; see the reappraisal #15 K2 truth table). The joined form must
also REPARSE to the same program — the old keyword-whitelist heuristic
recorded parse errors for ``until``/``select``/``case``/``f()\\n{``.
"""

import pytest

from psh.interactive.line_editor_helpers import convert_multiline_to_single as conv


class TestControlStructures:
    def test_if_then_fi(self):
        assert conv("if true\nthen\necho hi\nfi") == "if true; then echo hi; fi"

    def test_if_then_same_line(self):
        assert conv("if true; then\necho hi\nfi") == "if true; then echo hi; fi"

    def test_if_elif_else(self):
        assert conv("if false\nthen\necho a\nelif true\nthen\necho b\nelse\necho c\nfi") == \
            "if false; then echo a; elif true; then echo b; else echo c; fi"

    def test_nested_if(self):
        assert conv("if true\nthen\nif false\nthen\necho a\nelse\necho b\nfi\nfi") == \
            "if true; then if false; then echo a; else echo b; fi; fi"

    def test_while(self):
        assert conv("while false\ndo\nbreak\ndone") == "while false; do break; done"

    def test_until(self):
        # 'until' was missing from the old keyword whitelist: it recorded
        # 'until false do break done' — a parse error on recall.
        assert conv("until false\ndo\nbreak\ndone") == "until false; do break; done"

    def test_select(self):
        assert conv("select x in a\ndo\nbreak\ndone") == "select x in a; do break; done"

    def test_for(self):
        assert conv("for i in 1 2\ndo\necho $i\ndone") == "for i in 1 2; do echo $i; done"

    def test_for_do_same_line(self):
        assert conv("for i in 1 2; do\necho $i\ndone") == "for i in 1 2; do echo $i; done"

    def test_for_with_in_on_next_line(self):
        # `in` must never be preceded by a semicolon.
        assert conv("for i\nin 1 2\ndo\necho $i\ndone") == "for i in 1 2; do echo $i; done"

    def test_bare_if_then_condition_on_next_line(self):
        assert conv("if\ntrue\nthen\necho hi\nfi") == "if true; then echo hi; fi"

    def test_while_with_redirect_on_done(self):
        assert conv("while read -r l\ndo\necho got:$l\ndone </dev/null") == \
            "while read -r l; do echo got:$l; done </dev/null"

    def test_done_in_pipeline(self):
        assert conv("for i in 1\ndo\necho $i\ndone | tr a-z A-Z") == \
            "for i in 1; do echo $i; done | tr a-z A-Z"


class TestCase:
    def test_pattern_with_dsemi_on_line(self):
        # After `in` and after `;;` bash joins with a SPACE (`; a)` and
        # `;;;` are parse errors, which the old heuristic produced).
        assert conv("case x in\na) echo hi;;\nesac") == "case x in a) echo hi;; esac"

    def test_pattern_body_dsemi_all_split(self):
        assert conv("case x in\na)\necho hi\n;;\nesac") == "case x in a) echo hi; ;; esac"

    def test_last_clause_without_dsemi(self):
        assert conv("case x in\na) echo hi\nesac") == "case x in a) echo hi; esac"

    def test_two_clauses(self):
        assert conv("case b in\na) echo A;;\nb) echo B;;\nesac") == \
            "case b in a) echo A;; b) echo B;; esac"

    def test_fallthrough_semi_amp(self):
        assert conv("case a in\na) echo hi;&\nb) echo bee;;\nesac") == \
            "case a in a) echo hi;& b) echo bee;; esac"

    def test_paren_pattern(self):
        assert conv("case x in\n(a) echo hi;;\nesac") == "case x in (a) echo hi;; esac"

    def test_in_on_next_line(self):
        assert conv("case x\nin\na) echo hi;;\nesac") == "case x in a) echo hi;; esac"


class TestFunctionsAndGroups:
    def test_function_paren_form_brace_on_next_line(self):
        # Old heuristic emitted 'f() { {; echo body; }' — a parse error.
        assert conv("f()\n{\necho body\n}") == "f() { echo body; }"

    def test_function_paren_form_brace_same_line(self):
        assert conv("f() {\necho body\n}") == "f() { echo body; }"

    def test_function_keyword_form(self):
        assert conv("function g\n{\necho gee\n}") == "function g { echo gee; }"

    def test_brace_group(self):
        assert conv("{ echo one\necho two\n}") == "{ echo one; echo two; }"

    def test_subshell(self):
        assert conv("(echo one\necho two)") == "(echo one; echo two)"

    def test_subshell_close_in_if_condition_gets_semicolon(self):
        # A subshell's `)` is not a case pattern's `)`.
        assert conv("if (true)\nthen\necho hi\nfi") == "if (true); then echo hi; fi"


class TestVerbatimNewlines:
    """Newlines that are CONTENT stay verbatim (bash cmdhist)."""

    def test_quoted_newline(self):
        assert conv('echo "line1\nline2"') == 'echo "line1\nline2"'

    def test_mixed_quoted_newline_joins_the_rest(self):
        # Per-newline decisions: the quoted newline stays, the construct
        # newlines are joined (bash does the same).
        assert conv('if true\nthen echo "a\nb"\nfi') == 'if true; then echo "a\nb"; fi'

    def test_heredoc(self):
        assert conv("cat <<EOF\nhello\nEOF") == "cat <<EOF\nhello\nEOF"

    def test_heredoc_inside_if(self):
        # The construct head joins; the heredoc lines keep their newlines
        # (bash additionally puts a cosmetic space before 'fi').
        assert conv("if true\nthen\ncat <<EOF\nhi\nEOF\nfi") == \
            "if true; then\ncat <<EOF\nhi\nEOF\nfi"

    def test_command_substitution_newline(self):
        assert conv("echo $(echo hi\n)") == "echo $(echo hi\n)"

    def test_quoted_command_substitution_newline(self):
        assert conv('echo "$(echo hi\n)"') == 'echo "$(echo hi\n)"'

    def test_arith_expansion_newline(self):
        assert conv("echo $((1 +\n2))") == "echo $((1 +\n2))"

    def test_backtick_newline(self):
        assert conv("echo `echo hi\n`") == "echo `echo hi\n`"

    def test_quoted_backslash_newline_stays(self):
        assert conv("echo 'a \\\nb'") == "echo 'a \\\nb'"
        assert conv('echo "x \\\ny"') == 'echo "x \\\ny"'


class TestContinuationsAndSpacing:
    def test_backslash_continuation_spliced(self):
        # bash removes the backslash-newline pair entirely.
        assert conv("echo one \\\ntwo") == "echo one two"

    def test_operator_continuations_join_with_space(self):
        assert conv("true &&\necho yes") == "true && echo yes"
        assert conv("echo hi |\ncat") == "echo hi | cat"

    def test_blank_lines_dropped(self):
        assert conv("if true\nthen\n\necho hi\nfi") == "if true; then echo hi; fi"

    def test_indentation_preserved_like_bash(self):
        assert conv("if true\n   then\necho hi\nfi") == "if true;    then echo hi; fi"

    def test_array_initializer_elements_join_with_space(self):
        assert conv("a=(1\n2\n3)") == "a=(1 2 3)"

    def test_arith_command_matches_bash_bytes(self):
        # bash 5.2 itself records '((1 +; 2))' (corrupted); we match its
        # bytes rather than invent different behavior.
        assert conv("((1 +\n2))") == "((1 +; 2))"

    def test_plain_single_line(self):
        assert conv("echo hello") == "echo hello"

    def test_empty(self):
        assert conv("") == ""


class TestReparsesToSameProgram:
    """The joined form must reproduce the original program's behavior
    when fed back through the shell (this is what recall executes)."""

    @pytest.mark.parametrize("original", [
        "until false\ndo\nbreak\ndone",
        "select x in a\ndo\nbreak\ndone",
        "case x in\na) echo hi;;\nesac",
        "case x in\na)\necho hi\n;;\nesac",
        "case b in\na) echo A;;\nb) echo B;;\nesac",
        "f()\n{\necho body\n}\nf",
        "function g\n{\necho gee\n}\ng",
        "{ echo one\necho two\n}",
        "(echo one\necho two)",
        "if (true)\nthen\necho hi\nfi",
        'echo "line1\nline2"',
        "cat <<EOF\nhello\nEOF",
        "if true\nthen\ncat <<EOF\nhi\nEOF\nfi",
        "echo one \\\ntwo",
        "echo $(echo hi\n)",
        "a=(1\n2\n3)\necho ${a[1]}",
    ])
    def test_joined_output_matches_original(self, original):
        import subprocess
        import sys

        def run(cmd):
            return subprocess.run(
                [sys.executable, '-m', 'psh', '-c', cmd], input='',
                capture_output=True, text=True, timeout=15)

        # Join the whole text as one logical command, exactly as the
        # history writer sees it.
        joined = conv(original)
        orig, back = run(original), run(joined)
        assert (orig.returncode, orig.stdout) == (back.returncode, back.stdout)
        assert back.stderr == orig.stderr


class TestIdempotence:
    """Recall re-runs the joiner on entries that still contain newlines
    (heredocs, quoted strings) — a second pass must be a no-op."""

    @pytest.mark.parametrize("entry", [
        "if true; then\ncat <<EOF\nhi\nEOF\nfi",
        'echo "line1\nline2"',
        "cat <<EOF\nhello\nEOF",
        "echo $(echo hi\n)",
    ])
    def test_stable_under_second_pass(self, entry):
        assert conv(entry) == entry
