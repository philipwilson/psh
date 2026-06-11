"""Conformance tests: shell keyword recognition is case-sensitive (bash behavior).

Bash reserved words are matched case-sensitively: `IF`, `THEN`, `DONE` etc.
are ordinary words. PSH must agree (fixed in v0.293.0; previously PSH matched
keywords case-insensitively).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from conformance_framework import ConformanceTest


class TestKeywordCaseSensitivity(ConformanceTest):
    """Uppercase/mixed-case keywords are not reserved words."""

    def test_uppercase_keyword_as_variable_name(self):
        """Variables named after keywords (uppercased) work normally."""
        self.assert_identical_behavior('IF=3; echo $IF')
        self.assert_identical_behavior('DO=5; echo $DO')

    def test_uppercase_keyword_as_argument(self):
        """Uppercase keyword spellings are plain words as arguments."""
        self.assert_identical_behavior('echo DONE')
        self.assert_identical_behavior('echo FI THEN ESAC')

    def test_uppercase_else_is_plain_word_inside_if(self):
        """ELSE inside an if body is a plain word, not the else keyword.

        bash: the then-body is `echo n; ELSE echo y` which never runs
        (condition is false), so output is empty with exit 0.
        """
        self.assert_identical_behavior('if false; then echo n; ELSE echo y; fi')

    def test_uppercase_keyword_as_command_name(self):
        """A lone uppercase keyword is looked up as a command (127)."""
        psh_result = self.framework.run_in_psh('IF')
        bash_result = self.framework.run_in_bash('IF')
        assert psh_result.exit_code == 127
        assert bash_result.exit_code == 127
        assert 'command not found' in psh_result.stderr
        assert 'command not found' in bash_result.stderr

    def test_uppercase_keywords_are_syntax_errors_like_bash(self):
        """Constructs led by uppercase keywords fail to parse in both shells.

        Error text differs between shells, so compare exit status and stdout.
        """
        for command in (
            'IF true; then echo y; fi',
            'FOR i in 1; do echo $i; done',
            'WHILE false; do :; done',
            'CASE x in *) echo y;; esac',
            'if true; THEN echo y; fi',
            'for i IN 1 2; do echo $i; done',
            'case x IN x) echo y;; esac',
        ):
            psh_result = self.framework.run_in_psh(command)
            bash_result = self.framework.run_in_bash(command)
            assert bash_result.exit_code == 2, command
            assert psh_result.exit_code == 2, (
                f"psh should reject like bash: {command}\n"
                f"psh: rc={psh_result.exit_code} stdout={psh_result.stdout!r} "
                f"stderr={psh_result.stderr!r}"
            )
            assert psh_result.stdout == bash_result.stdout == '', command

    def test_lowercase_keywords_still_work(self):
        """Canonical lowercase keywords keep working."""
        self.assert_identical_behavior('if true; then echo y; fi')
        self.assert_identical_behavior('for i in 1 2; do echo $i; done')
        self.assert_identical_behavior('case x in x) echo y;; esac')
        self.assert_identical_behavior('until true; do :; done')
        self.assert_identical_behavior('! false')
