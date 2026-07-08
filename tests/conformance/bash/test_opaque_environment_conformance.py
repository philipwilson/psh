"""Conformance tests for opaque inherited environment entries (appraisal H3).

An inherited environment entry whose NAME is not a valid shell identifier
(``bad-name``, ``a.b``, ``1abc``, a non-ASCII name) is kept OPAQUE by bash: it
is passed through to child processes and is visible to ``printenv``, but it is
NOT materialised as a shell variable, so ``set`` / ``export -p`` / ``compgen -v``
do not list it. psh previously imported every inherited entry as an exported
shell variable, wrongly listing the invalid name.

Verified against bash 5.2.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest

# Inherited entries: two invalid names (kept opaque) plus one valid name
# (imported as a normal exported shell variable).
_OPAQUE_ENV = {"bad-name": "x", "a.b": "y", "GOODVAR": "ok"}


class TestOpaqueEnvironmentConformance(ConformanceTest):
    def test_invalid_name_is_visible_to_printenv(self):
        self.assert_identical_behavior("printenv bad-name", env=_OPAQUE_ENV)
        self.assert_identical_behavior("printenv a.b", env=_OPAQUE_ENV)

    def test_invalid_name_is_not_a_shell_variable(self):
        # export -p / compgen -v go to stdout, so the comparison is clean.
        self.assert_identical_behavior(
            "export -p | grep -c bad-name; echo rc=$?", env=_OPAQUE_ENV)
        self.assert_identical_behavior(
            "compgen -v 2>/dev/null | grep -c bad-name; echo rc=$?",
            env=_OPAQUE_ENV)

    def test_invalid_name_passes_through_to_external_child(self):
        self.assert_identical_behavior(
            "/usr/bin/env | grep '^bad-name='", env=_OPAQUE_ENV)

    def test_invalid_name_passes_through_to_subshell(self):
        self.assert_identical_behavior("(printenv bad-name)", env=_OPAQUE_ENV)

    def test_invalid_name_passes_through_to_command_substitution(self):
        self.assert_identical_behavior(
            'echo "[$(printenv bad-name)]"', env=_OPAQUE_ENV)

    def test_valid_name_is_imported_as_shell_variable(self):
        self.assert_identical_behavior("declare -p GOODVAR", env=_OPAQUE_ENV)
        self.assert_identical_behavior('echo "<$GOODVAR>"', env=_OPAQUE_ENV)
