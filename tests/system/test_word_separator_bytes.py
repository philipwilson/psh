"""Word separators are space and tab ONLY (plus newline), like bash.

Reappraisal #17 lexer MED-2: is_whitespace() used to treat FF, VT, CR and
every Unicode space-category character (NBSP, EN SPACE, IDEOGRAPHIC SPACE,
...) as token separators, so a copy-pasted `echo a<NBSP>b` split into two
words where bash keeps one. These tests feed RAW BYTES through script
files and pin psh to bash byte-for-byte.

The one deliberate divergence stays deliberate: a CRLF script's
line-ending CR is stripped by the line-reading layer (FileInput), so psh
runs a DOS-line-ending script as if dos2unix'd where bash keeps the CR
bytes — see TestScriptFileCRLFLineEndings in test_r16_scripting.py.
"""

import subprocess
import sys

import pytest
from shell_oracle import resolve_bash

BASH = resolve_bash().path

NBSP = b'\xc2\xa0'          # U+00A0
EN_SPACE = b'\xe2\x80\x82'  # U+2002
IDEO_SPACE = b'\xe3\x80\x80'  # U+3000


def _run_both_bytes(tmp_path, script_bytes, name='sep.sh'):
    script = tmp_path / name
    script.write_bytes(script_bytes)
    psh = subprocess.run([sys.executable, '-m', 'psh', str(script)],
                         capture_output=True, timeout=15)
    bash = subprocess.run([BASH, str(script)], capture_output=True,
                          timeout=15)
    return psh, bash


@pytest.mark.parametrize("label,sep", [
    ("nbsp", NBSP),
    ("en_space", EN_SPACE),
    ("ideographic_space", IDEO_SPACE),
    ("form_feed", b'\x0c'),
    ("vertical_tab", b'\x0b'),
    ("carriage_return_mid_line", b'\r'),
])
def test_separator_byte_is_a_word_character(tmp_path, label, sep):
    # `echo a<SEP>b` is ONE word: bash prints a<SEP>b.
    psh, bash = _run_both_bytes(tmp_path, b'echo a' + sep + b'b\n')
    assert psh.stdout == bash.stdout == b'a' + sep + b'b\n'
    assert psh.returncode == bash.returncode == 0


def test_nbsp_after_command_name_is_part_of_the_name(tmp_path):
    # `echo<NBSP>hi` is one word -> command not found (bash agrees).
    psh, bash = _run_both_bytes(tmp_path, b'echo' + NBSP + b'hi\n')
    assert psh.stdout == bash.stdout == b''
    assert psh.returncode == bash.returncode == 127
    assert b'command not found' in psh.stderr
    assert b'command not found' in bash.stderr


def test_set_dash_dash_counts_nbsp_word_as_one(tmp_path):
    psh, bash = _run_both_bytes(
        tmp_path, b'set -- a' + NBSP + b'b\necho $#\n')
    assert psh.stdout == bash.stdout == b'1\n'


def test_space_and_tab_still_separate(tmp_path):
    psh, bash = _run_both_bytes(tmp_path, b'set -- a b\tc\necho $#\n')
    assert psh.stdout == bash.stdout == b'3\n'


def test_quoted_nbsp_unchanged(tmp_path):
    psh, bash = _run_both_bytes(
        tmp_path, b'echo "a' + NBSP + b'b"\n')
    assert psh.stdout == bash.stdout == b'a' + NBSP + b'b\n'
