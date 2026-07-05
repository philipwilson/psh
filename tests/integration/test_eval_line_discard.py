"""eval processes its string line-by-line, so a word-arithmetic (or readonly)
discard-line error inside it discards only the OFFENDING line and resumes at
the next — matching bash.

eval used to feed its whole (multi-line) argument to the buffered-command
processor as a SINGLE chunk, so a discard-line error killed the entire eval
string. bash treats the eval argument like a script: `eval 'echo one\necho
$((1/0))\necho three'` prints one and three (line 2 dropped). Probe-verified
against bash 5.2 (tmp/probes-r18t2-arith/). See Shell.run_command's
line_oriented flag (eval passes True) and StringInput.split_lines.
"""

import subprocess
import sys


def _psh_c(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True, timeout=30)


class TestEvalLineDiscard:
    def test_multiline_arith_error_drops_only_that_line(self):
        r = _psh_c("eval 'echo one\necho $((1/0))\necho three'; echo after")
        assert r.stdout == "one\nthree\nafter\n"
        assert "Division by zero" in r.stderr
        assert r.returncode == 0

    def test_multiline_via_variable(self):
        r = _psh_c("m='echo one\necho $((1/0))\necho three'; "
                   'eval "$m"; echo after')
        assert r.stdout == "one\nthree\nafter\n"
        assert r.returncode == 0

    def test_multiline_arith_syntax_error(self):
        r = _psh_c("m='echo a\nx=$((5+))\necho c'; eval \"$m\"; echo after")
        assert r.stdout == "a\nc\nafter\n"
        assert r.returncode == 0

    def test_error_mid_string_resumes_and_finishes(self):
        r = _psh_c("m='echo one\nfoo=$((2/0))\necho three\necho four'; "
                   'eval "$m"; echo done')
        assert r.stdout == "one\nthree\nfour\ndone\n"
        assert r.returncode == 0

    def test_single_line_multi_statement_still_discards_rest_of_line(self):
        # No newline to resume at: the rest of the single line is dropped,
        # then the command after eval runs (bash).
        r = _psh_c("eval 'echo one; echo $((1/0)); echo two'; echo after")
        assert r.stdout == "one\nafter\n"
        assert r.returncode == 0

    def test_clean_multiline_unaffected(self):
        r = _psh_c("eval 'echo one\necho two'; echo after")
        assert r.stdout == "one\ntwo\nafter\n"
        assert r.returncode == 0
