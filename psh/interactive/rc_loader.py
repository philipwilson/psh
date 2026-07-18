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
            # The rc runs through THE sourced-program service — rc is not a
            # second source dialect (campaign F3, continuation medium 2): it
            # gains source depth (so `return 7` cleanly ends the rc with no
            # diagnostic and startup continues, like bash), the evalfile NUL
            # policy, and restoration on exception exits. Per bash, the rc
            # channel differs from `source` in exactly three ways, all owned
            # by the service's channel table: no >256-NUL binary refusal, no
            # RETURN-trap firing at rc end (probes B3/B6), and a `return N`
            # status that is DISCARDED rather than becoming $? (probes
            # B12/B13 — the return value below is deliberately ignored).
            # Like `source`, rc lines are never bang-expanded and never
            # recorded in history, and $0 is untouched (an rc file runs in
            # the shell's own context).
            from ..scripting.program_source import (
                SourceChannel,
                SourceRequest,
                execute_sourced_file,
            )
            execute_sourced_file(
                shell, SourceRequest(path=rc_file,
                                     kind=SourceChannel.RC_FILE))

        except Exception as e:
            # Print warning but continue shell startup (an `exit` in the rc
            # is a SystemExit — BaseException — and still exits the shell).
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
