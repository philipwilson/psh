"""Embedded (mid-word) process substitution: ``pre<(cmd)post``.

Bash performs process substitution anywhere in an unquoted word and
splices the /dev/fd/N path into the word at that position (verified
against bash 5.2):

    echo pre<(echo hi)post      ->  pre/dev/fd/63post
    echo a<(echo x)b<(echo y)c  ->  a/dev/fd/63b/dev/fd/62c
    echo "pre<(echo hi)post"    ->  pre<(echo hi)post   (quoted: literal)
    x=<(echo hi); echo "$x"     ->  /dev/fd/63          (assignment value)

Before v0.301 psh only recognized a process substitution standing alone
as a whole word; embedded occurrences fell through as literal text.
Both forms now share one mechanism: the parser builds a
ProcessSubstitution expansion part inside the Word, and the expansion
manager performs the substitution during word expansion, registering the
fd/pid with the same process_sub_scope() cleanup as before (v0.288).

All tests run psh in a subprocess (process/fd lifecycle of the whole
shell), matching test_process_sub_cleanup.py.
"""

import re
import subprocess
import sys

import pytest


def run_psh(cmd: str, timeout: float = 15.0) -> subprocess.CompletedProcess:
    """Run a command in a fresh psh process."""
    return subprocess.run(
        [sys.executable, '-m', 'psh', '-c', cmd],
        capture_output=True, text=True, timeout=timeout,
    )


def run_psh_combinator(cmd: str, timeout: float = 15.0) -> subprocess.CompletedProcess:
    """Run a command in a fresh psh process using the combinator parser."""
    return subprocess.run(
        [sys.executable, '-m', 'psh', '--parser', 'combinator', '-c', cmd],
        capture_output=True, text=True, timeout=timeout,
    )


class TestEmbeddedProcessSubstitution:
    """Affixed and multi-substitution words (bash-pinned)."""

    def test_affixed_read_side_path_form(self):
        """`echo pre<(echo hi)post` splices the path mid-word (bash:
        pre/dev/fd/63post)."""
        result = run_psh('echo pre<(echo hi)post')
        assert result.returncode == 0, result.stderr
        assert re.fullmatch(r'pre/dev/fd/\d+post\n', result.stdout), result.stdout

    def test_two_substitutions_in_one_word(self):
        """`echo a<(echo x)b<(echo y)c` creates two distinct substitutions
        (bash: a/dev/fd/63b/dev/fd/62c)."""
        result = run_psh('echo a<(echo x)b<(echo y)c')
        assert result.returncode == 0, result.stderr
        m = re.fullmatch(r'a/dev/fd/(\d+)b/dev/fd/(\d+)c\n', result.stdout)
        assert m, result.stdout
        assert m.group(1) != m.group(2), "both substitutions got the same fd"

    def test_affixed_substitution_is_live(self):
        """The embedded substitution is a real open pipe, not just text:
        a `/.` prefix yields the openable path /./dev/fd/N (bash: prints
        hi)."""
        result = run_psh('cat /.<(echo hi)')
        assert result.returncode == 0, result.stderr
        assert result.stdout == 'hi\n'

    def test_affixed_write_side_path_form(self):
        """`echo pre>(cat)post` — write side splices a path too (bash:
        pre/dev/fd/63post)."""
        result = run_psh('echo pre>(cat)post >/dev/null; echo done')
        assert result.returncode == 0, result.stderr
        assert 'done' in result.stdout

    def test_affixed_write_side_is_live(self, tmp_path):
        """tee /.>(cat > file) — the embedded write-side path is openable
        and feeds the child (bash-verified)."""
        out = tmp_path / 'embedded_out.txt'
        result = run_psh(
            f'echo data | tee /.>(cat > {out}) >/dev/null; sleep 0.3')
        assert result.returncode == 0, result.stderr
        assert out.read_text() == 'data\n'

    def test_affixed_path_is_textual(self):
        """`cat pre<(echo hi)post` fails: the argument is the literal text
        pre/dev/fd/Npost, which is not an openable path (bash: cat:
        pre/dev/fd/63: No such file or directory, rc=1)."""
        result = run_psh('cat pre<(echo hi)post; echo rc=$?')
        assert re.search(r'pre/dev/fd/\d+post', result.stderr), result.stderr
        assert 'rc=1' in result.stdout

    def test_double_quoted_stays_literal(self):
        """Quoted process substitution is literal text (bash)."""
        result = run_psh('echo "pre<(echo hi)post"')
        assert result.returncode == 0, result.stderr
        assert result.stdout == 'pre<(echo hi)post\n'

    def test_single_quoted_stays_literal(self):
        result = run_psh("echo 'pre<(echo hi)post'")
        assert result.returncode == 0, result.stderr
        assert result.stdout == 'pre<(echo hi)post\n'

    def test_path_not_subject_to_ifs_splitting(self):
        """The spliced /dev/fd/N path never field-splits, even with IFS=/
        (bash: process substitution is not a parameter/command/arithmetic
        expansion, so its result is exempt from word splitting)."""
        result = run_psh('IFS=/; echo pre<(echo hi)post')
        assert result.returncode == 0, result.stderr
        assert re.fullmatch(r'pre/dev/fd/\d+post\n', result.stdout), result.stdout

    def test_adjacent_to_quoted_text(self):
        """`echo <(echo a)"lit"<(echo b)` (bash: /dev/fd/63lit/dev/fd/62)."""
        result = run_psh('echo <(echo a)"lit"<(echo b)')
        assert result.returncode == 0, result.stderr
        assert re.fullmatch(r'/dev/fd/\d+lit/dev/fd/\d+\n', result.stdout), result.stdout


class TestProcessSubInAssignments:
    """Process substitution in assignment values (bash performs it)."""

    def test_whole_value_assignment(self):
        """`x=<(echo hi)` assigns the /dev/fd/N path (bash)."""
        result = run_psh('x=<(echo hi); echo "$x"')
        assert result.returncode == 0, result.stderr
        assert re.fullmatch(r'/dev/fd/\d+\n', result.stdout), result.stdout

    def test_affixed_value_assignment(self):
        """`x=pre<(echo hi)post` splices into the value (bash)."""
        result = run_psh('x=pre<(echo hi)post; echo "$x"')
        assert result.returncode == 0, result.stderr
        assert re.fullmatch(r'pre/dev/fd/\d+post\n', result.stdout), result.stdout

    def test_assignment_fd_closed_after_command(self):
        """The substitution's fd closes when the assignment finishes —
        a later `cat $x` cannot read it (bash: Bad file descriptor /
        No such file, rc!=0)."""
        result = run_psh('x=<(echo hi); cat "$x"; echo rc=$?')
        assert 'hi' not in result.stdout.replace('rc=', '')
        assert 'rc=0' not in result.stdout

    def test_array_initializer_element(self):
        """`a=(<(echo x))` stores the path as the element (bash)."""
        result = run_psh('a=(<(echo x)); echo "${a[0]}"')
        assert result.returncode == 0, result.stderr
        assert re.fullmatch(r'/dev/fd/\d+\n', result.stdout), result.stdout


class TestWholeWordRegression:
    """The pre-existing whole-word path must keep working unchanged."""

    def test_diff_two_substitutions(self):
        result = run_psh('diff <(echo a) <(echo a); echo rc=$?')
        assert result.stdout == 'rc=0\n', (result.stdout, result.stderr)

    def test_cat_single_substitution(self):
        result = run_psh('cat <(echo whole)')
        assert result.returncode == 0, result.stderr
        assert result.stdout == 'whole\n'

    def test_function_argument(self):
        result = run_psh('f() { cat "$1"; }; f <(echo ok)')
        assert result.returncode == 0, result.stderr
        assert result.stdout == 'ok\n'

    def test_redirect_target_still_works(self):
        """`< <(cmd)` redirect targets use a separate (string) path and
        must be unaffected."""
        result = run_psh(
            'while read l; do echo "got:$l"; done < <(printf "1\\n2\\n")')
        assert result.returncode == 0, result.stderr
        assert result.stdout == 'got:1\ngot:2\n'

    def test_case_pattern_stays_literal(self):
        """psh keeps `<(cmd)` literal in case patterns (no substitution is
        performed there); the literal pattern matches its own text."""
        result = run_psh(
            "case 'a<(x)c' in a<(x)c) echo m;; *) echo no;; esac")
        assert result.returncode == 0, result.stderr
        assert result.stdout == 'm\n'

    def test_heredoc_body_stays_literal(self):
        result = run_psh('cat <<EOF\npre<(echo hi)post\nEOF')
        assert result.returncode == 0, result.stderr
        assert result.stdout == 'pre<(echo hi)post\n'


class TestEmbeddedCleanup:
    """Embedded substitutions use the same scope cleanup as whole-word
    ones (v0.288): parent fds closed, children reaped without blocking."""

    def test_no_zombies_after_embedded_forms(self):
        """Embedded/assignment/array substitutions leave no defunct
        children once a later command's scope exit re-polls them."""
        cmd = (
            'cat pre<(echo a)post 2>/dev/null; '
            'echo pre<(echo b)post >/dev/null; '
            'x=<(echo c); '
            'a=(<(echo d)); '
            'sleep 0.3; '  # give the children time to exit
            'true; '       # later scope exit reaps them
            'ps -axo pid,ppid,stat | awk -v me=$$ \'$2==me {print $3}\''
        )
        result = run_psh(cmd)
        assert result.returncode == 0, result.stderr
        states = result.stdout.split()
        zombies = [s for s in states if s.startswith('Z')]
        assert zombies == [], (
            f"found zombie substitution children: {result.stdout!r}")

    def test_parent_fds_released_after_embedded_forms(self):
        """After several embedded-substitution commands, the lowest free
        fd in the shell is back to 3 (no parent-side fd leak)."""
        probe = (
            f'"{sys.executable}" -c '
            '"import os; print(os.open(\'/dev/null\', os.O_RDONLY))"'
        )
        cmd = (
            'cat pre<(echo a)post 2>/dev/null; '
            'echo a<(echo x)b<(echo y)c >/dev/null; '
            'x=<(echo c); '
            + probe
        )
        result = run_psh(cmd)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == '3', (
            f"fd slots leaked: lowest free fd is {result.stdout.strip()}")

    def test_failed_consumer_child_still_reaped(self):
        """`cat pre<(echo hi)post` FAILS (textual path), but the
        substitution child must still be reaped by a later command."""
        cmd = (
            'cat pre<(echo hi)post 2>/dev/null; '
            'cat pre<(echo hi)post 2>/dev/null; '
            'sleep 0.3; true; '
            'ps -axo pid,ppid,stat | awk -v me=$$ \'$2==me {print $3}\''
        )
        result = run_psh(cmd)
        assert result.returncode == 0, result.stderr
        zombies = [s for s in result.stdout.split() if s.startswith('Z')]
        assert zombies == [], (
            f"failed consumer leaked zombies: {result.stdout!r}")


class TestEmbeddedCombinatorParser:
    """The combinator parser shares the WordBuilder representation and
    must handle the same word-level forms."""

    def test_affixed_read_side(self):
        result = run_psh_combinator('echo pre<(echo hi)post')
        assert result.returncode == 0, result.stderr
        assert re.fullmatch(r'pre/dev/fd/\d+post\n', result.stdout), result.stdout

    def test_two_substitutions_in_one_word(self):
        result = run_psh_combinator('echo a<(echo x)b<(echo y)c')
        assert result.returncode == 0, result.stderr
        assert re.fullmatch(r'a/dev/fd/\d+b/dev/fd/\d+c\n', result.stdout), result.stdout

    def test_whole_word_still_works(self):
        result = run_psh_combinator('diff <(echo a) <(echo a); echo rc=$?')
        assert result.stdout == 'rc=0\n', (result.stdout, result.stderr)

    def test_quoted_stays_literal(self):
        result = run_psh_combinator('echo "pre<(echo hi)post"')
        assert result.returncode == 0, result.stderr
        assert result.stdout == 'pre<(echo hi)post\n'

    def test_assignment_value(self):
        result = run_psh_combinator('x=<(echo hi); echo "$x"')
        assert result.returncode == 0, result.stderr
        assert re.fullmatch(r'/dev/fd/\d+\n', result.stdout), result.stdout


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
