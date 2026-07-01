"""Script file validation."""
import os
import stat
import sys

from .base import ScriptComponent


class ScriptValidator(ScriptComponent):
    """Validates script files before execution."""

    def validate_script_file(self, script_path: str) -> int:
        """
        Validate script file and return appropriate exit code.

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

        if self.is_binary_file(script_path):
            print(f"psh: {script_path}: cannot execute binary file", file=sys.stderr)
            return 126

        return 0

    def is_binary_file(self, file_path: str) -> bool:
        """Check if file is binary: a NUL byte before the first newline (bash's rule).

        Only regular files are sniffed.  Reading from a pipe, FIFO, or device
        here would CONSUME bytes the real open is about to read — `psh <(...)`,
        `psh /dev/stdin`, and `source /dev/stdin` would silently no-op (bash
        never re-reads its script fd, so it has no such hazard).  High bytes
        are NOT binary markers: a UTF-8 (or Latin-1) script must run.
        """
        try:
            if not stat.S_ISREG(os.stat(file_path).st_mode):
                return False
            with open(file_path, 'rb') as f:
                chunk = f.read(1024)
                # A /dev/fd path on macOS opens as a dup() SHARING the original
                # descriptor's offset; rewind so the sniff leaves no trace.
                f.seek(0)
            return b'\0' in chunk.split(b'\n', 1)[0]
        except OSError:
            return True  # If we can't read it, assume binary
