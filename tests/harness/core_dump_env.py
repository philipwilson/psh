"""Does a fatal signal produce a core dump in THIS environment?

A shell that reports a signal death appends bash's ``" (core dumped)"`` suffix
exactly when the kernel set ``WCOREDUMP`` in the wait status — psh does this in
``psh/executor/job_control.py``. Whether the kernel sets it is a property of the
host, not of the shell, so a test that pins the diagnostic text has to ask the
host rather than assume. Two things decide it:

* ``RLIMIT_CORE``: soft 0 means no dump. The default is 0 on macOS and
  UNLIMITED on Linux, which is why these rows passed locally and failed on the
  Linux nightly.
* ``/proc/sys/kernel/core_pattern``: when it names a PIPE (``|/usr/share/…``),
  the kernel IGNORES ``RLIMIT_CORE`` and dumps anyway — it forces the limit to
  infinity for piped dumps. Hosted CI runners use a piped pattern (apport /
  systemd-coredump), so lowering the limit there does NOT suppress the suffix.

Verified directly, same kernel, only the pattern changed, with soft limit 0:
``core`` (file) -> ``WCOREDUMP False``; ``|/bin/cat`` (pipe) -> ``WCOREDUMP
True``.
"""

import resource

_CORE_PATTERN = "/proc/sys/kernel/core_pattern"


def core_dumps_expected() -> bool:
    """True when a core-dumping signal here will set ``WCOREDUMP``."""
    try:
        with open(_CORE_PATTERN, encoding="utf-8") as fh:
            pattern = fh.read().strip()
    except OSError:
        pattern = ""          # no procfs (macOS): the limit alone decides
    if pattern.startswith("|"):
        return True           # piped dumps ignore RLIMIT_CORE
    return resource.getrlimit(resource.RLIMIT_CORE)[0] != 0


def signal_death_text(description: str) -> str:
    """``description`` plus the core-dumped suffix this host would produce."""
    return description + (" (core dumped)" if core_dumps_expected() else "")
