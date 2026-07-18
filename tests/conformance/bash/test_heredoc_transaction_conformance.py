"""Conformance: the heredoc transaction (boundary campaign S2).

All rows probed against bash 5.2.26 (the pre-registered S2 battery,
red-on-base at 6148a602; see tmp/boundary-ledgers/S2.md):

1. FIFO body collection (reappraisal #20 H1 / #21 G1): heredoc bodies are
   consumed strictly in source order — an input line equal to a LATER
   pending delimiter is body text of the FIRST open heredoc, never an early
   close. Duplicate delimiters are distinct heredocs (ordinal identity).
2. Delimiter shapes (#20 H3): ``$'…'`` ANSI-C and ``$"…"`` locale quoting
   cook through real quote removal (``$'EOF'`` terminates at ``EOF`` with a
   literal body); a process-substitution-SHAPED word after ``<<`` is a
   literal delimiter (``cat << <(x)`` terminates at the line ``<(x)``,
   body still expands), with bash's no-paren-nesting extent.
3. EOF termination: an unterminated heredoc keeps its gathered body,
   warns ("delimited by end-of-file"), and runs.
4. Formatter round-trip (H3's formatter half): ``eval "$(declare -f f)"``
   of a function whose heredoc has an expansion-shaped or quoted delimiter
   preserves behavior (raw delimiter re-emitted).

Rows are order-independent; two queue rows are additionally exercised in
script-file and stdin input modes (the completeness oracle drives all
three modes through the same head-of-queue policy).
"""

import subprocess
import sys
import tempfile
from pathlib import Path

from conformance_framework import ConformanceTest

_REPO = Path(__file__).resolve().parents[3]

TAB = '\t'


class _HeredocTransactionBase(ConformanceTest):
    """Warning-row helper: identical stdout/rc; stderr equal after the
    shell-name prefix (bash's argv0 path vs "psh") is normalized."""

    @staticmethod
    def _norm_warn(text: str) -> str:
        out = []
        for line in text.splitlines():
            head, sep, rest = line.partition(': ')
            out.append('SH: ' + rest if sep else line)
        return '\n'.join(out)

    def assert_same_with_normalized_stderr(self, command: str):
        psh_result = self.framework.run_in_psh(command)
        bash_result = self.framework.run_in_bash(command)
        assert psh_result.stdout == bash_result.stdout, command
        assert psh_result.exit_code == bash_result.exit_code, command
        assert (self._norm_warn(psh_result.stderr)
                == self._norm_warn(bash_result.stderr)), (
            f"stderr differs for {command!r}:\n"
            f"psh:  {psh_result.stderr!r}\nbash: {bash_result.stderr!r}")

    def assert_same_error_class(self, command: str):
        psh_result = self.framework.run_in_psh(command)
        bash_result = self.framework.run_in_bash(command)
        assert bash_result.exit_code != 0, f"bash accepted: {command}"
        assert psh_result.exit_code != 0, f"psh accepted: {command}"
        assert psh_result.stdout == bash_result.stdout, command


class TestHeredocFifoOrderConformance(_HeredocTransactionBase):
    """Bodies close head-first; later delimiters are plain body text."""

    def test_two_operators_one_command(self):
        # A's body contains B's delimiter; bash feeds cat the LAST heredoc.
        self.assert_identical_behavior(
            "cat <<A <<B\nB\na body\nA\nb body\nB\necho after")

    def test_two_commands_sequential(self):
        self.assert_identical_behavior(
            "cat <<A; cat <<B\nB\nA\ntail\nB\necho after")

    def test_two_operators_reversed_names(self):
        self.assert_identical_behavior(
            "cat <<B <<A\nA\nb body\nB\na body\nA\necho after")

    def test_three_operators(self):
        self.assert_identical_behavior(
            "cat <<A <<B <<C\nC\nB\nA\nx\nB\ny\nC\necho after")

    def test_closed_delimiter_line_is_plain_body(self):
        self.assert_identical_behavior(
            "cat <<A <<B\na\nA\nA\nB\necho after")

    def test_and_and_chain(self):
        self.assert_identical_behavior(
            "cat <<A && cat <<B\nB\nA\ntail\nB\necho after")

    def test_pipeline_members(self):
        self.assert_identical_behavior(
            "cat <<A | cat <<B\nB\nA\nzz\nB\necho after")

    def test_strip_tabs_policy_is_per_head(self):
        # <<-A strips tabs for A's terminator only; B's does not.
        self.assert_identical_behavior(
            f"cat <<-A <<B\n{TAB}B\n{TAB}A\nbB\nB\necho after")

    def test_duplicate_delimiters_same_operator(self):
        self.assert_identical_behavior(
            "cat <<A <<A\nfirst\nA\nsecond\nA\necho after")

    def test_duplicate_delimiters_two_commands(self):
        self.assert_identical_behavior(
            "cat <<A; cat <<A\nfirst\nA\nsecond\nA\necho after")

    def test_immediate_close_empty_head_body(self):
        self.assert_identical_behavior(
            "cat <<A; cat <<A\nA\nsecond\nA\necho after")

    def test_bodies_gather_after_whole_line(self):
        self.assert_identical_behavior(
            "cat <<A; echo mid; cat <<B\nbodyA\nA\nbodyB\nB\necho after")


class TestHeredocDelimiterShapeConformance(_HeredocTransactionBase):
    """The delimiter-shape table x expansion suppression (#20 H3)."""

    def test_ansi_c_delimiter_cooks_and_suppresses(self):
        self.assert_identical_behavior(
            "Y=v\ncat <<$'EOF'\nb $Y\nEOF\necho after")

    def test_ansi_c_escape_decodes(self):
        self.assert_identical_behavior(
            f"cat <<$'E\\tF'\nhi\nE{TAB}F\necho after")

    def test_ansi_c_escaped_quote(self):
        self.assert_identical_behavior(
            "cat <<$'E\\'F'\nhi\nE'F\necho after")

    def test_ansi_c_composite(self):
        self.assert_identical_behavior("cat <<$'A'B\nhi\nAB\necho after")

    def test_ansi_c_raw_spelling_is_body_text(self):
        # The line $'EOF' is BODY; the cooked terminator is EOF.
        self.assert_identical_behavior(
            "cat <<$'EOF'\nhi\n$'EOF'\nEOF\necho after")

    def test_locale_dq_delimiter(self):
        self.assert_identical_behavior(
            'Y=v\ncat <<$"EOF"\nb $Y\nEOF\necho after')

    def test_unquoted_dollar_word_is_literal_and_expands_body(self):
        self.assert_identical_behavior(
            "X=v\ncat <<$X\nval=$X\n$X\necho after")

    def test_procsub_shaped_delimiter(self):
        self.assert_identical_behavior(
            "X=v\ncat << <(x)\nval=$X\n<(x)\necho after")

    def test_procsub_out_shaped_delimiter(self):
        self.assert_identical_behavior("cat << >(x)\nhi\n>(x)\necho after")

    def test_procsub_composite_delimiter(self):
        self.assert_identical_behavior("cat << <(x)y\nhi\n<(x)y\necho after")

    def test_procsub_space_inside(self):
        self.assert_identical_behavior("cat << <(a b)\nhi\n<(a b)\necho after")

    def test_procsub_glued_continuation(self):
        self.assert_identical_behavior("cat <<E<(x)\nhi\nE<(x)\necho after")

    def test_procsub_nested_parens_rejected(self):
        # bash's heredoc-word reader does not nest parens: syntax error.
        self.assert_same_error_class("cat << <(a(b)c)\nhi\n<(a(b)c)\necho after")

    def test_herestring_glue_is_not_heredoc(self):
        self.assert_same_error_class("cat <<<(x)")

    def test_classic_shapes_still_conform(self):
        for command in (
            "Y=v\ncat <<\\EOF\nb $Y\nEOF\necho after",
            'Y=v\ncat <<E"O"F\nb $Y\nEOF\necho after',
            'cat <<"E\\"F"\nhi\nE"F\necho after',
            "Y=v\ncat <<'EOF'\nb $Y\nEOF\necho after",
            f"cat <<-'EOF'\n{TAB}hi\n{TAB}EOF\necho after",
            "cat <<$\nhi\n$\necho after",
            "X=v\ncat <<E$X\nbody\nE$X\necho after",
            "Y=v\ncat <<EOF\nb $Y\nEOF\necho after",
        ):
            self.assert_identical_behavior(command)


class TestHeredocEofTerminationConformance(_HeredocTransactionBase):
    """Unterminated heredocs: body kept, bash-shaped warning, command runs."""

    def test_single_unterminated(self):
        self.assert_same_with_normalized_stderr("cat <<EOF\nhi")

    def test_two_pending_first_keeps_body(self):
        self.assert_same_with_normalized_stderr("cat <<A <<B\nhi")

    def test_quoted_unterminated_literal_body(self):
        self.assert_same_with_normalized_stderr("cat <<'EOF'\n$x")

    def test_empty_unterminated(self):
        self.assert_same_with_normalized_stderr("cat <<EOF")


class TestHeredocFormatterRoundTripConformance(_HeredocTransactionBase):
    """eval "$(declare -f f)" preserves heredoc behavior (raw delimiter)."""

    def test_round_trip_rows(self):
        for command in (
            'f() {\ncat <<$X\nb $Y\n$X\n}\ng="$(declare -f f)"\n'
            'unset -f f\neval "$g"\nY=v f\necho after',
            "f() {\ncat <<'EOF'\nb $Y\nEOF\n}\ng=\"$(declare -f f)\"\n"
            'unset -f f\neval "$g"\nY=v f\necho after',
            "f() {\ncat <<$'EOF'\nb $Y\nEOF\n}\ng=\"$(declare -f f)\"\n"
            'unset -f f\neval "$g"\nY=v f\necho after',
            f'f() {{\ncat <<-EOF\n{TAB}b $Y\n{TAB}EOF\n}}\n'
            'g="$(declare -f f)"\nunset -f f\neval "$g"\nY=v f\necho after',
            'f() {\ncat <<E"O"F\nb $Y\nEOF\n}\ng="$(declare -f f)"\n'
            'unset -f f\neval "$g"\nY=v f\necho after',
        ):
            self.assert_identical_behavior(command)


class TestHeredocInputModeConformance(_HeredocTransactionBase):
    """The queue battery holds in script-file and stdin modes too."""

    QUEUE_SCRIPT = "cat <<A; cat <<B\nB\nA\ntail\nB\necho after"
    EXPECT_OUT = "B\ntail\nafter\n"

    def _bash(self):
        from harness.shell_oracle import resolve_bash
        return resolve_bash().path

    def test_script_file_mode(self):
        with tempfile.NamedTemporaryFile('w', suffix='.sh', delete=False) as f:
            f.write(self.QUEUE_SCRIPT + "\n")
            path = f.name
        try:
            psh = subprocess.run(
                [sys.executable, '-m', 'psh', path],
                capture_output=True, text=True, cwd=_REPO, timeout=15)
            bash = subprocess.run(
                [self._bash(), path],
                capture_output=True, text=True, timeout=15)
            assert psh.stdout == bash.stdout == self.EXPECT_OUT
            assert psh.returncode == bash.returncode == 0
        finally:
            Path(path).unlink()

    def test_stdin_mode(self):
        psh = subprocess.run(
            [sys.executable, '-m', 'psh'],
            input=self.QUEUE_SCRIPT + "\n",
            capture_output=True, text=True, cwd=_REPO, timeout=15)
        bash = subprocess.run(
            [self._bash()], input=self.QUEUE_SCRIPT + "\n",
            capture_output=True, text=True, timeout=15)
        assert psh.stdout == bash.stdout == self.EXPECT_OUT
        assert psh.returncode == bash.returncode == 0
