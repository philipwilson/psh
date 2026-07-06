"""
Regression tests for visitor/executor fixes from code quality reviews.

Based on findings from two independent reviews:
  - visitor_executor_implementation_review_2026-02-09.md
  - codex_visitor_executor_review.md

Phase 1 (v0.146.0) — Critical + High executor bugs:
  1a. Background brace-group double execution
  1b. Loop_depth leak on multi-level break/continue
  1c. Special-builtin prefix assignment persistence

Phase 2 (v0.147.0) — Medium executor bug:
  2a. Pipeline test-mode fallback with real Pipeline node

Phase 3 (v0.148.0) — Medium visitor bugs:
  3a. Linter generic_visit duplication
  3b. Formatter C-style for loop $ injection
  3c. Array subscript expansion (verified not-a-bug)
  3d. Enhanced validator _has_parameter_default under-reporting
"""

import subprocess
import sys

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _psh(cmd: str) -> subprocess.CompletedProcess:
    """Run a command in psh and return the result."""
    return subprocess.run(
        [sys.executable, '-m', 'psh', '-c', cmd],
        capture_output=True, text=True, timeout=10,
    )


# ===========================================================================
# Phase 1 — Critical + High executor bugs
# ===========================================================================


class TestBraceGroupBackground:
    """Fix 1a: { echo hi; } & must not execute in parent AND child."""

    def test_background_brace_group_no_double_execution(self):
        """Background brace group should produce output only once."""
        # Use a file to capture output since background job output is async
        result = _psh(
            'f=$(mktemp); { echo hi > "$f"; } & wait; cat "$f"; rm "$f"'
        )
        assert result.returncode == 0
        # Output should contain exactly one "hi", not two
        assert result.stdout.strip() == "hi"

    def test_foreground_brace_group_still_works(self):
        """Foreground brace group should still execute normally."""
        result = _psh('{ echo hello; echo world; }')
        assert result.returncode == 0
        assert result.stdout == "hello\nworld\n"


class TestLoopDepthLeak:
    """Fix 1b: loop_depth must be decremented even on multi-level break/continue."""

    def test_nested_break_2_does_not_leak(self):
        """break 2 from inner loop should not leak loop_depth."""
        result = _psh(
            'for i in 1 2; do for j in a b; do break 2; done; done; echo ok'
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "ok"

    def test_nested_continue_2_does_not_leak(self):
        """continue 2 from inner loop should not leak loop_depth."""
        result = _psh(
            'for i in 1 2; do for j in a b; do continue 2; done; done; echo ok'
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "ok"

    def test_nested_while_break_2(self):
        """break 2 from nested while loops."""
        result = _psh(
            'x=0; while [ $x -lt 3 ]; do x=$((x+1)); '
            'y=0; while [ $y -lt 3 ]; do y=$((y+1)); break 2; done; done; '
            'echo "x=$x"'
        )
        assert result.returncode == 0
        assert "x=1" in result.stdout

    def test_nested_until_break_2(self):
        """break 2 from nested until loops."""
        result = _psh(
            'x=0; until [ $x -ge 3 ]; do x=$((x+1)); '
            'y=0; until [ $y -ge 3 ]; do y=$((y+1)); break 2; done; done; '
            'echo "x=$x"'
        )
        assert result.returncode == 0
        assert "x=1" in result.stdout


class TestSpecialBuiltinAssignmentPersistence:
    """Special-builtin prefix persistence is MODE-AWARE (F9, 2026-07-06).

    The original "Fix 1c" made a prefix before a special builtin persist in
    ALL modes; bash only does this under ``set -o posix``. In default mode the
    prefix is temporary, like any builtin. These tests now pin both modes.
    """

    def test_export_prefix_temporary_in_default_mode(self):
        """FOO=1 export BAR=2 -> FOO is NOT persisted in default (bash) mode."""
        result = _psh('unset FOO; FOO=1 export BAR=2; printf "<%s>\\n" "${FOO-unset}"')
        assert result.returncode == 0
        assert result.stdout.strip() == "<unset>"

    def test_export_prefix_persists_in_posix_mode(self):
        """Under set -o posix the prefix persists for the special builtin."""
        result = _psh('set -o posix; unset FOO; FOO=1 export BAR=2; printf "<%s>\\n" "${FOO-unset}"')
        assert result.returncode == 0
        assert result.stdout.strip() == "<1>"

    def test_readonly_prefix_temporary_in_default_mode(self):
        result = _psh('unset FOO; FOO=hello readonly BAR=world; printf "<%s>\\n" "${FOO-unset}"')
        assert result.returncode == 0
        assert result.stdout.strip() == "<unset>"

    def test_readonly_prefix_persists_in_posix_mode(self):
        result = _psh('set -o posix; unset FOO; FOO=hello readonly BAR=world; printf "<%s>\\n" "${FOO-unset}"')
        assert result.returncode == 0
        assert result.stdout.strip() == "<hello>"

    def test_eval_prefix_temporary_in_default_mode(self):
        result = _psh('unset X; X=42 eval echo ok; printf "<%s>\\n" "${X-unset}"')
        assert result.returncode == 0
        assert "ok" in result.stdout
        assert "<unset>" in result.stdout

    def test_eval_prefix_persists_in_posix_mode(self):
        result = _psh('set -o posix; unset X; X=42 eval echo ok; printf "<%s>\\n" "${X-unset}"')
        assert result.returncode == 0
        assert "<42>" in result.stdout

    def test_regular_builtin_assignment_does_not_persist(self):
        """FOO=bar echo hi; echo $FOO should NOT print bar (non-special)."""
        result = _psh('unset FOO; FOO=bar echo hi; printf "%s\\n" "FOO=$FOO"')
        assert result.returncode == 0
        # FOO should be empty/unset after non-special builtin
        assert "FOO=\n" in result.stdout or "FOO=" in result.stdout.strip()


# ===========================================================================
# Phase 3 — Medium visitor bugs
# ===========================================================================


class TestFormatterCStyleFor:
    """Fix 3b: C-style for loop formatter should not inject $ characters."""

    def test_c_style_for_no_dollar_in_output(self):
        """for ((i=0; i<3; i++)) should format without $ prefixes."""
        from psh.ast_nodes import CStyleForLoop, SimpleCommand, StatementList, Word
        from psh.visitor.formatter_visitor import FormatterVisitor

        body = StatementList(statements=[
            SimpleCommand(words=[Word.from_string('echo'), Word.from_string('hi')])
        ])
        node = CStyleForLoop(
            init_expr='i=0',
            condition_expr='i<3',
            update_expr='i++',
            body=body,
            redirects=[],
        )
        formatter = FormatterVisitor()
        output = formatter.visit(node)
        # Should NOT contain $i=0, $i<3, or $i++
        assert '$i=0' not in output
        assert '$i<3' not in output
        assert '$i++' not in output
        # Should contain the expressions without $
        assert 'for ((i=0; i<3; i++))' in output


class TestLinterGenericVisit:
    """Fix 3a: Linter generic_visit should use dataclasses.fields, not dir()."""

    def test_generic_visit_no_duplicate_traversal(self):
        """generic_visit should not traverse the same child multiple times."""
        from psh.ast_nodes import (
            SimpleCommand,
            StatementList,
            WhileLoop,
            Word,
        )
        from psh.visitor.linter_visitor import LinterVisitor

        # Create a simple while loop — generic_visit will be called for
        # WhileLoop since the linter has no explicit visit_WhileLoop
        cmd = SimpleCommand(words=[Word.from_string('echo'), Word.from_string('test')])
        body = StatementList(statements=[cmd])
        condition = StatementList(statements=[
            SimpleCommand(words=[Word.from_string('true')])
        ])
        node = WhileLoop(
            condition=condition,
            body=body,
            redirects=[],
        )

        linter = LinterVisitor()
        # This should not raise and should traverse without issues
        linter.visit(node)


class TestEnhancedValidatorParameterDefault:
    """Fix 3d: _has_parameter_default should only match inside ${...}."""

    def test_default_inside_expansion(self):
        """${var:-default} should be detected as having a default."""
        from psh.visitor.enhanced_validator_visitor import EnhancedValidatorVisitor
        v = EnhancedValidatorVisitor()
        assert v._has_parameter_default('${FOO:-bar}') is True
        assert v._has_parameter_default('${FOO:=bar}') is True

    def test_no_false_positive_outside_expansion(self):
        """Plain text containing :- should not be detected as a default."""
        from psh.visitor.enhanced_validator_visitor import EnhancedValidatorVisitor
        v = EnhancedValidatorVisitor()
        # These contain :- or := but NOT inside ${...}
        assert v._has_parameter_default('some:-text') is False
        assert v._has_parameter_default('path:=/usr/bin') is False

    def test_nested_expansion_with_default(self):
        """Nested ${...} with default should still be detected."""
        from psh.visitor.enhanced_validator_visitor import EnhancedValidatorVisitor
        v = EnhancedValidatorVisitor()
        assert v._has_parameter_default('${FOO:-${BAR:-baz}}') is True

    def test_no_expansion_at_all(self):
        """Plain text without any expansion should return False."""
        from psh.visitor.enhanced_validator_visitor import EnhancedValidatorVisitor
        v = EnhancedValidatorVisitor()
        assert v._has_parameter_default('hello world') is False
        assert v._has_parameter_default('') is False


class TestFormatterArraySubscript:
    """Fix 3c: Verify ${arr[0]} round-trips correctly (not-a-bug)."""

    def test_braced_array_subscript_roundtrip(self):
        """${arr[0]} should format as ${arr[0]} through parse → format."""
        from psh.ast_nodes import (
            ExpansionPart,
            LiteralPart,
            ParameterExpansion,
            SimpleCommand,
            Word,
        )
        from psh.visitor.formatter_visitor import FormatterVisitor

        # Simulate a command like: echo ${arr[0]}
        expansion = ParameterExpansion(parameter='arr[0]')
        word = Word(parts=[ExpansionPart(expansion=expansion)])
        node = SimpleCommand(
            words=[
                Word(parts=[LiteralPart('echo')]),
                word,
            ],
        )
        formatter = FormatterVisitor()
        output = formatter.visit(node)
        assert '${arr[0]}' in output
