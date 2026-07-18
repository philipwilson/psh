"""Unit pins for the ProgramSource normalization boundary (campaign F3).

The behavioral truth is pinned bash-compared in
tests/system/source_service/; these pins lock the REPRESENTATION: the exact
filter algorithms (extracted from bash 5.2 builtins/evalfile.c and
general.c), the per-channel policy table, and the frozen dataclass contract.
"""
import dataclasses

import pytest

from psh.scripting.input_sources import FileInput, StdinInput, StringInput
from psh.scripting.program_source import (
    BINARY_SNIFF_WINDOW,
    BinaryProgramText,
    ProgramSource,
    SourceChannel,
    SourceRequest,
    evalfile_nul_filter,
    looks_binary_sample,
    strip_nul_stream,
)


class TestStreamFilter:
    """Stream channels (script file, stdin) delete every NUL."""

    def test_deletes_all_nuls(self):
        assert strip_nul_stream("e\x00cho\x00\x00 hi") == "echo hi"

    def test_identity_without_nuls(self):
        assert strip_nul_stream("echo hi\n") == "echo hi\n"


class TestEvalfileFilter:
    """bash 5.2's _evalfile loop: delete a NUL, skip the shifted-in byte.

    The second NUL of an adjacent pair therefore SURVIVES unexamined, and
    parse_and_execute's C-string read truncates there — reproduced by
    cutting at the first retained NUL.
    """

    def test_isolated_nul_deleted(self):
        assert evalfile_nul_filter("echo A\x00B\n") == "echo AB\n"

    def test_two_separated_nuls_deleted(self):
        assert evalfile_nul_filter("A\x00B\x00C") == "ABC"

    def test_adjacent_pair_truncates_rest(self):
        assert evalfile_nul_filter("echo A\x00\x00B\necho C\n") == "echo A"

    def test_triple_run_truncates_rest(self):
        assert evalfile_nul_filter("echo A\x00\x00\x00B\necho C\n") == "echo A"

    def test_leading_pair_truncates_to_empty(self):
        assert evalfile_nul_filter("\x00\x00echo hi\n") == ""

    def test_leading_single_nul_deleted(self):
        assert evalfile_nul_filter("\x00echo hi\n") == "echo hi\n"

    def test_limit_counts_deleted_nuls_only(self):
        # 256 deleted NULs are allowed; the 257th refuses. A run of 2k
        # adjacent NULs deletes only k (the survivors are skipped).
        ok = "x" + "\x00y" * 256
        assert evalfile_nul_filter(ok, limited=True) == "x" + "y" * 256

        bad = "x" + "\x00y" * 257
        with pytest.raises(BinaryProgramText):
            evalfile_nul_filter(bad, limited=True, path="f")

    def test_unlimited_channel_never_refuses(self):
        text = "\x00y" * 300
        assert evalfile_nul_filter(text) == "y" * 300


class TestBinarySniff:
    """bash 5.2 check_binary_file, applied only to the script channel."""

    def test_elf_magic_is_binary_even_with_newline(self):
        assert looks_binary_sample(b"\x7fELF\necho hi\n")

    def test_shebang_widens_to_whole_sample(self):
        assert looks_binary_sample(b"#!/bin/sh\necho a\x00b\n")
        assert not looks_binary_sample(b"#!/bin/sh\necho ok\n")

    def test_nul_before_first_newline(self):
        assert looks_binary_sample(b"e\x00cho\necho ok\n")
        assert not looks_binary_sample(b"echo ok\ne\x00cho\n")

    def test_empty_sample_not_binary(self):
        assert not looks_binary_sample(b"")

    def test_window_is_80_bytes(self):
        # The caller reads only BINARY_SNIFF_WINDOW bytes, so a NUL past
        # byte 80 never reaches the sniff (probe A11-window).
        assert BINARY_SNIFF_WINDOW == 80


class TestChannelPolicyTable:
    """Per-channel flags come from ProgramSource, not call-site pokes."""

    def _flags(self, source):
        return (source.history_expansion_eligible,
                source.eof_drops_dangling_continuation,
                source.stops_on_function_return,
                source.posix_syntax_exit)

    def test_script_file_channel(self, tmp_path):
        p = tmp_path / "s.sh"
        p.write_text("echo hi\n")
        src = ProgramSource.script_file(str(p)).make_input_source()
        assert isinstance(src, FileInput)
        assert self._flags(src) == (True, True, False, True)

    def test_stdin_channel(self):
        src = ProgramSource.stdin_script().make_input_source()
        assert isinstance(src, StdinInput)
        assert self._flags(src) == (True, True, False, True)

    def test_command_string_channel(self):
        src = ProgramSource.command_string("echo hi").make_input_source()
        assert isinstance(src, StringInput)
        # -c strings never bang-expand (bash -ic 'echo !!' — F1 probe B8).
        assert self._flags(src) == (False, False, False, True)

    def test_command_text_channel_flags(self):
        src = ProgramSource.command_text(
            "echo hi", line_oriented=True,
            posix_syntax_exit=False).make_input_source()
        assert isinstance(src, StringInput)
        assert self._flags(src) == (True, False, False, False)

    def test_sourced_file_channel(self, tmp_path):
        p = tmp_path / "f"
        p.write_text("echo hi\n")
        src = ProgramSource.sourced_file(str(p)).make_input_source()
        assert isinstance(src, FileInput)
        # Sourced files: keep dangling continuation (string input), never
        # bang-expand, and `return` stops the file.
        assert self._flags(src) == (False, False, True, True)

    def test_rc_file_channel(self, tmp_path):
        p = tmp_path / "rc"
        p.write_text("echo hi\n")
        src = ProgramSource.rc_file(str(p)).make_input_source()
        assert isinstance(src, FileInput)
        assert self._flags(src) == (False, False, True, True)

    def test_every_channel_has_a_policy_row(self):
        from psh.scripting.program_source import _CHANNEL_POLICY
        assert set(_CHANNEL_POLICY) == set(SourceChannel)


class TestNulPolicyThroughInputSources:
    def test_script_file_stream_delete(self, tmp_path):
        p = tmp_path / "s.sh"
        p.write_bytes(b"echo A\x00\x00B\necho C\n")
        with ProgramSource.script_file(str(p)).make_input_source() as src:
            assert src.lines[:2] == ["echo AB", "echo C"]

    def test_sourced_file_pair_truncates(self, tmp_path):
        p = tmp_path / "f"
        p.write_bytes(b"echo A\x00\x00B\necho C\n")
        with ProgramSource.sourced_file(str(p)).make_input_source() as src:
            assert src.lines == ["echo A"]

    def test_sourced_file_limit_raises(self, tmp_path):
        p = tmp_path / "f.bin"
        p.write_bytes(b"x" + b"\x00y" * 300)
        with pytest.raises(BinaryProgramText):
            with ProgramSource.sourced_file(str(p)).make_input_source():
                pass

    def test_rc_file_no_limit(self, tmp_path):
        p = tmp_path / "rc"
        p.write_bytes(b"\x00e" * 300 + b"cho hi\n")
        with ProgramSource.rc_file(str(p)).make_input_source() as src:
            assert src.lines[0].endswith("cho hi")

    def test_stdin_records_strip_nuls(self, tmp_path):
        import os
        r, w = os.pipe()
        try:
            os.write(w, b"echo A\x00\x00B\necho C\n")
            os.close(w)
            src = ProgramSource.stdin_script(fd=r).make_input_source()
            assert src.read_line() == "echo AB"
            assert src.read_line() == "echo C"
        finally:
            os.close(r)

    def test_read_text_matches_execution_view(self, tmp_path):
        p = tmp_path / "s.sh"
        p.write_bytes(b"echo o\x00k\r\necho two\n")
        # Same decode, CRLF normalization, and stream NUL policy as the
        # execution path.
        assert ProgramSource.script_file(str(p)).read_text() == \
            "echo ok\necho two\n"


class TestRepresentationContract:
    def test_program_source_is_frozen(self):
        ps = ProgramSource.command_string("echo hi")
        with pytest.raises(dataclasses.FrozenInstanceError):
            ps.name = "other"  # type: ignore[misc]

    def test_source_request_is_frozen(self):
        req = SourceRequest(path="/tmp/f")
        with pytest.raises(dataclasses.FrozenInstanceError):
            req.path = "/tmp/g"  # type: ignore[misc]

    def test_source_request_defaults(self):
        req = SourceRequest(path="/tmp/f")
        assert req.kind is SourceChannel.SOURCED_FILE
        assert req.args is None
