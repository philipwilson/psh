"""Input source abstraction for psh.

This module provides different input sources for the shell:
- FileInput: Read commands from script files
- StringInput: Read commands from strings (for -c option)
- InteractiveInput: Read commands interactively (for REPL)
"""

from abc import ABC, abstractmethod
from typing import Optional


class InputSource(ABC):
    """Abstract base class for shell input sources."""

    @abstractmethod
    def read_line(self) -> Optional[str]:
        """Read the next line from the input source.

        Returns:
            The next line as a string, or None on EOF.
        """
        pass

    @abstractmethod
    def is_interactive(self) -> bool:
        """Return True if this is an interactive input source."""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Return the name of this input source for error messages."""
        pass

    def get_line_number(self) -> int:
        """Return the current line number (1-based). Override if tracking line numbers."""
        return 0

    def get_location(self) -> str:
        """Return a location string for error messages."""
        line_num = self.get_line_number()
        if line_num > 0:
            return f"{self.get_name()}:{line_num}"
        return self.get_name()


class FileInput(InputSource):
    """Input source for reading commands from script files."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.file = None
        self.line_number = 0
        self.processed_lines = []
        self.current_line = 0
        self.preprocessed = False

    def __enter__(self):
        self.file = open(self.file_path, 'r', encoding='utf-8')
        return self

    def __exit__(self, exc_type, _exc_val, _exc_tb):
        if self.file:
            self.file.close()

    def _preprocess_file(self):
        """Read entire file and preprocess line continuations."""
        if self.preprocessed:
            return

        # Read entire file content
        content = self.file.read()

        # Process line continuations
        from .input_preprocessing import process_line_continuations
        processed_content = process_line_continuations(content)

        # Split back into lines
        self.processed_lines = processed_content.split('\n')
        self.preprocessed = True

    def read_line(self) -> Optional[str]:
        """Read the next line from the preprocessed file."""
        if not self.preprocessed:
            self._preprocess_file()

        if self.current_line < len(self.processed_lines):
            line = self.processed_lines[self.current_line]
            self.current_line += 1
            self.line_number += 1
            return line
        return None

    def is_interactive(self) -> bool:
        return False

    def get_name(self) -> str:
        return self.file_path

    def get_line_number(self) -> int:
        return self.line_number


class StringInput(InputSource):
    """Input source for reading commands from a string."""

    def __init__(self, command: str, name: str = "<command>"):
        # Process line continuations before storing
        from .input_preprocessing import process_line_continuations
        processed_command = process_line_continuations(command)

        # For run_command (single-line commands), return as one chunk
        # For -c and scripts, split on newlines for line-by-line processing
        # (needed for shopt options that affect tokenization of subsequent lines)
        if name == "<command>":
            # Single command mode - return the whole command as one line
            self.lines = [processed_command] if processed_command else []
        else:
            # Script mode and -c mode - split into lines for multi-line processing
            self.lines = processed_command.split('\n')

        self.current = 0
        self.name = name
        self.line_number = 0

    def read_line(self) -> Optional[str]:
        """Read the next line from the string."""
        if self.current < len(self.lines):
            line = self.lines[self.current]
            self.current += 1
            self.line_number += 1
            return line
        return None

    def is_interactive(self) -> bool:
        return False

    def get_name(self) -> str:
        return self.name

    def get_line_number(self) -> int:
        return self.line_number


class InteractiveInput(InputSource):
    """Input source for interactive shell sessions."""

    def __init__(self, line_editor, prompt_func):
        self.line_editor = line_editor
        self.prompt_func = prompt_func

    def read_line(self) -> Optional[str]:
        """Read the next line interactively."""
        try:
            prompt = self.prompt_func()
            return self.line_editor.read_line(prompt)
        except (EOFError, KeyboardInterrupt):
            return None

    def is_interactive(self) -> bool:
        return True

    def get_name(self) -> str:
        return "<stdin>"
