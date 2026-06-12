"""
Code metrics visitor for PSH.

This visitor analyzes AST to collect various code metrics and statistics
useful for understanding script complexity and structure.
"""

from collections import defaultdict
from typing import Any, Dict

from ..ast_nodes import (
    AndOrList,
    ArithmeticEvaluation,
    ArrayElementAssignment,
    ArrayInitialization,
    ASTNode,
    BreakStatement,
    CaseConditional,
    ContinueStatement,
    CStyleForLoop,
    EnhancedTestStatement,
    ForLoop,
    FunctionDef,
    IfConditional,
    Pipeline,
    ProcessSubstitution,
    Redirect,
    SelectLoop,
    SimpleCommand,
    StatementList,
    TopLevel,
    UntilLoop,
    WhileLoop,
)
from .base import ASTVisitor
from .constants import SHELL_BUILTINS
from .traversal import visit_children


class CodeMetrics:
    """Container for code metrics data."""

    def __init__(self):
        # Basic counts
        self.total_lines = 0
        self.total_commands = 0
        self.total_pipelines = 0
        self.total_functions = 0
        self.total_loops = 0
        self.total_conditionals = 0
        self.total_redirections = 0
        self.total_variables = 0
        self.total_arrays = 0

        # Command usage
        self.command_frequency = defaultdict(int)
        self.builtin_commands = set()
        self.external_commands = set()

        # Complexity metrics
        self.max_nesting_depth = 0
        self.max_pipeline_length = 0
        self.max_function_complexity = 0
        self.cyclomatic_complexity = 1  # Start at 1 for main path

        # Variables and functions
        self.variable_names = set()
        self.function_names = set()
        self.array_names = set()

        # Control flow
        self.loop_types = defaultdict(int)  # while, for, select, c-style for
        self.conditional_types = defaultdict(int)  # if, case

        # Advanced features
        self.process_substitutions = 0
        self.command_substitutions = 0
        self.arithmetic_evaluations = 0
        self.here_documents = 0

        # Per-function metrics
        self.function_metrics = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary format."""
        return {
            'summary': {
                'total_commands': self.total_commands,
                'total_pipelines': self.total_pipelines,
                'total_functions': self.total_functions,
                'total_loops': self.total_loops,
                'total_conditionals': self.total_conditionals,
                'total_redirections': self.total_redirections,
                'total_variables': len(self.variable_names),
                'total_arrays': len(self.array_names),
            },
            'complexity': {
                'cyclomatic_complexity': self.cyclomatic_complexity,
                'max_nesting_depth': self.max_nesting_depth,
                'max_pipeline_length': self.max_pipeline_length,
                'max_function_complexity': self.max_function_complexity,
            },
            'commands': {
                'unique_commands': len(self.command_frequency),
                'builtin_count': len(self.builtin_commands),
                'external_count': len(self.external_commands),
                'top_10_commands': dict(sorted(
                    self.command_frequency.items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:10]),
            },
            'control_flow': {
                'loop_types': dict(self.loop_types),
                'conditional_types': dict(self.conditional_types),
            },
            'advanced_features': {
                'process_substitutions': self.process_substitutions,
                'command_substitutions': self.command_substitutions,
                'arithmetic_evaluations': self.arithmetic_evaluations,
                'here_documents': self.here_documents,
            },
            'identifiers': {
                'functions': sorted(self.function_names),
                'variables': sorted(self.variable_names),
                'arrays': sorted(self.array_names),
            },
            'function_metrics': self.function_metrics,
        }


class MetricsVisitor(ASTVisitor[None]):
    """
    Collect code metrics from shell script AST.

    Metrics collected include:
    - Command counts and frequency
    - Control structure usage
    - Complexity metrics (cyclomatic, nesting depth)
    - Variable and function usage
    - Advanced feature usage
    """

    def __init__(self):
        """Initialize the metrics visitor."""
        super().__init__()
        self.metrics = CodeMetrics()
        self.current_nesting_depth = 0
        self.current_function = None
        self.in_command_substitution = False

    def visit_TopLevel(self, node: TopLevel) -> None:
        """Visit top-level statements."""
        for item in node.items:
            self.visit(item)

    def _visit_redirects(self, node: ASTNode) -> None:
        """Count redirects carried by *node*.

        Compound commands (loops, conditionals, groups, ...) carry a
        ``redirects`` list just like simple commands; every explicit visit
        method for such a node calls this so e.g. ``while ...; done > log``
        contributes to total_redirections. Nodes without an explicit method
        reach visit_Redirect through generic_visit's child traversal.
        """
        for redirect in getattr(node, 'redirects', []):
            self.visit(redirect)

    def visit_Redirect(self, node: Redirect) -> None:
        """Count a redirection (and here-documents)."""
        self.metrics.total_redirections += 1
        if node.type in ['<<', '<<-']:
            self.metrics.here_documents += 1

    def visit_StatementList(self, node: StatementList) -> None:
        """Visit statement list."""
        for statement in node.statements:
            self.visit(statement)

    def visit_AndOrList(self, node: AndOrList) -> None:
        """Visit and/or list."""
        # Each && or || adds to cyclomatic complexity
        self.metrics.cyclomatic_complexity += len(node.operators)

        for pipeline in node.pipelines:
            self.visit(pipeline)

    def visit_Pipeline(self, node: Pipeline) -> None:
        """Visit pipeline."""
        self.metrics.total_pipelines += 1
        self.metrics.max_pipeline_length = max(
            self.metrics.max_pipeline_length,
            len(node.commands)
        )

        for command in node.commands:
            self.visit(command)

    def visit_SimpleCommand(self, node: SimpleCommand) -> None:
        """Visit simple command."""
        # Handle array assignments even if no command
        for assignment in node.array_assignments:
            if isinstance(assignment, ArrayInitialization):
                self.metrics.array_names.add(assignment.name)
            elif isinstance(assignment, ArrayElementAssignment):
                self.metrics.array_names.add(assignment.name)

        # Count redirections (even for bare-redirect commands like `> file`)
        self._visit_redirects(node)

        if not node.args:
            return

        self.metrics.total_commands += 1
        cmd_name = node.args[0]

        # Track command frequency
        self.metrics.command_frequency[cmd_name] += 1

        # Classify command
        if cmd_name in SHELL_BUILTINS:
            self.metrics.builtin_commands.add(cmd_name)
        else:
            self.metrics.external_commands.add(cmd_name)

        # Special handling for declare/typeset
        if cmd_name in ['declare', 'typeset'] and len(node.args) >= 3:
            # declare -a varname or declare varname=value
            for i, arg in enumerate(node.args[1:], 1):
                if arg.startswith('-'):
                    continue
                # Extract variable name
                if '=' in arg:
                    var_name = arg.split('=', 1)[0]
                else:
                    var_name = arg
                if self._is_valid_varname(var_name):
                    self.metrics.variable_names.add(var_name)
                    # If -a flag, it's an array
                    if '-a' in node.args or '-A' in node.args:
                        self.metrics.array_names.add(var_name)

        # Check for variable assignments
        for arg in node.args:
            if '=' in arg and self._is_assignment(arg):
                var_name = arg.split('=', 1)[0]
                self.metrics.variable_names.add(var_name)

        # Look for variable expansions and command substitutions
        for arg in node.args:
            self._analyze_string_features(arg)

    def visit_FunctionDef(self, node: FunctionDef) -> None:
        """Visit function definition."""
        self.metrics.total_functions += 1
        self.metrics.function_names.add(node.name)

        # Track per-function metrics
        old_function = self.current_function

        self.current_function = node.name
        function_start_complexity = self.metrics.cyclomatic_complexity

        # Analyze function body
        self.current_nesting_depth += 1
        self.visit(node.body)
        self.current_nesting_depth -= 1

        # Calculate function complexity
        function_complexity = self.metrics.cyclomatic_complexity - function_start_complexity
        self.metrics.function_metrics[node.name] = {
            'complexity': function_complexity,
            'commands': self._count_commands_in_node(node.body),
        }

        self.metrics.max_function_complexity = max(
            self.metrics.max_function_complexity,
            function_complexity
        )

        self.current_function = old_function
        self._visit_redirects(node)

    def visit_IfConditional(self, node: IfConditional) -> None:
        """Visit if conditional."""
        self.metrics.total_conditionals += 1
        self.metrics.conditional_types['if'] += 1

        # Each if/elif branch adds to complexity
        self.metrics.cyclomatic_complexity += 1
        self.metrics.cyclomatic_complexity += len(node.elif_parts)

        self.current_nesting_depth += 1
        self.metrics.max_nesting_depth = max(
            self.metrics.max_nesting_depth,
            self.current_nesting_depth
        )

        # Visit all parts
        self.visit(node.condition)
        self.visit(node.then_part)
        for cond, then in node.elif_parts:
            self.visit(cond)
            self.visit(then)
        if node.else_part:
            self.visit(node.else_part)

        self.current_nesting_depth -= 1
        self._visit_redirects(node)

    def visit_WhileLoop(self, node: WhileLoop) -> None:
        """Visit while loop."""
        self.metrics.total_loops += 1
        self.metrics.loop_types['while'] += 1
        self.metrics.cyclomatic_complexity += 1

        self.current_nesting_depth += 1
        self.metrics.max_nesting_depth = max(
            self.metrics.max_nesting_depth,
            self.current_nesting_depth
        )

        self.visit(node.condition)
        self.visit(node.body)

        self.current_nesting_depth -= 1
        self._visit_redirects(node)

    def visit_UntilLoop(self, node: UntilLoop) -> None:
        """Visit until loop (mirrors while: a loop with a condition + body)."""
        self.metrics.total_loops += 1
        self.metrics.loop_types['until'] += 1
        self.metrics.cyclomatic_complexity += 1

        self.current_nesting_depth += 1
        self.metrics.max_nesting_depth = max(
            self.metrics.max_nesting_depth,
            self.current_nesting_depth
        )

        self.visit(node.condition)
        self.visit(node.body)

        self.current_nesting_depth -= 1
        self._visit_redirects(node)

    def visit_ForLoop(self, node: ForLoop) -> None:
        """Visit for loop."""
        self.metrics.total_loops += 1
        self.metrics.loop_types['for'] += 1
        self.metrics.cyclomatic_complexity += 1

        # Loop variable
        self.metrics.variable_names.add(node.variable)

        self.current_nesting_depth += 1
        self.metrics.max_nesting_depth = max(
            self.metrics.max_nesting_depth,
            self.current_nesting_depth
        )

        # Analyze items for features
        for item in node.items:
            # Items might contain variables without $
            if self._is_valid_varname(item):
                # This could be a variable name
                self.metrics.variable_names.add(item)
            else:
                # Or it might contain $ variables
                self._analyze_string_features(item)

        self.visit(node.body)

        self.current_nesting_depth -= 1
        self._visit_redirects(node)

    def visit_CStyleForLoop(self, node: CStyleForLoop) -> None:
        """Visit C-style for loop."""
        self.metrics.total_loops += 1
        self.metrics.loop_types['c-style-for'] += 1
        self.metrics.cyclomatic_complexity += 1

        self.current_nesting_depth += 1
        self.metrics.max_nesting_depth = max(
            self.metrics.max_nesting_depth,
            self.current_nesting_depth
        )

        # Analyze arithmetic expressions
        if node.init_expr:
            self._analyze_arithmetic_expr(node.init_expr)
        if node.condition_expr:
            self._analyze_arithmetic_expr(node.condition_expr)
        if node.update_expr:
            self._analyze_arithmetic_expr(node.update_expr)

        self.visit(node.body)

        self.current_nesting_depth -= 1
        self._visit_redirects(node)

    def visit_SelectLoop(self, node: SelectLoop) -> None:
        """Visit select loop."""
        self.metrics.total_loops += 1
        self.metrics.loop_types['select'] += 1
        self.metrics.cyclomatic_complexity += 1

        # Loop variable
        self.metrics.variable_names.add(node.variable)

        self.current_nesting_depth += 1
        self.metrics.max_nesting_depth = max(
            self.metrics.max_nesting_depth,
            self.current_nesting_depth
        )

        # Analyze items
        for item in node.items:
            self._analyze_string_features(item)

        self.visit(node.body)

        self.current_nesting_depth -= 1
        self._visit_redirects(node)

    def visit_CaseConditional(self, node: CaseConditional) -> None:
        """Visit case statement."""
        self.metrics.total_conditionals += 1
        self.metrics.conditional_types['case'] += 1

        # Each case adds to complexity
        self.metrics.cyclomatic_complexity += len(node.items)

        self.current_nesting_depth += 1
        self.metrics.max_nesting_depth = max(
            self.metrics.max_nesting_depth,
            self.current_nesting_depth
        )

        # Analyze expression
        self._analyze_string_features(node.expr)

        # Visit case items
        for item in node.items:
            self.visit(item.commands)

        self.current_nesting_depth -= 1
        self._visit_redirects(node)

    def visit_ArithmeticEvaluation(self, node: ArithmeticEvaluation) -> None:
        """Visit arithmetic evaluation."""
        self.metrics.arithmetic_evaluations += 1
        self._analyze_arithmetic_expr(node.expression)
        self._visit_redirects(node)

    def visit_ProcessSubstitution(self, node: ProcessSubstitution) -> None:
        """Visit process substitution."""
        self.metrics.process_substitutions += 1
        # Process substitution contains a command
        # but we'll count it separately

    def visit_BreakStatement(self, node: BreakStatement) -> None:
        """Visit break statement."""
        # Break adds a path, increasing complexity
        self.metrics.cyclomatic_complexity += 1

    def visit_ContinueStatement(self, node: ContinueStatement) -> None:
        """Visit continue statement."""
        # Continue adds a path, increasing complexity
        self.metrics.cyclomatic_complexity += 1

    def visit_EnhancedTestStatement(self, node: EnhancedTestStatement) -> None:
        """Visit enhanced test [[...]]."""
        self.metrics.total_conditionals += 1
        self.metrics.conditional_types['test'] += 1
        self._visit_redirects(node)

    # Helper methods

    def _is_assignment(self, arg: str) -> bool:
        """Check if argument is a variable assignment."""
        if '=' not in arg:
            return False
        var_name = arg.split('=', 1)[0]
        return self._is_valid_varname(var_name)

    def _is_valid_varname(self, var_name: str) -> bool:
        """Check if string is a valid variable name."""
        if not var_name:
            return False
        return var_name[0].isalpha() or var_name[0] == '_'

    def _analyze_string_features(self, text: str) -> None:
        """Analyze string for command substitutions and variables."""
        # Simple heuristic - count $(...) and `...`
        self.metrics.command_substitutions += text.count('$(')
        self.metrics.command_substitutions += text.count('`')

        # Count variable references - handle both quoted and unquoted
        import re
        # Match $var, ${var}, $1, etc.
        var_pattern = r'\$(?:\{?([a-zA-Z_][a-zA-Z0-9_]*)\}?|(\d+)|[@*#?$!-])'
        matches = re.finditer(var_pattern, text)
        for match in matches:
            # Get the variable name from either group 1 (named var) or group 2 (numeric)
            var = match.group(1) or match.group(2) or match.group(0).strip('$')
            if var and (var[0].isalpha() or var[0] == '_'):
                self.metrics.variable_names.add(var)

    def _analyze_arithmetic_expr(self, expr: str) -> None:
        """Analyze arithmetic expression for variables."""
        # Look for variable names in arithmetic
        import re
        # Match valid identifiers
        var_pattern = r'\b[a-zA-Z_][a-zA-Z0-9_]*\b'
        matches = re.findall(var_pattern, expr)
        for var in matches:
            # Filter out operators and numbers
            if var not in ['if', 'then', 'else', 'while', 'for', 'do', 'done']:
                self.metrics.variable_names.add(var)

    def _count_commands_in_node(self, node: ASTNode) -> int:
        """Count total commands in a node subtree."""
        # Avoid infinite recursion with visited set
        visited = set()

        def count_recursive(n):
            if id(n) in visited:
                return 0
            visited.add(id(n))

            if isinstance(n, SimpleCommand):
                return 1

            count = 0
            if hasattr(n, '__dict__'):
                for attr_name, value in n.__dict__.items():
                    # Skip private attributes and known non-node attributes
                    if attr_name.startswith('_') or attr_name == 'background':
                        continue

                    if isinstance(value, list):
                        for item in value:
                            if isinstance(item, ASTNode):
                                count += count_recursive(item)
                    elif isinstance(value, ASTNode):
                        count += count_recursive(value)

            return count

        return count_recursive(node)

    def get_metrics(self) -> CodeMetrics:
        """Get the collected metrics."""
        return self.metrics

    def get_report(self) -> Dict[str, Any]:
        """Get a formatted metrics report."""
        return self.metrics.to_dict()

    def get_summary(self) -> str:
        """Get a formatted summary of collected metrics."""
        m = self.metrics
        return f"""Script Metrics Summary:
═══════════════════════════════════════
Commands:
  Total Commands:        {m.total_commands:>6}
  Unique Commands:       {len(m.command_frequency):>6}
  Built-in Commands:     {len(m.builtin_commands):>6}
  External Commands:     {len(m.external_commands):>6}

Structure:
  Functions Defined:     {m.total_functions:>6}
  Pipelines:            {m.total_pipelines:>6}
  Loops:                {m.total_loops:>6}
  Conditionals:         {m.total_conditionals:>6}

Complexity:
  Cyclomatic Complexity: {m.cyclomatic_complexity:>6}
  Max Pipeline Length:   {m.max_pipeline_length:>6}
  Max Nesting Depth:     {m.max_nesting_depth:>6}
  Max Function Complex:  {m.max_function_complexity:>6}

Advanced Features:
  Variables Used:        {len(m.variable_names):>6}
  Arrays Used:          {len(m.array_names):>6}
  Command Substitutions: {m.command_substitutions:>6}
  Arithmetic Operations: {m.arithmetic_evaluations:>6}
  Process Substitutions: {m.process_substitutions:>6}
  Here Documents:        {m.here_documents:>6}

Top Commands:
{self._format_top_commands()}"""

    def _format_top_commands(self) -> str:
        """Format top 5 most used commands."""
        top_cmds = sorted(
            self.metrics.command_frequency.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]

        lines = []
        for cmd, count in top_cmds:
            lines.append(f"  {cmd:<20} {count:>6}")
        return '\n'.join(lines) if lines else "  (none)"

    def generic_visit(self, node: ASTNode) -> None:
        """Descend into child nodes for unhandled node types."""
        visit_children(self, node)
