"""Shebang parsing and execution."""
import os
import subprocess
import sys
from typing import List, Optional, Tuple

from .base import ScriptComponent


class ShebangHandler(ScriptComponent):
    """Handles shebang parsing and execution."""

    def parse_shebang(self, script_path: str) -> Tuple[bool, Optional[str], List[str]]:
        """
        Parse shebang line from script file.

        Returns:
            tuple: (has_shebang, interpreter_path, interpreter_args)
        """
        try:
            with open(script_path, 'rb') as f:
                # Read first line, max 1024 bytes
                first_line = f.readline(1024)

                # Check for shebang
                if not first_line.startswith(b'#!'):
                    return (False, None, [])

                # Decode shebang line
                try:
                    shebang_line = first_line[2:].decode('utf-8', errors='ignore').strip()
                except UnicodeDecodeError:
                    return (False, None, [])

                if not shebang_line:
                    return (False, None, [])

                # Parse interpreter and arguments
                parts = shebang_line.split()
                if not parts:
                    return (False, None, [])

                interpreter = parts[0]
                interpreter_args = parts[1:] if len(parts) > 1 else []

                return (True, interpreter, interpreter_args)

        except (IOError, OSError):
            return (False, None, [])

    def should_execute_with_shebang(self, script_path: str) -> bool:
        """Determine if script should be executed with its shebang interpreter."""
        has_shebang, interpreter, interpreter_args = self.parse_shebang(script_path)

        if not has_shebang:
            return False

        # If interpreter is psh or our script name, use psh directly
        if interpreter.endswith('/psh') or interpreter == 'psh':
            return False

        # Handle /usr/bin/env pattern - check the actual interpreter
        if interpreter.endswith('/env') or interpreter == 'env':
            # Get the actual interpreter from interpreter_args
            if not interpreter_args:
                return False
            actual_interpreter = interpreter_args[0]
            if actual_interpreter.endswith('/psh') or actual_interpreter == 'psh':
                return False

        # Check if interpreter exists and is executable
        if interpreter.startswith('/'):
            # Absolute path
            return os.path.exists(interpreter) and os.access(interpreter, os.X_OK)
        else:
            # Search in PATH
            path_dirs = self.state.env.get('PATH', '').split(':')
            for path_dir in path_dirs:
                if path_dir:
                    full_path = os.path.join(path_dir, interpreter)
                    if os.path.exists(full_path) and os.access(full_path, os.X_OK):
                        return True
            return False

    def execute_with_shebang(self, script_path: str, script_args: List[str]) -> int:
        """Execute script using its shebang interpreter."""
        has_shebang, interpreter, interpreter_args = self.parse_shebang(script_path)

        if not has_shebang:
            return 1

        # Build command line for interpreter
        cmd_args = []

        # Add interpreter
        cmd_args.append(interpreter)

        # Add interpreter arguments
        cmd_args.extend(interpreter_args)

        # Add script path
        cmd_args.append(script_path)

        # Add script arguments
        if script_args:
            cmd_args.extend(script_args)

        try:
            # Execute the interpreter
            result = subprocess.run(cmd_args, env=self.state.env)
            return result.returncode
        except FileNotFoundError:
            print(f"psh: {interpreter}: No such file or directory", file=sys.stderr)
            return 127
        except PermissionError:
            print(f"psh: {interpreter}: Permission denied", file=sys.stderr)
            return 126
        except OSError as e:
            print(f"psh: {interpreter}: {e}", file=sys.stderr)
            return 1
