"""
Conformance tests: `set -e` and the brace-group errexit exemption.

A brace group `{ ...; }` is TRANSPARENT to errexit: the exemption of a
non-final `&&`/`||` member inside it carries out, so `set -e; { false && true; }`
does NOT abort (bash). psh re-marked the whole brace group eligible, so it
aborted (reappraisal #13 MED). Subshells `( )` and functions are NOT transparent
— they remain a fresh errexit context where only the final status counts.

Verified against bash 5.2.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestErrexitBraceGroupTransparent(ConformanceTest):
    def test_brace_and_exempt_does_not_abort(self):
        self.assert_identical_behavior('set -e; { false && true; }; echo reached')

    def test_brace_or_does_not_abort(self):
        self.assert_identical_behavior('set -e; { false || true; }; echo reached')

    def test_nested_brace_exempt(self):
        self.assert_identical_behavior(
            'set -e; { { false && true; }; }; echo reached')

    def test_brace_with_leading_command(self):
        self.assert_identical_behavior(
            'set -e; { echo a; false && true; }; echo reached')


class TestErrexitBraceGroupStillAborts(ConformanceTest):
    """A brace group whose last command IS errexit-eligible still aborts."""

    def test_brace_final_failure_aborts(self):
        self.assert_identical_behavior('set -e; { true && false; }; echo reached')

    def test_brace_plain_false_aborts(self):
        self.assert_identical_behavior('set -e; { false; }; echo reached')

    def test_brace_last_cmd_fails_aborts(self):
        self.assert_identical_behavior('set -e; { echo a; false; }; echo reached')

    def test_real_failure_after_exempt_brace(self):
        self.assert_identical_behavior(
            'set -e; { false && true; }; false; echo reached')


class TestErrexitOtherCompoundsUnchanged(ConformanceTest):
    """Subshells and functions are NOT transparent (only final status counts)."""

    def test_subshell_aborts(self):
        self.assert_identical_behavior('set -e; ( false && true ); echo reached')

    def test_function_aborts(self):
        self.assert_identical_behavior(
            'set -e; f(){ false && true; }; f; echo reached')


class TestErrexitBraceErrTrap(ConformanceTest):
    """ERR trap fires under exactly the errexit conditions for a brace group."""

    def test_err_trap_exempt(self):
        self.assert_identical_behavior(
            'set -e; trap "echo ERR" ERR; { false && true; }; echo reached')

    def test_err_trap_fires_on_final_failure(self):
        self.assert_identical_behavior(
            'set -e; trap "echo ERR" ERR; { true && false; }; echo reached')
