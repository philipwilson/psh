"""History files round-trip arbitrary bytes via UTF-8 + surrogateescape (I4).

Reappraisal-20 finding 20: the five history-file paths (startup load, exit save,
`-w` rewrite, `-a` append, `-r`/`-n` read) used the platform-default text
encoding, so a history file holding a malformed byte raised UnicodeDecodeError
(RED on base) and a surrogate-escaped in-memory entry could not be written. All
five now use `encoding='utf-8', errors='surrogateescape'` (I1 byte doctrine), so
a lone `\\xff` round-trips as `\\udcff` and back.
"""

import pytest

from psh.shell import Shell

RAW = b"echo caf\xc3\xa9 \xff done\n"          # valid é (2 bytes) + lone \xff
DECODED = "echo café \udcff done"              # surrogate for the \xff
REENCODED = b"echo caf\xc3\xa9 \xff done"      # round-trips back to the bytes


@pytest.fixture
def hist(tmp_path):
    """A HistoryManager whose default history file lives under tmp_path."""
    sh = Shell(norc=True)
    sh.state.history_file = str(tmp_path / "psh_history")
    mgr = sh.interactive_manager.history_manager
    return sh, mgr, tmp_path


def _read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def _write_bytes(path, data):
    with open(path, "wb") as f:
        f.write(data)


def test_load_roundtrips_malformed_bytes(hist):
    sh, mgr, _ = hist
    _write_bytes(sh.state.history_file, RAW)
    mgr.load_from_file()  # RED on base: UnicodeDecodeError here
    assert sh.state.history[-1] == DECODED
    assert sh.state.history[-1].encode("utf-8", "surrogateescape") == REENCODED


def test_save_roundtrips_malformed_bytes(hist):
    sh, mgr, _ = hist
    sh.state.history.append(DECODED)
    mgr.save_to_file()  # RED on base: cannot encode the surrogate under default
    assert REENCODED in _read_bytes(sh.state.history_file)


def test_write_history_w_roundtrips(hist):
    sh, mgr, _ = hist
    sh.state.history.append(DECODED)
    assert mgr.write_history() is True
    assert REENCODED in _read_bytes(sh.state.history_file)


def test_append_history_a_roundtrips(hist):
    sh, mgr, _ = hist
    sh.state.history.append(DECODED)
    assert mgr.append_history() is True
    assert REENCODED in _read_bytes(sh.state.history_file)


def test_read_history_r_roundtrips(hist):
    sh, mgr, tmp_path = hist
    other = tmp_path / "other_hist"
    _write_bytes(str(other), RAW)
    assert mgr.read_history(str(other)) is True  # RED on base: UnicodeDecodeError
    assert sh.state.history[-1] == DECODED


def test_read_new_history_n_roundtrips(hist):
    sh, mgr, tmp_path = hist
    other = tmp_path / "other_hist_n"
    _write_bytes(str(other), RAW)
    assert mgr.read_new_history(str(other)) is True
    assert sh.state.history[-1] == DECODED


def test_save_then_load_is_a_faithful_cycle(hist):
    sh, mgr, _ = hist
    sh.state.history.append(DECODED)
    mgr.save_to_file()
    # Fresh session loading the same file must recover the identical entry.
    sh2 = Shell(norc=True)
    sh2.state.history_file = sh.state.history_file
    sh2.interactive_manager.history_manager.load_from_file()
    assert sh2.state.history[-1] == DECODED


def test_valid_multibyte_is_one_char(hist):
    sh, mgr, _ = hist
    _write_bytes(sh.state.history_file, "echo café\n".encode("utf-8"))
    mgr.load_from_file()
    assert sh.state.history[-1] == "echo café"  # é is ONE char, not surrogates
