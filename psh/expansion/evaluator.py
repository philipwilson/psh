"""Expansion evaluator for Word AST nodes.

This module evaluates expansion AST nodes to produce strings,
delegating to the existing VariableExpander and ExpansionManager
to avoid duplicating expansion logic.
"""

from typing import TYPE_CHECKING, Optional

from ..ast_nodes import (
    ArithmeticExpansion,
    CommandSubstitution,
    Expansion,
    ParameterExpansion,
    ProcessSubstitution,
    VariableExpansion,
)

if TYPE_CHECKING:
    from ..shell import Shell


class ExpansionEvaluator:
    """Evaluates expansion AST nodes by delegating to VariableExpander."""

    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.state = shell.state
        self.expansion_manager = shell.expansion_manager

    def evaluate(self, expansion: Expansion,
                 quote_ctx: Optional[str] = None) -> str:
        """Evaluate any expansion type.

        Reconstructs the canonical string form and delegates to
        VariableExpander.expand_variable() or ExpansionManager
        methods, avoiding duplicated logic.

        Args:
            expansion: The expansion AST node to evaluate
            quote_ctx: quote context enclosing the expansion
                (expansion.operands: None / DQ_WORD / DQ_STRING) —
                consulted by parameter-expansion value operands

        Returns:
            The expanded string value

        Raises:
            ValueError: If expansion type is unknown
        """
        if isinstance(expansion, VariableExpansion):
            return self._evaluate_variable(expansion)
        elif isinstance(expansion, CommandSubstitution):
            return self._evaluate_command_sub(expansion)
        elif isinstance(expansion, ParameterExpansion):
            return self._evaluate_parameter(expansion, quote_ctx)
        elif isinstance(expansion, ArithmeticExpansion):
            return self._evaluate_arithmetic(expansion)
        elif isinstance(expansion, ProcessSubstitution):
            return self._evaluate_process_substitution(expansion)
        else:
            raise ValueError(f"Unknown expansion type: {type(expansion)}")

    def _evaluate_variable(self, expansion: VariableExpansion) -> str:
        """Evaluate simple variable expansion by delegating to VariableExpander."""
        name = expansion.name
        # Array subscript syntax (arr[0]) requires ${...} form
        if '[' in name:
            return self.expansion_manager.variable_expander.expand_variable(
                f"${{{name}}}"
            )
        return self.expansion_manager.variable_expander.expand_variable(
            f"${name}"
        )

    def _evaluate_command_sub(self, expansion: CommandSubstitution) -> str:
        """Evaluate command substitution.

        The parsed ``program`` (built at the outer parse; None for backticks)
        already rejected invalid syntax. Execution re-parses ``source`` against
        the RUNTIME alias table so alias timing, byte, and status semantics
        match bash, which re-parses substitution bodies at expansion time.
        """
        if expansion.backtick_style:
            cmd_sub = f"`{expansion.source}`"
        else:
            cmd_sub = f"$({expansion.source})"
        return self.expansion_manager.command_sub.execute(cmd_sub)

    def _evaluate_parameter(self, expansion: ParameterExpansion,
                            quote_ctx: Optional[str] = None) -> str:
        """Evaluate parameter expansion by calling VariableExpander directly.

        Uses expand_parameter_direct() with the pre-parsed components —
        the parser (param_parser.py) fully classifies every operator form,
        so an operator-less node is always a plain parameter.
        """
        ve = self.expansion_manager.variable_expander
        # Reject syntactically-invalid parameter names (bash "bad
        # substitution") at expansion time, for both operator and plain forms
        # (the operator path, expand_parameter_direct, otherwise bypasses it).
        # Validate ONCE here from the pre-parsed node — the plain path below no
        # longer re-parses ${...} and re-validates a second time.
        ve._reject_bad_substitution(expansion)
        if expansion.operator:
            return ve.expand_parameter_direct(
                # Preserve None vs '': ${#v} (length) has word=None,
                # ${v#} (empty removal pattern) has word=''.
                expansion.operator, expansion.parameter,
                expansion.word, quote_ctx=quote_ctx
            )
        else:
            # Plain ${var} / ${arr[idx]} — name resolution straight from the
            # parsed name (nounset, specials, subscripts), no re-parse.
            return ve._resolve_plain_parameter(expansion.parameter)

    def _evaluate_arithmetic(self, expansion: ArithmeticExpansion) -> str:
        """Evaluate arithmetic expansion straight from the parsed expression
        text (no ``$(( ))`` wrap/unwrap round-trip)."""
        result = self.expansion_manager.arithmetic_expansion_value(
            expansion.expression
        )
        return str(result)

    def _evaluate_process_substitution(self, expansion: ProcessSubstitution) -> str:
        """Perform a process substitution and return its /dev/fd/N path.

        The parent fd and child pid register with the
        ProcessSubstitutionHandler; the enclosing process_sub_scope()
        closes the fd and reaps the child when the consuming command
        finishes (e.g. assignment values like ``x=<(cmd)``).
        """
        return self.shell.io_manager.create_process_substitution_for_expansion(
            expansion.direction, expansion.source)
