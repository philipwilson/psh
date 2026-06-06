"""Script file validation."""
import os
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
        """Check if file is binary by looking for null bytes and other indicators."""
        try:
            with open(file_path, 'rb') as f:
                # Read first 1024 bytes for analysis
                chunk = f.read(1024)

                if not chunk:
                    return False  # Empty file is not binary

                # Check for null bytes (strong indicator of binary)
                if b'\0' in chunk:
                    return True

                # Check for very high ratio of non-printable characters
                printable_chars = 0
                for byte in chunk:
                    # Count ASCII printable chars (32-126) plus common whitespace
                    if 32 <= byte <= 126 or byte in (9, 10, 13):  # tab, newline, carriage return
                        printable_chars += 1

                # If less than 70% printable characters, consider it binary
                if chunk and (printable_chars / len(chunk)) < 0.70:
                    return True

                # Check for common binary file signatures
                binary_signatures = [
                    b'\x7fELF',      # ELF executable
                    b'MZ',           # DOS/Windows executable
                    b'\xca\xfe\xba\xbe',  # Java class file
                    b'\x89PNG',      # PNG image
                    b'\xff\xd8\xff', # JPEG image
                    b'GIF8',         # GIF image
                    b'%PDF',         # PDF file
                ]

                for sig in binary_signatures:
                    if chunk.startswith(sig):
                        return True

                return False

        except OSError:
            return True  # If we can't read it, assume binary
