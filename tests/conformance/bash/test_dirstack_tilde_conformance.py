"""Conformance tests for directory-stack tilde prefixes (~+, ~-, ~N).

Pins bug M3 (reappraisal #7): bash tilde-prefix forms
  ~+    -> $PWD              ~-    -> $OLDPWD
  ~N    -> `dirs +N`         ~+N   -> `dirs +N`        ~-N   -> `dirs -N`
psh previously expanded ``~+`` to ``$HOME`` with a literal ``+`` appended
(the lexer split ``~+`` into two words) and left ``~-``/``~N`` literal.

Paths are chosen to avoid the macOS /tmp -> /private/tmp symlink (logical
vs physical) confusing the comparison: /usr, /bin and / are stable.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestDirstackTilde(ConformanceTest):
    """~+ / ~- / ~N / ~+N / ~-N tilde-prefix expansion."""

    def test_tilde_plus_is_pwd(self):
        self.assert_identical_behavior('cd /usr; echo ~+')

    def test_tilde_plus_with_suffix(self):
        self.assert_identical_behavior('cd /usr; echo ~+/bin')

    def test_tilde_minus_is_oldpwd(self):
        self.assert_identical_behavior('cd /bin; cd /usr; echo ~-')

    def test_tilde_minus_with_suffix(self):
        self.assert_identical_behavior('cd /bin; cd /usr; echo ~-/x')

    def test_tilde_minus_unset_oldpwd_literal(self):
        self.assert_identical_behavior('unset OLDPWD; echo ~-')

    def test_quoted_tilde_plus_literal(self):
        self.assert_identical_behavior('cd /usr; echo "~+"')

    def test_tilde_plus_not_at_word_start_literal(self):
        self.assert_identical_behavior('cd /usr; echo x~+')

    def test_dirstack_tilde_plus_n(self):
        self.assert_identical_behavior(
            'cd /; pushd /bin >/dev/null; pushd /usr >/dev/null; echo ~+1')

    def test_dirstack_tilde_n(self):
        self.assert_identical_behavior(
            'cd /; pushd /bin >/dev/null; pushd /usr >/dev/null; echo ~2')

    def test_dirstack_tilde_minus_n(self):
        self.assert_identical_behavior(
            'cd /; pushd /bin >/dev/null; pushd /usr >/dev/null; echo ~-0')

    def test_dirstack_tilde_plus_zero_is_top(self):
        self.assert_identical_behavior(
            'cd /; pushd /bin >/dev/null; pushd /usr >/dev/null; echo ~+0')

    def test_dirstack_out_of_range_literal(self):
        self.assert_identical_behavior('cd /usr; echo ~9 ~+9')

    def test_cd_to_tilde_minus(self):
        self.assert_identical_behavior('cd /bin; cd /usr; cd ~-; echo "$PWD"')
