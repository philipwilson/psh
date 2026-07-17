"""Tests for the mapfile / readarray builtin.

mapfile reads lines from input into an indexed array. Because a pipeline's
right-hand side runs in a subshell (where the array would be lost), these tests
feed input via a here-string / file redirection into the in-process shell, or
group the consumer with mapfile inside the same subshell.
"""

import subprocess
import sys

import pytest
from shell_oracle import resolve_bash

BASH = resolve_bash().path


def _run(script, stdin=""):
    """Run a psh script in a subprocess with the given stdin."""
    return subprocess.run([sys.executable, '-m', 'psh', '-c', script],
                          input=stdin, capture_output=True, text=True)


class TestMapfileBasic:
    def test_reads_lines_keeping_newlines(self):
        r = _run('mapfile x; printf "%s" "${x[0]}${x[1]}"', "a\nb\n")
        assert r.stdout == "a\nb\n"

    def test_strip_with_t(self):
        r = _run('mapfile -t x; echo "[${x[0]}][${x[1]}] ${#x[@]}"', "a\nb\n")
        assert r.stdout.strip() == "[a][b] 2"

    def test_default_array_is_mapfile(self):
        r = _run('mapfile -t; echo "${MAPFILE[1]}"', "a\nb\n")
        assert r.stdout.strip() == "b"

    def test_readarray_is_synonym(self):
        r = _run('readarray -t a; echo "${a[1]}"', "x\ny\n")
        assert r.stdout.strip() == "y"

    def test_empty_input_makes_empty_array(self):
        r = _run('mapfile -t a; echo "n=${#a[@]}"', "")
        assert r.stdout.strip() == "n=0"

    def test_final_line_without_newline_is_kept(self):
        r = _run('mapfile -t a; echo "${a[@]} n=${#a[@]}"', "a\nb")
        assert r.stdout.strip() == "a b n=2"


class TestMapfileOptions:
    def test_n_limits_count(self):
        r = _run('mapfile -t -n 2 a; echo "${a[@]} ${#a[@]}"', "1\n2\n3\n4\n")
        assert r.stdout.strip() == "1 2 2"

    def test_n_zero_reads_all(self):
        r = _run('mapfile -t -n 0 a; echo "${#a[@]}"', "1\n2\n3\n")
        assert r.stdout.strip() == "3"

    def test_s_skips_lines(self):
        r = _run('mapfile -t -s 1 a; echo "${a[@]}"', "1\n2\n3\n")
        assert r.stdout.strip() == "2 3"

    def test_O_origin_does_not_clear(self):
        r = _run('a=(k0 k1 k2 k3); mapfile -t -O 1 a <<< $\'X\\nY\'; echo "${a[@]}"')
        assert r.stdout.strip() == "k0 X Y k3"

    def test_default_clears_array(self):
        r = _run('a=(o0 o1 o2); mapfile -t a <<< N; echo "${a[@]} ${#a[@]}"')
        assert r.stdout.strip() == "N 1"

    def test_d_custom_delimiter(self):
        r = _run('mapfile -t -d : a; echo "${a[@]} ${#a[@]}"', "x:y:z:")
        assert r.stdout.strip() == "x y z 3"

    def test_clustered_flags(self):
        r = _run('mapfile -tn2 a; echo "${a[@]}"', "1\n2\n3\n")
        assert r.stdout.strip() == "1 2"

    def test_u_reads_from_fd(self, tmp_path):
        f = tmp_path / "mf.txt"
        f.write_text("p\nq\n")
        r = _run(f'exec 3< "{f}"; mapfile -t -u 3 a; exec 3<&-; echo "${{a[@]}}"')
        assert r.stdout.strip() == "p q"

    def test_redirect_from_file(self, tmp_path):
        f = tmp_path / "mf2.txt"
        f.write_text("p\nq\n")
        r = _run(f'mapfile -t a < "{f}"; echo "${{a[@]}}"')
        assert r.stdout.strip() == "p q"


class TestMapfileErrors:
    def test_invalid_array_name(self):
        r = _run('mapfile -t 1bad', "hi\n")
        assert r.returncode == 1
        assert "not a valid identifier" in r.stderr

    def test_invalid_option(self):
        r = _run('mapfile -z a', "hi\n")
        assert r.returncode == 2
        assert "invalid option" in r.stderr

    def test_callback_option_unsupported(self):
        r = _run('mapfile -C cb a', "hi\n")
        assert r.returncode == 2
        assert "not supported" in r.stderr

    def test_quantum_option_unsupported(self):
        # -c quantum is only meaningful with -C; psh honest-errors both
        # rather than silently ignoring them.
        r = _run('mapfile -c 2 a', "hi\n")
        assert r.returncode == 2
        assert "not supported" in r.stderr

    def test_callback_does_not_consume_input_or_create_array(self):
        # The honest error fires BEFORE any input is read: the target array
        # must not be created (regression guard against a silent
        # input-consuming no-op — R18 T2-G).
        r = _run('mapfile -C cb arr; declare -p arr', "a\nb\nc\n")
        assert r.returncode != 0
        assert "not supported" in r.stderr
        assert "arr=" not in r.stdout

    def test_extra_args_ignored(self):
        # bash uses the first arg and ignores the rest (exit 0).
        r = _run('mapfile -t a b <<< hi; echo "rc=$? a=${a[0]}"')
        assert r.stdout.strip() == "rc=0 a=hi"


class TestMapfileType:
    def test_type_recognises_readarray_alias(self):
        r = _run('type readarray; type mapfile')
        assert "readarray is a shell builtin" in r.stdout
        assert "mapfile is a shell builtin" in r.stdout


class TestMapfileBashParity:

    @pytest.mark.parametrize("script,stdin", [
        ('mapfile -t a; echo "${a[@]}|${#a[@]}"', "one\ntwo\nthree\n"),
        ('mapfile a; printf "%s" "${a[0]}"', "keep\n"),
        ('mapfile -t -n 2 a; echo "${a[@]}"', "1\n2\n3\n"),
        ('mapfile -t -s 1 a; echo "${a[@]}"', "x\ny\nz\n"),
        ('mapfile -t -d : a; echo "${a[@]}|${#a[@]}"', "a:b:c:"),
        ('readarray -t a; echo "${#a[@]}"', ""),
    ])
    def test_matches_bash(self, script, stdin):
        psh = _run(script, stdin)
        bash = subprocess.run([BASH, '-c', script], input=stdin,
                              capture_output=True, text=True)
        assert psh.stdout == bash.stdout
        assert psh.returncode == bash.returncode
