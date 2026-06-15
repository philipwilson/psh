r"""Conformance tests for the ``\$`` escape in double-quoted string contexts.

These contexts route through ``VariableExpander.expand_string_variables`` /
``_process_double_quote_escape`` rather than the command-argument Word path:
here-strings/documents, redirect targets, ``[[ ]]`` operands, and ``${...}``
operands. In every double-quoted context bash drops the backslash on ``\$``
unconditionally (the result is a literal ``$``; the following text is NOT
re-scanned as an expansion). Regression pin for reappraisal #9 bug H1, where
psh kept the backslash when ``\$`` was not immediately followed by a
variable-name character (e.g. ``"a\$ b"`` -> psh ``a\$ b`` vs bash ``a$ b``).
"""

import os
import sys

# Add parent directory to path for framework import
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestEscapedDollarStringContextConformance(ConformanceTest):
    r"""``\$`` always drops its backslash in double-quoted string contexts."""

    # --- here-strings ---------------------------------------------------

    def test_herestring_escaped_dollar_space(self):
        r"""``"a\$ b"`` -> ``a$ b`` ($ not followed by a name char)."""
        self.assert_identical_behavior(r'cat <<< "a\$ b"')

    def test_herestring_escaped_dollar_dot(self):
        r"""``"a\$.b"`` -> ``a$.b``."""
        self.assert_identical_behavior(r'cat <<< "a\$.b"')

    def test_herestring_escaped_dollar_eos(self):
        r"""``"a\$"`` -> ``a$`` ($ at end of string)."""
        self.assert_identical_behavior(r'cat <<< "a\$"')

    def test_herestring_escaped_dollar_shields_name(self):
        r"""``"a\$VAR"`` -> literal ``a$VAR`` (the \$ shields the expansion)."""
        self.assert_identical_behavior(r'VAR=x; cat <<< "a\$VAR"')

    def test_herestring_double_backslash_dollar(self):
        r"""``"a\\\$ b"`` -> literal backslash then literal ``$``."""
        self.assert_identical_behavior(r'cat <<< "a\\\$ b"')

    def test_herestring_other_escapes_literal(self):
        r"""C-style ``\n``/``\t`` stay literal in double quotes."""
        self.assert_identical_behavior(r'cat <<< "a\nb\tc"')

    def test_herestring_escaped_backtick(self):
        r"""``\``` drops its backslash."""
        self.assert_identical_behavior(r'cat <<< "a\`b"')

    # --- parameter-expansion operands -----------------------------------

    def test_param_default_escaped_dollar_space(self):
        r"""``${v:-a\$ b}`` default value drops the backslash on \$."""
        self.assert_identical_behavior(r'unset v; echo "${v:-a\$ b}"')

    # --- redirect targets -----------------------------------------------

    def test_redirect_target_escaped_dollar(self):
        r"""A ``\$`` in a redirect target is a literal ``$`` in the path."""
        self.assert_identical_behavior(
            r'f="a\$b"; echo hi > "$f"; ls a*; rm -f "$f"')
