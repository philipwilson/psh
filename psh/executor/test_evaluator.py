"""Test expression evaluator for [[ ]] constructs."""
import fnmatch
import re
from typing import TYPE_CHECKING

from ..ast_nodes import (
    BinaryTestExpression,
    CompoundTestExpression,
    NegatedTestExpression,
    TestExpression,
    UnaryTestExpression,
)

if TYPE_CHECKING:
    from ..shell import Shell


def to_int(value: str) -> int:
    """Convert string to integer for numeric comparisons."""
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"integer expression expected: {value}")


class TestExpressionEvaluator:
    """Evaluates [[ ]] test expressions using shell state for expansions."""

    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.expansion_manager = shell.expansion_manager
        self.state = shell.state

    def _set_bash_rematch(self, match) -> None:
        """Set BASH_REMATCH from an `re` match (full match + capture groups)."""
        from ..core import IndexedArray, VarAttributes

        arr = IndexedArray()
        if match is not None:
            arr.set(0, match.group(0))
            for i, group in enumerate(match.groups(), start=1):
                arr.set(i, group if group is not None else '')
        self.state.scope_manager.set_variable(
            'BASH_REMATCH', arr, attributes=VarAttributes.ARRAY,
        )

    def evaluate(self, expr: TestExpression) -> bool:
        """Evaluate a test expression to boolean."""
        if isinstance(expr, BinaryTestExpression):
            return self._evaluate_binary_test(expr)
        elif isinstance(expr, UnaryTestExpression):
            return self.evaluate_unary_test(expr)
        elif isinstance(expr, CompoundTestExpression):
            return self._evaluate_compound_test(expr)
        elif isinstance(expr, NegatedTestExpression):
            return not self.evaluate(expr.expression)
        else:
            raise ValueError(f"Unknown test expression type: {type(expr).__name__}")

    def _expand_operand(self, operand: str) -> str:
        """Expand tilde and variables in a [[ ]] operand."""
        result = self.expansion_manager.expand_tilde(operand)
        return self.expansion_manager.expand_string_variables(result)

    def _evaluate_binary_test(self, expr: BinaryTestExpression) -> bool:
        """Evaluate binary test expression."""
        # Expand tilde and variables in operands
        left = self._expand_operand(expr.left)
        right = self._expand_operand(expr.right)

        # Process escape sequences for pattern matching
        left = self._process_escape_sequences(left)
        right = self._process_escape_sequences(right)

        # Handle different operators
        if expr.operator == '=':
            return left == right
        elif expr.operator == '==':
            # Shell pattern matching (not string equality)
            # If the right operand was quoted, treat it as literal string
            right_quote_type = getattr(expr, 'right_quote_type', None)
            if right_quote_type:
                return left == right
            else:
                return self._pattern_match(left, right)
        elif expr.operator == '!=':
            # Shell pattern non-matching
            right_quote_type = getattr(expr, 'right_quote_type', None)
            if right_quote_type:
                return left != right
            else:
                return not self._pattern_match(left, right)
        elif expr.operator == '<':
            return left < right
        elif expr.operator == '>':
            return left > right
        elif expr.operator == '=~':
            # Regex matching; populate BASH_REMATCH with the full match and
            # capture groups (cleared to an empty array on no match), like bash.
            try:
                pattern = re.compile(right)
            except re.error as e:
                raise ValueError(f"invalid regex: {e}")
            match = pattern.search(left)
            self._set_bash_rematch(match)
            return bool(match)
        elif expr.operator == '-eq':
            return to_int(left) == to_int(right)
        elif expr.operator == '-ne':
            return to_int(left) != to_int(right)
        elif expr.operator == '-lt':
            return to_int(left) < to_int(right)
        elif expr.operator == '-le':
            return to_int(left) <= to_int(right)
        elif expr.operator == '-gt':
            return to_int(left) > to_int(right)
        elif expr.operator == '-ge':
            return to_int(left) >= to_int(right)
        elif expr.operator == '-nt':
            from ..utils.file_tests import file_newer_than
            return file_newer_than(left, right)
        elif expr.operator == '-ot':
            from ..utils.file_tests import file_older_than
            return file_older_than(left, right)
        elif expr.operator == '-ef':
            from ..utils.file_tests import files_same
            return files_same(left, right)
        else:
            raise ValueError(f"unknown binary operator: {expr.operator}")

    def _process_escape_sequences(self, text: str) -> str:
        """Process escape sequences in test expression operands."""
        if not text or '\\' not in text:
            return text

        result = []
        i = 0
        while i < len(text):
            if text[i] == '\\' and i + 1 < len(text):
                result.append(text[i + 1])
                i += 2
            else:
                result.append(text[i])
                i += 1

        return ''.join(result)

    def _pattern_match(self, string: str, pattern: str) -> bool:
        """Match string against a shell pattern, with extglob support."""
        if self.state.options.get('extglob', False):
            from ..expansion.extglob import contains_extglob, match_extglob
            if contains_extglob(pattern):
                return match_extglob(pattern, string)
        from ..expansion.glob import normalize_bracket_expressions
        return fnmatch.fnmatch(string, normalize_bracket_expressions(pattern))

    def evaluate_unary_test(self, expr: UnaryTestExpression) -> bool:
        """Evaluate unary test expression."""
        # Handle -v operator specially since it needs shell state
        if expr.operator == '-v':
            operand = expr.operand  # Don't expand for -v, we want the variable name
            return self._is_variable_set(operand)

        # Expand tilde and variables in operand for other operators
        operand = self._expand_operand(expr.operand)

        # Import test command's unary operators
        from ..builtins.test_command import TestBuiltin
        test_cmd = TestBuiltin()

        # Reuse the existing unary operator implementation
        # Note: evaluate_unary returns 0 for true, 1 for false (shell convention)
        result = test_cmd.evaluate_unary(expr.operator, operand, self.shell)
        return result == 0

    def _evaluate_compound_test(self, expr: CompoundTestExpression) -> bool:
        """Evaluate compound test expression with && or ||."""
        left_result = self.evaluate(expr.left)

        if expr.operator == '&&':
            if not left_result:
                return False
            return self.evaluate(expr.right)
        elif expr.operator == '||':
            if left_result:
                return True
            return self.evaluate(expr.right)
        else:
            raise ValueError(f"unknown compound operator: {expr.operator}")

    def _is_variable_set(self, var_ref: str) -> bool:
        """Check if a variable is set, including array element syntax.

        Supports:
        - var: check if variable is set
        - array[key]: check if array element exists
        """
        if '[' in var_ref and var_ref.endswith(']'):
            var_name = var_ref[:var_ref.index('[')]
            key_expr = var_ref[var_ref.index('[') + 1:-1]

            # Expand the key expression
            key = self.expansion_manager.expand_string_variables(key_expr)

            # Get the array variable
            var_obj = self.state.scope_manager.get_variable_object(var_name)
            if not var_obj:
                return False

            from ..core import AssociativeArray, IndexedArray
            if isinstance(var_obj.value, AssociativeArray):
                return key in var_obj.value._elements
            elif isinstance(var_obj.value, IndexedArray):
                try:
                    index = int(key)
                    return index in var_obj.value._elements
                except ValueError:
                    return False
            else:
                return False
        else:
            var_obj = self.state.scope_manager.get_variable_object(var_ref)
            return var_obj is not None
