"""Integration tests: execution of command substitutions whose extent
requires grammar-aware scanning (case patterns, comments, heredocs).

These forms were parse errors before the grammar-aware extent scanner
(find_command_substitution_end); each case here was verified against
bash 5.2. Run in subprocesses because several exercise the multi-line
input gathering in the source processor.
"""

import subprocess
import sys


def run_psh(script, parser=None):
    cmd = [sys.executable, '-m', 'psh']
    if parser:
        cmd += ['--parser', parser]
    cmd += ['-c', script]
    return subprocess.run(cmd, capture_output=True, text=True)


class TestCasePatternInCommandSub:
    """Bare `pattern)` case forms inside $(...) execute correctly."""

    def test_headline_case(self):
        r = run_psh('echo $(case x in x) echo inner;; esac)')
        assert r.returncode == 0 and r.stdout == 'inner\n' and r.stderr == ''

    def test_headline_case_combinator_parser(self):
        r = run_psh('echo $(case x in x) echo inner;; esac)',
                    parser='combinator')
        assert r.returncode == 0 and r.stdout == 'inner\n' and r.stderr == ''

    def test_multi_branch(self):
        r = run_psh('echo $(case b in a) echo A;; b) echo B;; c) echo C;; esac)')
        assert r.returncode == 0 and r.stdout == 'B\n'

    def test_fallthrough_operators(self):
        r = run_psh('echo $(case x in x) echo one;;& *) echo two;; esac)')
        assert r.returncode == 0 and r.stdout == 'one two\n'
        r = run_psh('echo $(case x in x) echo one;& y) echo two;; esac)')
        assert r.returncode == 0 and r.stdout == 'one two\n'

    def test_nested_cmdsub_and_case(self):
        r = run_psh('echo $(echo $(case x in x) echo i;; esac))')
        assert r.returncode == 0 and r.stdout == 'i\n'

    def test_for_loop_words_from_case_cmdsub(self):
        r = run_psh('for f in $(case x in x) echo a b;; esac); do echo "<$f>"; done')
        assert r.returncode == 0 and r.stdout == '<a>\n<b>\n'

    def test_double_quoted_cmdsub(self):
        r = run_psh('echo "$(case x in x) echo dq;; esac)"')
        assert r.returncode == 0 and r.stdout == 'dq\n'

    def test_process_substitution(self):
        r = run_psh('cat <(case x in x) echo psub;; esac)')
        assert r.returncode == 0 and r.stdout == 'psub\n'

    def test_parameter_default_with_case_cmdsub(self):
        r = run_psh('unset v; echo ${v:-$(case x in x) echo d;; esac)}')
        assert r.returncode == 0 and r.stdout == 'd\n'

    def test_patsub_replacement_with_case_cmdsub(self):
        r = run_psh('x=abc; echo ${x/b/$(case q in q) echo Z;; esac)}')
        assert r.returncode == 0 and r.stdout == 'aZc\n'

    def test_composite_word(self):
        r = run_psh('echo pre$(case x in x) echo MID;; esac)post')
        assert r.returncode == 0 and r.stdout == 'preMIDpost\n'

    def test_backtick_form_already_worked(self):
        r = run_psh('echo `case x in x) echo bt;; esac`')
        assert r.returncode == 0 and r.stdout == 'bt\n'


class TestCommentsAndHeredocsInCommandSub:
    """Parens hidden in comments and heredoc bodies inside $(...)."""

    def test_comment_hides_paren(self):
        r = run_psh('echo $(# comment with )\necho hi)')
        assert r.returncode == 0 and r.stdout == 'hi\n' and r.stderr == ''

    def test_comment_at_line_end(self):
        r = run_psh('echo $(echo hi # not-a-paren )\n)')
        assert r.returncode == 0 and r.stdout == 'hi\n' and r.stderr == ''

    def test_heredoc_body_paren(self):
        r = run_psh('echo $(cat <<EOF\n)\nEOF\n)')
        assert r.returncode == 0 and r.stdout == ')\n' and r.stderr == ''

    def test_quoted_delimiter_heredoc_body(self):
        r = run_psh('echo $(cat <<"EOF"\na ) b\nEOF\n)')
        assert r.returncode == 0 and r.stdout == 'a ) b\n' and r.stderr == ''


class TestMultilineCommandSub:
    """Unclosed $(...) is incomplete input: more lines are gathered."""

    def test_multiline_cmdsub_dash_c(self):
        r = run_psh('echo $(\necho multi\n)')
        assert r.returncode == 0 and r.stdout == 'multi\n' and r.stderr == ''

    def test_multiline_case_cmdsub(self):
        r = run_psh('echo $(case x in\nx) echo nl;;\nesac)')
        assert r.returncode == 0 and r.stdout == 'nl\n' and r.stderr == ''

    def test_multiline_cmdsub_stdin(self):
        r = subprocess.run([sys.executable, '-m', 'psh'],
                           input='echo $(\necho stdin-multi\n)\n',
                           capture_output=True, text=True)
        assert r.returncode == 0 and r.stdout == 'stdin-multi\n'

    def test_multiline_cmdsub_script(self, tmp_path):
        script = tmp_path / 's.sh'
        script.write_text('echo $(\necho script-multi\n)\n')
        r = subprocess.run([sys.executable, '-m', 'psh', str(script)],
                           capture_output=True, text=True)
        assert r.returncode == 0 and r.stdout == 'script-multi\n'

    def test_unclosed_at_eof_still_errors(self):
        r = run_psh('echo $(foo')
        assert r.returncode == 2
        assert 'unclosed command substitution' in r.stderr


class TestUnsupportedFormsStillRejected:
    """Degenerate inputs keep failing (bash rejects them too)."""

    def test_escaped_paren_pattern_rejected(self):
        # bash: "syntax error near unexpected token `echo'"; psh reports the
        # substitution as unclosed. Both reject with a nonzero status.
        r = run_psh('echo $(case x in x\\) echo esc;; esac)')
        assert r.returncode != 0

    def test_unterminated_case_before_closer_rejected(self):
        # bash: "syntax error near unexpected token `)'"
        r = run_psh('echo $(case x in x) echo hi)')
        assert r.returncode != 0
