"""Conformance tests for the ``hash`` builtin (bash 5.2, probed 2026-06-13).

This file holds the flipped absent-feature ledger entry (`hash ls; hash`
— see test_absent_features.py) plus the full probe battery: listing
format, lookups, hit counts, PATH invalidation, ``set +h``, and the
stale-remembered-path semantics (default blind exec vs ``shopt -s
checkhash`` re-search).

Comparison caveats baked into the commands below:

- error-message PREFIXES differ (``psh:`` vs ``bash: line 1:``), so
  commands that provoke errors redirect stderr to /dev/null and compare
  ``$?`` instead;
- bash lists multi-entry tables in hash-bucket order while psh uses
  insertion order, so exact-stdout listing comparisons use single-entry
  tables (a deliberate cosmetic difference).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestHashBuiltin(ConformanceTest):
    """The hash builtin's own surface."""

    def test_hash_records_and_lists(self):
        """The flipped ledger entry: `hash ls; hash` prints the
        hits/command table identically (header, %4d column, path)."""
        self.assert_identical_behavior('hash ls; hash')

    def test_empty_table_message_on_stdout(self):
        self.assert_identical_behavior('hash; echo rc=$?')

    def test_not_found_name_status(self):
        self.assert_identical_behavior(
            'hash nosuchcmd_xyz 2>/dev/null; echo rc=$?')

    def test_builtin_name_skipped_silently(self):
        self.assert_identical_behavior('hash echo; echo rc=$?; hash')

    def test_function_name_skipped_silently(self):
        self.assert_identical_behavior('f() { :; }; hash f; echo rc=$?; hash')

    def test_slash_name_ignored(self):
        self.assert_identical_behavior('hash /bin/ls; echo rc=$?; hash')

    def test_dash_t_single_and_multiple(self):
        self.assert_identical_behavior('hash ls; hash -t ls')
        self.assert_identical_behavior('hash ls cat; hash -t ls cat')

    def test_dash_t_unhashed_is_not_found(self):
        self.assert_identical_behavior('hash -t ls 2>/dev/null; echo rc=$?')

    def test_dash_t_lookup_counts_as_hit(self):
        self.assert_identical_behavior('hash ls; hash -t ls; hash')

    def test_dash_l_reusable_format(self):
        self.assert_identical_behavior('hash ls; hash -l')
        self.assert_identical_behavior('hash -l; echo rc=$?')

    def test_dash_p_explicit_path(self):
        self.assert_identical_behavior(
            'hash -p /bin/echo myecho; hash -t myecho; hash')

    def test_dash_p_does_not_verify(self):
        self.assert_identical_behavior(
            'hash -p /nonexistent/echo myecho; echo rc=$?; hash -t myecho')

    def test_dash_d_deletes(self):
        self.assert_identical_behavior('hash ls cat; hash -d ls; hash')
        # populated table: a miss is reported, rc 1
        self.assert_identical_behavior(
            'hash ls; hash -d nosuchcmd_xyz 2>/dev/null; echo rc=$?')
        # EMPTY table: -d silently succeeds (bash quirk)
        self.assert_identical_behavior(
            'hash -d nosuchcmd_xyz; echo rc=$?')

    def test_dash_r_clears(self):
        self.assert_identical_behavior('hash ls; hash -r; hash; echo rc=$?')

    def test_dash_r_with_name_rehashes(self):
        self.assert_identical_behavior('hash cat; hash -r ls; hash')

    def test_dash_t_without_names_errors(self):
        self.assert_identical_behavior('hash -t 2>/dev/null; echo rc=$?')

    def test_invalid_option_status(self):
        self.assert_identical_behavior('hash -v 2>/dev/null; echo rc=$?')


class TestHashExecutionSemantics(ConformanceTest):
    """The executor side: hashing on use, invalidation, staleness."""

    def test_running_command_counts_hits(self):
        self.assert_identical_behavior(
            'ls >/dev/null; ls >/dev/null; ls >/dev/null; hash')

    def test_hash_then_run_increments(self):
        self.assert_identical_behavior('hash ls; ls >/dev/null; hash')

    def test_path_assignment_clears_table(self):
        # bash: even PATH=$PATH empties the table
        self.assert_identical_behavior('hash ls; PATH=$PATH; hash')

    def test_unset_path_clears_table(self):
        self.assert_identical_behavior('hash ls; unset PATH; hash')

    def test_cd_does_not_clear_table(self):
        self.assert_identical_behavior('hash ls; cd /; hash')

    def test_subshell_inherits_table(self):
        self.assert_identical_behavior('hash ls; (hash)')

    def test_set_plus_h_disables_hashing(self):
        self.assert_identical_behavior(
            'set +h; hash ls 2>/dev/null; echo rc=$?; '
            'ls >/dev/null; hash 2>/dev/null; echo rc=$?')

    def test_stale_path_fails_127_by_default(self):
        """bash does NOT re-search PATH when a remembered path is gone
        (probe-verified): the exec fails 127 and the entry stays."""
        self.assert_identical_behavior(
            'd=$(mktemp -d); printf "#!/bin/sh\\necho OK\\n" > "$d/zcmd9"; '
            'chmod +x "$d/zcmd9"; export PATH="$d:$PATH"; zcmd9; '
            'rm "$d/zcmd9"; zcmd9 2>/dev/null; echo rc=$?; rmdir "$d"')

    def test_checkhash_researches_path(self):
        """shopt -s checkhash: the stale entry is dropped and PATH is
        searched afresh — the later copy runs (bash)."""
        self.assert_identical_behavior(
            'shopt -s checkhash; d=$(mktemp -d); mkdir "$d/a" "$d/b"; '
            'printf "#!/bin/sh\\necho ONE\\n" > "$d/a/zcmd9"; '
            'printf "#!/bin/sh\\necho TWO\\n" > "$d/b/zcmd9"; '
            'chmod +x "$d/a/zcmd9" "$d/b/zcmd9"; '
            'export PATH="$d/a:$d/b:$PATH"; zcmd9; '
            'rm "$d/a/zcmd9"; zcmd9; echo rc=$?; rm -r "$d"')
