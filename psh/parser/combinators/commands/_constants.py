"""Shared module constants for the command-parser mixins.

These live in their own module (rather than ``__init__.py``) so the mixin
modules can import them without creating a circular import back through the
package that composes them.
"""

import re

# Pre-compiled regex for fd duplication detection (e.g. ">&2", "2>&1", ">&-")
_FD_DUP_RE = re.compile(r'^(\d*)([><])&(-|\d+)$')

# Token types that should be treated as word-like for composite merging
_WORD_LIKE_TYPES = frozenset({
    'WORD', 'STRING', 'VARIABLE', 'PARAM_EXPANSION', 'COMMAND_SUB',
    'COMMAND_SUB_BACKTICK', 'ARITH_EXPANSION', 'PROCESS_SUB_IN', 'PROCESS_SUB_OUT',
})
