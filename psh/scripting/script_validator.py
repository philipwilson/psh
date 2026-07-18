"""Script file validation."""
import os
import stat
import sys

from .base import ScriptComponent
from .program_source import BINARY_SNIFF_WINDOW, looks_binary_sample


class ScriptValidator(ScriptComponent):
    """Validates script files before execution."""

    def validate_script_file(self, script_path: str,
                             binary_sniff: bool = True) -> int:
        """
        Validate script file and return appropriate exit code.

        ``binary_sniff`` selects the script-INVOCATION channel's content
        sniff (bash ``check_binary_file``).  The ``source`` builtin passes
        False: bash 5.2 never content-sniffs a sourced file — its binary
        refusal is the sourced-program service's >256-NUL rule
        (psh/scripting/program_source.py).

        Returns:
            0 if file is valid
            126 if permission denied or binary file
            127 if file not found
        """
        if not os.path.exists(script_path):
            print(f"psh: {script_path}: No such file or directory", file=sys.stderr)
            return 127

        if os.path.isdir(script_path):
            print(f"psh: {script_path}: Is a directory", file=sys.stderr)
            return 126

        if not os.access(script_path, os.R_OK):
            print(f"psh: {script_path}: Permission denied", file=sys.stderr)
            return 126

        if binary_sniff and self.is_binary_file(script_path):
            print(f"psh: {script_path}: cannot execute binary file", file=sys.stderr)
            return 126

        return 0

    def is_binary_file(self, file_path: str) -> bool:
        """Bash's script-invocation binary sniff (``check_binary_file``).

        The rule set lives in ``program_source.looks_binary_sample`` (ELF
        magic; ``#!`` first line makes a NUL anywhere in the sample binary;
        otherwise a NUL before the first newline) over bash's exact 80-byte
        window — a NUL at byte 90 does NOT refuse the file (probe A11).

        Only regular files are sniffed.  Reading from a pipe, FIFO, or device
        here would CONSUME bytes the real open is about to read — `psh <(...)`
        and `psh /dev/stdin` would silently no-op (bash
        never re-reads its script fd, so it has no such hazard).  High bytes
        are NOT binary markers: a UTF-8 (or Latin-1) script must run.
        """
        try:
            if not stat.S_ISREG(os.stat(file_path).st_mode):
                return False
            with open(file_path, 'rb') as f:
                sample = f.read(BINARY_SNIFF_WINDOW)
                # A /dev/fd path on macOS opens as a dup() SHARING the original
                # descriptor's offset; rewind so the sniff leaves no trace.
                f.seek(0)
            return looks_binary_sample(sample)
        except OSError:
            return True  # If we can't read it, assume binary
