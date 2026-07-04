"""File test utilities for shell operations.

Single source of truth for the ``-nt``/``-ot``/``-ef`` file comparisons used
by BOTH the ``test``/``[`` builtin (``builtins/test_command.py``) and the
``[[ ]]`` evaluator (``executor/enhanced_test_evaluator.py``) — so the two
forms can never diverge.
"""
import os
from typing import Optional


def _mtime(path: str) -> Optional[float]:
    """Modification time of ``path``, or None if it cannot be stat-ed."""
    try:
        return os.stat(path).st_mtime
    except OSError:
        return None


def file_newer_than(file1: str, file2: str) -> bool:
    """True iff file1 is newer than file2 (bash ``-nt``).

    bash's rule is asymmetric on existence: true when file1's mtime is greater
    than file2's, OR when file1 exists and file2 does NOT. A missing file1 is
    never newer, and both-missing (or equal mtimes) is false.
    """
    m1 = _mtime(file1)
    if m1 is None:
        return False
    m2 = _mtime(file2)
    if m2 is None:
        return True
    return m1 > m2


def file_older_than(file1: str, file2: str) -> bool:
    """True iff file1 is older than file2 (bash ``-ot``).

    Symmetric to :func:`file_newer_than`: true when file1's mtime is less than
    file2's, OR when file2 exists and file1 does NOT. A missing file2 means
    file1 is never older, and both-missing (or equal mtimes) is false.
    """
    m2 = _mtime(file2)
    if m2 is None:
        return False
    m1 = _mtime(file1)
    if m1 is None:
        return True
    return m1 < m2


def files_same(file1: str, file2: str) -> bool:
    """Check if two files are the same (same device and inode)."""
    try:
        stat1 = os.stat(file1)
        stat2 = os.stat(file2)
        return (stat1.st_dev == stat2.st_dev and
                stat1.st_ino == stat2.st_ino)
    except OSError:
        return False
