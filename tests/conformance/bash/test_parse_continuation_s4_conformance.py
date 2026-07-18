"""Conformance: parse-outcome-driven continuation is unchanged (campaign S4).

Campaign S4 rewired the completeness oracle and the cmdhist joiner to consume
the typed ``Complete | Incomplete | Invalid`` parse outcome instead of
re-deriving the trichotomy from ``ParseError.at_eof``. This must NOT change any
user-visible continuation behavior: multiline if/while/for/until/case/heredoc/
quote/unclosed-expansion continuation must behave identically to bash, and
identically across ``-c`` (whole-string parse) and file/stdin (the accumulator's
line-by-line continuation oracle).

It also pins the handoff-4 disposition: a heredoc whose cooked delimiter carries
a decoded newline, inside command substitution, matches bash on exit code and
stdout across all input modes (the only residual is psh's diagnostic wording).

All rows probed against bash 5.2.26; see tmp/boundary-ledgers/S4-probes/.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from conformance_framework import ConformanceTest

# Multiline scripts: each exercises a continuation construct. Chosen so the
# whole-string parse (-c) and the line-by-line accumulator (file/stdin) both
# must agree with bash.
CONTINUATION_SCRIPTS = {
    "if": "if true\nthen\necho yes\nfi\n",
    "if_else": "if false\nthen\necho a\nelse\necho b\nfi\n",
    "while": "n=0\nwhile [ $n -lt 2 ]\ndo\necho $n\nn=$((n+1))\ndone\n",
    "until": "n=0\nuntil [ $n -ge 2 ]\ndo\necho $n\nn=$((n+1))\ndone\n",
    "for": "for i in 1 2 3\ndo\necho $i\ndone\n",
    "case": "x=b\ncase $x in\na) echo A;;\nb) echo B;;\nesac\n",
    "nested": "for i in 1 2\ndo\nif [ $i = 1 ]\nthen\necho one\nfi\ndone\n",
    "function": "greet()\n{\necho hi\n}\ngreet\n",
    "brace_group": "{\necho a\necho b\n}\n",
    "subshell": "(\necho sub\n)\n",
    "heredoc": "cat <<EOF\nline one\nline two\nEOF\n",
    "heredoc_dash": "cat <<-END\n\tindented\nEND\n",
    "quoted_multiline": "echo 'line one\nline two'\n",
    "dquoted_multiline": 'echo "a\nb"\n',
    "backslash_continuation": "echo one \\\ntwo three\n",
    "andor_continuation": "true &&\necho ok\n",
    "pipe_continuation": "echo hello |\ncat\n",
    "unclosed_then_closed_expansion": "echo $(\necho inner\n)\n",
}

# Handoff 4: heredoc with a decoded-newline cooked delimiter, in/out of $(...).
HANDOFF4_SCRIPTS = {
    "h4_top_level_newline_delim": "cat <<$'E\\nF'\nbody\nE\nF\n",
    "h4_cmdsub_newline_delim": "x=$(cat <<$'E\\nF'\nbody\nE\nF\n)\necho \"[$x]\"\n",
    "h4_cmdsub_tab_delim": "x=$(cat <<$'E\\tF'\nbody\nE\tF\n)\necho \"[$x]\"\n",
    "h4_cmdsub_plain_delim": "x=$(cat <<EOF\nbody\nEOF\n)\necho \"[$x]\"\n",
}


class TestParseContinuationConformance(ConformanceTest):
    """Multiline continuation is identical to bash across -c/file/stdin."""

    def _run(self, argv, script, mode, cwd):
        if mode == "-c":
            return subprocess.run(argv + ["-c", script], capture_output=True,
                                  text=True, timeout=30, cwd=cwd)
        if mode == "file":
            p = Path(cwd) / "script.sh"
            p.write_text(script)
            return subprocess.run(argv + [str(p)], capture_output=True,
                                  text=True, timeout=30, cwd=cwd)
        return subprocess.run(argv, input=script, capture_output=True,
                              text=True, timeout=30, cwd=cwd)

    @pytest.mark.parametrize("mode", ["-c", "file", "stdin"])
    @pytest.mark.parametrize("name", list(CONTINUATION_SCRIPTS))
    def test_continuation_matches_bash(self, name, mode):
        script = CONTINUATION_SCRIPTS[name]
        with tempfile.TemporaryDirectory() as d:
            bash = self._run(self.framework.bash_path, script, mode, d)
            psh = self._run([sys.executable, "-m", "psh"], script, mode, d)
        assert psh.returncode == bash.returncode, (
            f"{name}/{mode}: rc psh={psh.returncode} bash={bash.returncode}")
        assert psh.stdout == bash.stdout, (
            f"{name}/{mode}: stdout psh={psh.stdout!r} bash={bash.stdout!r}")

    @pytest.mark.parametrize("mode", ["-c", "file", "stdin"])
    @pytest.mark.parametrize("name", list(HANDOFF4_SCRIPTS))
    def test_handoff4_heredoc_newline_delim_in_cmdsub(self, name, mode):
        script = HANDOFF4_SCRIPTS[name]
        with tempfile.TemporaryDirectory() as d:
            bash = self._run(self.framework.bash_path, script, mode, d)
            psh = self._run([sys.executable, "-m", "psh"], script, mode, d)
        # Exit code and stdout match bash; stderr wording may differ (psh's
        # "unclosed command substitution" vs bash's "unexpected EOF" — the
        # documented, campaign-wide diagnostic divergence).
        assert psh.returncode == bash.returncode, (
            f"{name}/{mode}: rc psh={psh.returncode} bash={bash.returncode}\n"
            f"psh stderr: {psh.stderr!r}\nbash stderr: {bash.stderr!r}")
        assert psh.stdout == bash.stdout, (
            f"{name}/{mode}: stdout psh={psh.stdout!r} bash={bash.stdout!r}")
