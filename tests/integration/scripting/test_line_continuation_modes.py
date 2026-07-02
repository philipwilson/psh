"""Line-continuation contexts behave identically in script, -c, and stdin
modes (reappraisal #15, A5).

The three non-interactive front-ends (FileInput, StringInput for -c, and
slurped stdin) all preprocess through the same
``process_line_continuations``; these subprocess tests pin that a comment
ending in a backslash does not swallow the next command and that a quoted
heredoc body keeps its literal trailing backslashes, in every mode.
"""

import subprocess
import sys

import pytest

COMMENT_SCRIPT = "# comment ends in backslash \\\necho survived\n"
QUOTED_HEREDOC_SCRIPT = "cat <<'EOF'\na\\\nb\nEOF\necho after\n"
UNQUOTED_HEREDOC_SCRIPT = "cat <<EOF\na\\\nb\nEOF\necho after\n"


def run_psh(script, mode, tmp_path):
    if mode == 'script':
        path = tmp_path / 'input.sh'
        path.write_text(script)
        return subprocess.run([sys.executable, '-m', 'psh', str(path)],
                              capture_output=True, text=True, timeout=15)
    if mode == '-c':
        return subprocess.run([sys.executable, '-m', 'psh', '-c', script],
                              capture_output=True, text=True, timeout=15)
    return subprocess.run([sys.executable, '-m', 'psh'], input=script,
                          capture_output=True, text=True, timeout=15)


@pytest.mark.parametrize('mode', ['script', '-c', 'stdin'])
class TestContinuationContextsAcrossModes:
    def test_comment_backslash_does_not_swallow_next_line(self, mode, tmp_path):
        result = run_psh(COMMENT_SCRIPT, mode, tmp_path)
        assert result.returncode == 0
        assert result.stdout == "survived\n"
        assert result.stderr == ""

    def test_quoted_heredoc_keeps_trailing_backslash(self, mode, tmp_path):
        result = run_psh(QUOTED_HEREDOC_SCRIPT, mode, tmp_path)
        assert result.returncode == 0
        assert result.stdout == "a\\\nb\nafter\n"
        assert result.stderr == ""

    def test_unquoted_heredoc_still_joins(self, mode, tmp_path):
        result = run_psh(UNQUOTED_HEREDOC_SCRIPT, mode, tmp_path)
        assert result.returncode == 0
        assert result.stdout == "ab\nafter\n"
        assert result.stderr == ""

    def test_comment_backslash_inside_if_body(self, mode, tmp_path):
        script = "if true; then\n# c \\\necho body\nfi\n"
        result = run_psh(script, mode, tmp_path)
        assert result.returncode == 0
        assert result.stdout == "body\n"
        assert result.stderr == ""

    def test_hash_inside_backtick_splices(self, mode, tmp_path):
        # Regression: bash splices backslash-newline inside a backtick word
        # regardless of '#'; the comment then eats the joined-in text, so the
        # substitution yields just "a".
        script = "echo `echo a # c \\\necho b`\n"
        result = run_psh(script, mode, tmp_path)
        assert result.returncode == 0
        assert result.stdout == "a\n"
        assert result.stderr == ""

    def test_hash_inside_closed_backtick_keeps_outer_join(self, mode, tmp_path):
        script = "echo `echo a # b` \\\necho c\n"
        result = run_psh(script, mode, tmp_path)
        assert result.returncode == 0
        assert result.stdout == "a echo c\n"
        assert result.stderr == ""

    def test_single_quote_inside_backtick_splices(self, mode, tmp_path):
        script = "echo `echo 'a \\\nb'`\n"
        result = run_psh(script, mode, tmp_path)
        assert result.returncode == 0
        assert result.stdout == "a b\n"
        assert result.stderr == ""

    def test_comment_after_closed_backtick_does_not_swallow(self, mode, tmp_path):
        # The A5 comment fix stays intact when a closed backtick precedes it.
        script = "echo `echo hi` # trailing \\\necho survived\n"
        result = run_psh(script, mode, tmp_path)
        assert result.returncode == 0
        assert result.stdout == "hi\nsurvived\n"
        assert result.stderr == ""

    def test_command_sub_comment_still_suppresses_join(self, mode, tmp_path):
        # Contrast: $( ) honors the interior comment (no splice), so line 2
        # runs as its own word inside the substitution.
        script = "echo $(echo a # c \\\necho b)\n"
        result = run_psh(script, mode, tmp_path)
        assert result.returncode == 0
        assert result.stdout == "a b\n"
        assert result.stderr == ""
