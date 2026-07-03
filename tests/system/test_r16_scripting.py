"""Reappraisal #16 Tier-2 SCRIPTING cluster: `source`/`.` semantics and the
CR-in-script-file data-integrity fix. Pinned against bash 5.2.

Findings covered here (LINENO drift → test_lineno_script_file.py; POSIX short
options → test_cli_argument_parsing.py):

* $0 is NOT changed inside a sourced file (the file sees the caller's $0);
* a NO-ARG `source`/`.` shares the caller's positionals (a `set --` inside
  it persists), while a WITH-ARGS source saves/restores them;
* `source`/`.` searches $PATH before the current directory (non-posix bash);
* a script file preserves embedded CR bytes (no universal-newline CR→LF).
"""
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV = {**os.environ, 'PYTHONPATH': str(REPO_ROOT)}


def run_psh(*args, cwd=None, env=None, stdin_input=None):
    return subprocess.run([sys.executable, '-m', 'psh', *args],
                          capture_output=True, text=True, timeout=10,
                          cwd=cwd, env=env or ENV, input=stdin_input)


def run_bash(*args, cwd=None, env=None, stdin_input=None):
    return subprocess.run(['bash', *args], capture_output=True, text=True,
                          timeout=10, cwd=cwd, env=env or os.environ.copy(),
                          input=stdin_input)


class TestSourceDollarZero:
    def test_sourced_file_sees_caller_dollar0(self, tmp_path):
        (tmp_path / 's2.sh').write_text('echo "$0"\n')
        (tmp_path / 'main.sh').write_text('source ./s2.sh\n')
        psh = run_psh('./main.sh', cwd=str(tmp_path))
        bash = run_bash('./main.sh', cwd=str(tmp_path))
        assert psh.stdout == bash.stdout == './main.sh\n'

    def test_dot_form_sees_caller_dollar0(self, tmp_path):
        (tmp_path / 's2.sh').write_text('echo "$0"\n')
        (tmp_path / 'main.sh').write_text('. ./s2.sh\n')
        psh = run_psh('./main.sh', cwd=str(tmp_path))
        assert psh.stdout == './main.sh\n'


class TestSourcePositionals:
    def test_noarg_source_set_persists(self, tmp_path):
        (tmp_path / 'setonly.sh').write_text('set -- A B C\n')
        script = 'set -- x; . ./setonly.sh; echo "$@"'
        psh = run_psh('-c', script, cwd=str(tmp_path))
        bash = run_bash('-c', script, cwd=str(tmp_path))
        assert psh.stdout == bash.stdout == 'A B C\n'

    def test_noarg_source_without_set_leaves_positionals(self, tmp_path):
        (tmp_path / 'quiet.sh').write_text('echo "in:$@"\n')
        script = 'set -- x y; . ./quiet.sh; echo "out:$@"'
        psh = run_psh('-c', script, cwd=str(tmp_path))
        bash = run_bash('-c', script, cwd=str(tmp_path))
        assert psh.stdout == bash.stdout == 'in:x y\nout:x y\n'

    def test_witharg_source_restores_positionals(self, tmp_path):
        # WITH args: the sourced file sees Q R, then the caller's x y is
        # restored on return (the file did not itself `set --`).
        (tmp_path / 'echoargs.sh').write_text('echo "in:$@"\n')
        script = 'set -- x y; . ./echoargs.sh Q R; echo "out:$@"'
        psh = run_psh('-c', script, cwd=str(tmp_path))
        bash = run_bash('-c', script, cwd=str(tmp_path))
        assert psh.stdout == bash.stdout == 'in:Q R\nout:x y\n'


class TestSourcePathSearch:
    def test_path_dir_wins_over_cwd(self, tmp_path):
        pathdir = tmp_path / 'pathdir'
        pathdir.mkdir()
        (pathdir / 'both.sh').write_text('echo from-PATH\n')
        (tmp_path / 'both.sh').write_text('echo from-CWD\n')
        env = {**ENV, 'PATH': f"{pathdir}:{ENV.get('PATH', '')}"}
        benv = {**os.environ, 'PATH': f"{pathdir}:{os.environ.get('PATH', '')}"}
        psh = run_psh('-c', '. both.sh', cwd=str(tmp_path), env=env)
        bash = run_bash('-c', '. both.sh', cwd=str(tmp_path), env=benv)
        assert psh.stdout == bash.stdout == 'from-PATH\n'

    def test_cwd_fallback_when_not_on_path(self, tmp_path):
        (tmp_path / 'only.sh').write_text('echo from-CWD\n')
        env = {**ENV, 'PATH': '/nonexistent-dir-xyz'}
        psh = run_psh('-c', '. only.sh', cwd=str(tmp_path), env=env)
        assert psh.returncode == 0
        assert psh.stdout == 'from-CWD\n'


class TestScriptFileCarriageReturn:
    # NOTE: these capture RAW BYTES (text=False). subprocess text-mode capture
    # applies universal-newline translation to the CHILD's stdout, which would
    # itself turn a genuine \r byte into \n and hide the very divergence under
    # test.
    @staticmethod
    def _bytes(argv, cwd=None):
        return subprocess.run(argv, capture_output=True, timeout=10,
                              cwd=cwd, env=ENV).stdout

    def test_embedded_cr_in_double_quotes_preserved(self, tmp_path):
        # bash keeps the raw CR byte in the value; psh used to translate it to
        # LF (universal newlines), corrupting the value.
        script = tmp_path / 'cr.sh'
        script.write_bytes(b'x="a\rb"\nprintf %s "$x"\n')
        psh = self._bytes([sys.executable, '-m', 'psh', str(script)])
        bash = subprocess.run(['bash', str(script)], capture_output=True,
                              timeout=10).stdout
        assert psh == bash == b'a\rb'

    def test_embedded_cr_in_single_quotes_preserved(self, tmp_path):
        script = tmp_path / 'cr2.sh'
        script.write_bytes(b"x='a\rb'\nprintf %s \"$x\"\n")
        psh = self._bytes([sys.executable, '-m', 'psh', str(script)])
        bash = subprocess.run(['bash', str(script)], capture_output=True,
                              timeout=10).stdout
        assert psh == bash == b'a\rb'

    def test_plain_lf_script_unaffected(self, tmp_path):
        script = tmp_path / 'lf.sh'
        script.write_bytes(b'echo one\necho two\n')
        psh = run_psh(str(script))
        assert psh.returncode == 0
        assert psh.stdout == 'one\ntwo\n'
