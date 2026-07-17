"""RC file loading for interactive shell startup."""
import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..shell import Shell


def load_rc_file(shell: 'Shell') -> None:
    """Load ~/.pshrc or alternative RC file if it exists."""
    # Determine which RC file to load
    if shell.state.rcfile:
        rc_file = os.path.expanduser(shell.state.rcfile)
    else:
        rc_file = os.path.expanduser("~/.pshrc")

    # Check if file exists and is readable
    if os.path.isfile(rc_file) and os.access(rc_file, os.R_OK):
        # Check security before loading
        if not is_safe_rc_file(rc_file):
            print(f"psh: warning: {rc_file} has unsafe permissions, skipping", file=sys.stderr)
            return

        try:
            # Source the file without adding to history.
            # (We deliberately do NOT touch $0: an rc file runs in the shell's
            # own context. A previous attempt assigned shell.variables['0'],
            # which is a no-op — state.variables is a snapshot dict — so it
            # never had any effect.)
            from ..scripting.input_sources import FileInput
            with FileInput(rc_file) as input_source:
                # bash never bang-expands rc-file lines (probe-verified:
                # `echo !!` in an --rcfile stays literal under -i -s).
                input_source.history_expansion_eligible = False
                shell.script_manager.execute_from_source(input_source, add_to_history=False)

        except Exception as e:
            # Print warning but continue shell startup
            print(f"psh: warning: error loading {rc_file}: {e}", file=sys.stderr)


def is_safe_rc_file(filepath: str) -> bool:
    """Check if RC file has safe permissions."""
    try:
        stat_info = os.stat(filepath)
        # Check if file is owned by user or root
        if stat_info.st_uid not in (os.getuid(), 0):
            return False
        # Check if file is world-writable
        if stat_info.st_mode & 0o002:
            return False
        return True
    except OSError:
        return False
