"""Conformance tests: the ``nocasematch`` shopt option.

bash's ``nocasematch`` shell option makes pattern matching in ``[[ ]]``
(``==``/``!=`` glob patterns and ``=~`` regex) and in ``case`` statements
case-insensitive. These tests pin identical bash behavior with the option
both set and unset, plus the ``shopt`` query-form exit code (0 when the
option is set, 1 when unset — the exit code reflects the option's state).

psh formerly rejected ``shopt -s nocasematch`` with "invalid shell option
name", and its ``shopt OPTION`` query form always exited 0. Both are fixed
(reappraisal #6 bug L6).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from conformance_framework import ConformanceTest


class TestNocasematchDoubleBracket(ConformanceTest):
    """nocasematch in ``[[ ]]`` ==/!=/=~."""

    def test_eq_case_insensitive_when_set(self):
        self.assert_identical_behavior(
            'shopt -s nocasematch; [[ ABC == abc ]] && echo m || echo no')

    def test_eq_case_sensitive_when_unset(self):
        # Default: case-sensitive (no match).
        self.assert_identical_behavior(
            '[[ ABC == abc ]] && echo m || echo no')

    def test_ne_case_insensitive_when_set(self):
        self.assert_identical_behavior(
            'shopt -s nocasematch; [[ ABC != abc ]] && echo ne || echo eq')

    def test_glob_pattern_case_insensitive_when_set(self):
        self.assert_identical_behavior(
            'shopt -s nocasematch; [[ HELLO == h* ]] && echo m || echo no')

    def test_regex_case_insensitive_when_set(self):
        self.assert_identical_behavior(
            'shopt -s nocasematch; [[ ABC =~ ^abc$ ]] && echo m || echo no')

    def test_regex_case_sensitive_when_unset(self):
        self.assert_identical_behavior(
            '[[ ABC =~ ^abc$ ]] && echo m || echo no')

    def test_unset_after_set_restores_case_sensitivity(self):
        self.assert_identical_behavior(
            'shopt -s nocasematch; shopt -u nocasematch; '
            '[[ ABC == abc ]] && echo m || echo no')


class TestNocasematchCase(ConformanceTest):
    """nocasematch in ``case`` statements."""

    def test_case_insensitive_when_set(self):
        self.assert_identical_behavior(
            'shopt -s nocasematch; case ABC in abc) echo m;; *) echo no;; esac')

    def test_case_sensitive_when_unset(self):
        self.assert_identical_behavior(
            'case ABC in abc) echo m;; *) echo no;; esac')

    def test_case_glob_pattern_when_set(self):
        self.assert_identical_behavior(
            'shopt -s nocasematch; case HELLO in h*) echo m;; *) echo no;; esac')


class TestShoptQueryExitCode(ConformanceTest):
    """``shopt OPTION`` (query form) exit code reflects the option's state."""

    def test_query_unset_exits_1(self):
        self.assert_identical_behavior('shopt nocasematch; echo $?')

    def test_query_set_exits_0(self):
        self.assert_identical_behavior(
            'shopt -s nocasematch; shopt nocasematch; echo $?')

    def test_query_after_unset_exits_1(self):
        self.assert_identical_behavior(
            'shopt -s nocasematch; shopt -u nocasematch; shopt nocasematch; echo $?')

    def test_print_form_set_exits_0(self):
        self.assert_identical_behavior(
            'shopt -s nocasematch; shopt -p nocasematch; echo $?')
