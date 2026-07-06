"""Command-substitution byte policy (expansion Phase-1a F1).

bash treats a command substitution's captured output as bytes: NUL bytes are
stripped (with one warning per substitution) because they cannot survive in a
C string / argv / environment, and every other byte round-trips unchanged.
psh previously decoded with errors='replace' (0xFF -> U+FFFD -> ``ef bf bd``)
and kept NUL bytes. It now strips NUL (warning once) and decodes with
surrogateescape, so bytes round-trip back out through builtin output, external
argv, the environment, and here-doc/here-string bodies.

These are subprocess tests: the round-trip needs real byte-level fds (a NUL or
0xFF cannot travel through pytest's text capture). Bytes are emitted and read
back with python3 and reported as integer lists, so assertions stay exact and
platform-stable. All expectations were pinned against bash 5.2.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV = {**os.environ, 'PYTHONPATH': str(REPO_ROOT)}
ENV.pop('PYTHONIOENCODING', None)


def run_psh_bytes(command: str):
    """Run `psh -c command` with a sealed stdin; return (stdout, stderr, rc)."""
    p = subprocess.run([sys.executable, '-m', 'psh', '-c', command],
                       input=b'', capture_output=True, timeout=20,
                       cwd=str(REPO_ROOT), env=ENV)
    return p.stdout, p.stderr, p.returncode


def _emit(byte_list):
    """A shell snippet that writes exactly `byte_list` to stdout via python3."""
    blist = ','.join(str(b) for b in byte_list)
    return f"python3 -c 'import os;os.write(1,bytes([{blist}]))'"


_REPORT = ("python3 -c 'import sys;"
           "sys.stdout.write(str(list(sys.stdin.buffer.read())))'")


class TestByteRoundTrip:
    def test_all_non_nul_bytes_round_trip_through_output(self):
        """Every byte 1..255 survives cmdsub capture and printf output."""
        allb = list(range(1, 256))
        out, err, rc = run_psh_bytes(
            f'x=$({_emit(allb)}); printf %s "$x" | {_REPORT}')
        assert rc == 0, err
        assert out == str(allb).encode()

    def test_high_byte_round_trips_via_external_argv(self):
        out, err, rc = run_psh_bytes(
            f'x=$({_emit([255])}); python3 -c '
            f"'import sys,os;sys.stdout.write(str(list(os.fsencode(sys.argv[1]))))'"
            f' "$x"')
        assert rc == 0, err
        assert out == b'[255]'

    def test_high_byte_round_trips_via_environment(self):
        out, err, rc = run_psh_bytes(
            f'export X=$({_emit([255])}); python3 -c '
            f"'import os,sys;sys.stdout.write(str(list(os.environb[b\"X\"])))'")
        assert rc == 0, err
        assert out == b'[255]'

    def test_valid_utf8_unchanged(self):
        # é = c3 a9 stays two bytes (a valid sequence, decoded then re-encoded).
        out, _, rc = run_psh_bytes(
            f'x=$({_emit([0xc3, 0xa9])}); printf %s "$x" | {_REPORT}')
        assert rc == 0
        assert out == b'[195, 169]'

    def test_heredoc_body_round_trips_bytes(self):
        out, _, rc = run_psh_bytes(
            f'x=$({_emit([255, 97])}); cat <<< "$x" | {_REPORT}')
        assert rc == 0
        assert out == b'[255, 97, 10]'  # here-string appends a newline

    def test_redirect_to_file_round_trips_bytes(self, tmp_path):
        target = tmp_path / 'out.bin'
        out, err, rc = run_psh_bytes(
            f'x=$({_emit([255])}); printf %s "$x" > {target}')
        assert rc == 0, err
        assert target.read_bytes() == b'\xff'


class TestNulStripping:
    def test_nul_stripped_from_value(self):
        out, err, rc = run_psh_bytes(
            f'x=$({_emit([97, 0, 98])}); printf "<%s>" "$x"')
        assert rc == 0
        assert out == b'<ab>'
        assert b'ignored null byte in input' in err

    @pytest.mark.parametrize('bytes_in,expected', [
        ([0, 97], b'<a>'),        # leading
        ([97, 0], b'<a>'),        # trailing
        ([0], b'<>'),             # only NUL
        ([97, 0, 98, 0, 99], b'<abc>'),  # multiple
    ])
    def test_nul_positions_all_stripped(self, bytes_in, expected):
        out, err, rc = run_psh_bytes(
            f'x=$({_emit(bytes_in)}); printf "<%s>" "$x"')
        assert rc == 0
        assert out == expected

    def test_one_warning_per_substitution(self):
        # Multiple NULs in one substitution -> exactly one warning (bash).
        _, err, _ = run_psh_bytes(
            f'x=$({_emit([97, 0, 98, 0, 99])}); printf "%s" "$x"')
        assert err.count(b'ignored null byte in input') == 1

    def test_two_substitutions_two_warnings(self):
        _, err, _ = run_psh_bytes(
            f'a=$({_emit([0, 97])}); b=$({_emit([0, 98])}); printf "%s%s" "$a" "$b"')
        assert err.count(b'ignored null byte in input') == 2

    def test_no_warning_without_nul(self):
        _, err, _ = run_psh_bytes(
            f'x=$({_emit([97, 98])}); printf "%s" "$x"')
        assert b'null byte' not in err
