"""
Executor visitor that executes AST nodes using the visitor pattern.

This visitor provides a clean architecture for command execution while
maintaining compatibility with the existing execution engine.
"""

import sys
from typing import TYPE_CHECKING

from psh.visitor import ASTVisitor

from ..ast_nodes import (
    AndOrList,
    # Arithmetic
    ArithmeticEvaluation,
    ArrayElementAssignment,
    # Array operations
    ArrayInitialization,
    # Core nodes
    ASTNode,
    BraceGroup,
    CaseConditional,
    CStyleForLoop,
    # Test commands
    EnhancedTestStatement,
    ForLoop,
    # Function nodes
    FunctionDef,
    IfConditional,
    Pipeline,
    SelectLoop,
    SimpleCommand,
    StatementList,
    # Other
    SubshellGroup,
    TopLevel,
    UntilLoop,
    WhileLoop,
)
from ..core import LoopBreak, LoopContinue
from ..core.exceptions import FunctionReturn
from .array import ArrayOperationExecutor
from .command import CommandExecutor
from .context import ExecutionContext
from .control_flow import ControlFlowExecutor
from .function import FunctionOperationExecutor
from .pipeline import PipelineExecutor
from .subshell import SubshellExecutor

if TYPE_CHECKING:
    from ..shell import Shell


class ExecutorVisitor(ASTVisitor[int]):
    """
    Visitor that executes AST nodes and returns exit status.

    This visitor maintains compatibility with the existing execution
    engine while providing a cleaner architecture based on the visitor
    pattern.
    """

    def __init__(self, shell: 'Shell'):
        """
        Initialize executor with shell instance.

        Args:
            shell: The shell instance providing access to all components
        """
        super().__init__()  # Initialize method cache
        self.shell = shell
        self.state = shell.state
        self.expansion_manager = shell.expansion_manager
        self.io_manager = shell.io_manager
        self.job_manager = shell.job_manager
        self.builtin_registry = shell.builtin_registry
        self.function_manager = shell.function_manager

        # Execution context - replaces scattered state variables
        self.context = ExecutionContext()

        # Command executor - handles simple command execution.
        # It receives this visitor explicitly: strategies use it to run
        # function bodies and compound commands (no hidden backchannel).
        self.command_executor = CommandExecutor(shell, self)

        # Pipeline executor - handles pipeline execution
        self.pipeline_executor = PipelineExecutor(shell)

        # Control flow executor - handles control structures
        self.control_flow_executor = ControlFlowExecutor(shell)

        # Array operation executor - handles array operations
        self.array_executor = ArrayOperationExecutor(shell)

        # Function operation executor - handles function operations
        self.function_executor = FunctionOperationExecutor(shell)

        # Subshell executor - handles subshells and brace groups
        self.subshell_executor = SubshellExecutor(shell)

    # Top-level execution

    def visit_TopLevel(self, node: TopLevel) -> int:
        """Execute top-level statements."""
        exit_status = 0

        for item in node.items:
            try:
                self.shell.trap_manager.run_pending_traps()
                # Track $LINENO: each statement carries its absolute source
                # line (see ASTNode.line). Re-stamping per item also restores
                # LINENO after a function/source call returns to this list.
                if item.line is not None:
                    self.state.scope_manager.set_current_line_number(item.line)
                exit_status = self.visit(item)
                # Update $? after each top-level item
                self.state.last_exit_code = exit_status

                # Check errexit mode (set -e). Only a failure the AndOrList
                # marked eligible triggers it (POSIX exempts condition
                # contexts, non-final && / || members, and ! negation).
                if (exit_status != 0 and self.state.options.get('errexit', False)
                        and self.state.errexit_eligible):
                    if self.shell.state.is_script_mode:
                        sys.exit(exit_status)
                    break
            except LoopBreak:
                # Re-raise when a loop in an enclosing frame (eval inside a
                # loop, a seeded substitution child) is there to handle it;
                # otherwise it's an error (defensive — the break builtin
                # only raises when loop_depth > 0).
                if self.context.loop_depth > 0:
                    raise
                print("break: only meaningful in a `for', `while', or `until' loop",
                      file=sys.stderr)
                exit_status = 1
                self.state.last_exit_code = exit_status
            except LoopContinue:
                if self.context.loop_depth > 0:
                    raise
                print("continue: only meaningful in a `for', `while', or `until' loop",
                      file=sys.stderr)
                exit_status = 1
                self.state.last_exit_code = exit_status
            except SystemExit:
                # Let exit propagate
                raise
            except KeyboardInterrupt:
                # Handle Ctrl+C
                print()  # New line after ^C
                exit_status = 130
                self.state.last_exit_code = exit_status

        return exit_status

    def visit_StatementList(self, node: StatementList) -> int:
        """Execute a list of statements."""
        exit_status = 0

        for statement in node.statements:
            try:
                self.shell.trap_manager.run_pending_traps()
                # Track $LINENO: each statement carries its absolute source
                # line (see ASTNode.line). Re-stamping per statement also
                # restores LINENO after a function/source call returns here.
                if statement.line is not None:
                    self.state.scope_manager.set_current_line_number(statement.line)
                exit_status = self.visit(statement)
                # Update $? after each statement
                self.state.last_exit_code = exit_status

                # Check errexit mode
                # If errexit is set and command failed, stop executing further statements.
                # Only failures marked eligible by visit_AndOrList trigger this
                # (POSIX exempts conditions, non-final && / || members, ! negation).
                if (exit_status != 0 and self.state.options.get('errexit', False)
                        and self.state.errexit_eligible):
                    # In script mode, exit the process
                    if self.shell.state.is_script_mode:
                        sys.exit(exit_status)
                    # Otherwise, just stop executing further statements in this list
                    break
            except FunctionReturn:
                # Function return should propagate up
                raise
            except (LoopBreak, LoopContinue):
                # Re-raise if we're in a loop, otherwise it's an error.
                # (Defensive: the break/continue builtins only raise when
                # loop_depth > 0, so this path needs a context that reset
                # the depth after the raise — e.g. a trap action.)
                if self.context.loop_depth > 0:
                    raise
                exit_status = 1
                self.state.last_exit_code = exit_status
                # Don't continue executing statements after break/continue error
                break

        return exit_status

    def visit_AndOrList(self, node: AndOrList) -> int:
        """Execute pipelines with && and || operators.

        Also decides set -e eligibility per POSIX: a failure only triggers
        errexit when it comes from the FINAL pipeline of the list, that
        pipeline is not !-negated, and we are not inside a condition
        context. Non-final pipelines run with errexit suppressed so groups
        and functions inside them are exempt too.
        """
        if not node.pipelines:
            return 0

        if getattr(node, 'background', False):
            return self._execute_background_list(node)

        last = len(node.pipelines) - 1

        def run_pipeline(idx: int) -> int:
            pipeline = node.pipelines[idx]
            # $LINENO tracks per pipeline within a multi-line && / || chain.
            if pipeline.line is not None:
                self.state.scope_manager.set_current_line_number(pipeline.line)
            exempt = idx != last or getattr(pipeline, 'negated', False)
            if exempt:
                with self.context.errexit_suppressed():
                    status = self.visit(pipeline)
            else:
                status = self.visit(pipeline)
            # Record whether this (possibly failing) status may trigger
            # set -e; read by the statement-level checks. A brace group is
            # TRANSPARENT to errexit (unlike a subshell or function): the
            # eligibility its body's last command established propagates out,
            # so `set -e; { false && true; }` does NOT abort (the inner
            # non-final && member's exemption carries through). Keep what the
            # body set rather than re-marking the whole group eligible.
            if not exempt and self._pipeline_is_brace_group(pipeline):
                pass
            else:
                self.state.errexit_eligible = (
                    not exempt and self.context.errexit_suppress == 0)
            # The ERR trap fires under exactly the errexit conditions (bash);
            # $? must already be the failing status inside the action. A brace
            # group is transparent: the failing leaf command inside it already
            # fired ERR, so firing again as the status re-surfaces through the
            # enclosing brace-group pipeline would double-count (bash fires
            # once). Skip the brace-group level — the body owns the fire.
            if (status != 0 and self.state.errexit_eligible
                    and not self._pipeline_is_brace_group(pipeline)):
                self.state.last_exit_code = status
                self.shell.trap_manager.execute_err_trap(status)
            return status

        # Execute first pipeline
        exit_status = run_pipeline(0)
        self.state.last_exit_code = exit_status

        # Process remaining pipelines based on operators
        for i, op in enumerate(node.operators):
            if op == '&&' and exit_status == 0:
                # Execute next pipeline only if previous succeeded
                exit_status = run_pipeline(i + 1)
            elif op == '||' and exit_status != 0:
                # Execute next pipeline only if previous failed
                exit_status = run_pipeline(i + 1)
            # Otherwise skip this pipeline

            self.state.last_exit_code = exit_status

        return exit_status

    @staticmethod
    def _pipeline_is_brace_group(pipeline) -> bool:
        """True if *pipeline* is a single brace group `{ ...; }` (no `|`).

        Brace groups run in the current shell and are transparent to errexit;
        subshells `( )` and functions are not (handled normally).
        """
        from ..ast_nodes import BraceGroup
        cmds = getattr(pipeline, 'commands', None)
        return (cmds is not None and len(cmds) == 1
                and isinstance(cmds[0], BraceGroup))

    def _execute_background_list(self, node: AndOrList) -> int:
        """Run a whole and-or list (or a backgrounded compound command) in
        a background subshell: `a && b &`, `while ...; done &` (POSIX)."""
        from ..ast_nodes import CommandList
        foreground_copy = AndOrList()
        foreground_copy.pipelines = node.pipelines
        foreground_copy.operators = node.operators
        statements = CommandList()
        statements.statements.append(foreground_copy)
        return self.subshell_executor._execute_background_subshell(statements, [])

    def visit_Pipeline(self, node: Pipeline) -> int:
        """Execute a pipeline of commands."""
        if not node.timed:
            # Delegate to PipelineExecutor
            return self.pipeline_executor.execute(node, self.context, self)
        return self._execute_timed_pipeline(node)

    def _execute_timed_pipeline(self, node: Pipeline) -> int:
        """Run a `time`-prefixed pipeline, reporting real/user/sys afterwards.

        Times the WHOLE pipeline (bash). user/sys include forked children's CPU
        (``os.times()`` children deltas). ``time`` with no command times an empty
        pipeline (status 0). The report goes to the shell's stderr.
        """
        import os
        import time
        start_real = time.monotonic()
        start = os.times()
        status = 0
        try:
            if node.commands:
                status = self.pipeline_executor.execute(node, self.context, self)
        finally:
            real = time.monotonic() - start_real
            end = os.times()
            user = (end.user - start.user) + (end.children_user - start.children_user)
            system = (end.system - start.system) + (end.children_system - start.children_system)
            self._report_time(node, real, user, system)
        return status

    @staticmethod
    def _format_time_long(seconds: float) -> str:
        """bash default `%lR` style: `<min>m<sec>.<ms>s` (e.g. 0m0.003s)."""
        minutes = int(seconds // 60)
        return f"{minutes}m{seconds - minutes * 60:.3f}s"

    def _report_time(self, node: Pipeline, real: float, user: float, system: float) -> None:
        if node.time_posix:
            # `time -p`: POSIX format, seconds with 2 decimals.
            text = f"real {real:.2f}\nuser {user:.2f}\nsys {system:.2f}\n"
        else:
            # bash default TIMEFORMAT: a leading blank line, then m/s form.
            text = (f"\nreal\t{self._format_time_long(real)}"
                    f"\nuser\t{self._format_time_long(user)}"
                    f"\nsys\t{self._format_time_long(system)}\n")
        try:
            self.state.stderr.write(text)
            self.state.stderr.flush()
        except (OSError, ValueError):
            pass

    # Simple command execution

    def visit_SimpleCommand(self, node: SimpleCommand) -> int:
        """Execute a simple command (builtin or external)."""
        # Delegate to CommandExecutor
        return self.command_executor.execute(node, self.context)

    # Control structures

    def visit_IfConditional(self, node: IfConditional) -> int:
        """Execute if/then/else statement."""
        # Delegate to ControlFlowExecutor
        return self.control_flow_executor.execute_if(node, self.context, self)

    def visit_WhileLoop(self, node: WhileLoop) -> int:
        """Execute while loop."""
        # Delegate to ControlFlowExecutor
        return self.control_flow_executor.execute_while(node, self.context, self)

    def visit_UntilLoop(self, node: UntilLoop) -> int:
        """Execute until loop."""
        return self.control_flow_executor.execute_until(node, self.context, self)

    def visit_ForLoop(self, node: ForLoop) -> int:
        """Execute for loop."""
        # Delegate to ControlFlowExecutor
        return self.control_flow_executor.execute_for(node, self.context, self)


    def visit_CaseConditional(self, node: CaseConditional) -> int:
        """Execute case statement."""
        # Delegate to ControlFlowExecutor
        return self.control_flow_executor.execute_case(node, self.context, self)


    def visit_SubshellGroup(self, node: SubshellGroup) -> int:
        """Execute subshell group (...) in isolated environment."""
        # Delegate to SubshellExecutor
        return self.subshell_executor.execute_subshell(node, self.context)

    def visit_BraceGroup(self, node: BraceGroup) -> int:
        """Execute brace group {...} in current shell environment."""
        # Delegate to SubshellExecutor
        return self.subshell_executor.execute_brace_group(node, self.context, self)

    def visit_FunctionDef(self, node: FunctionDef) -> int:
        """Define a function."""
        # Delegate to FunctionOperationExecutor
        return self.function_executor.execute_function_def(node)

    # Additional node type implementations

    def visit_ArithmeticEvaluation(self, node: ArithmeticEvaluation) -> int:
        """Execute arithmetic command: ((expression))"""
        from ..core import UnboundVariableError
        from ..expansion.arithmetic import evaluate_arithmetic

        try:
            # Apply redirections if any
            with self.io_manager.with_redirections(node.redirects):
                result = evaluate_arithmetic(node.expression, self.shell)
                # Bash behavior: exit 0 if expression is true (non-zero)
                # exit 1 if expression is false (zero)
                return 0 if result != 0 else 1
        except UnboundVariableError as e:
            # set -u: an unset variable in `(( ))` aborts the shell (bash),
            # handled identically to a bare `$undef`.
            from .strategies import report_unbound_variable
            return report_unbound_variable(self.state, e)
        except (ValueError, ArithmeticError) as e:
            print(f"psh: ((: {e}", file=self.state.stderr)
            return 1

    def visit_CStyleForLoop(self, node: CStyleForLoop) -> int:
        """Execute C-style for loop: for ((init; cond; update))"""
        from ..core import UnboundVariableError
        try:
            # Delegate to ControlFlowExecutor
            return self.control_flow_executor.execute_c_style_for(node, self.context, self)
        except UnboundVariableError as e:
            # set -u: an unset variable in the init/condition/update arithmetic
            # aborts the shell (bash), like a bare `$undef`.
            from .strategies import report_unbound_variable
            return report_unbound_variable(self.state, e)

    def visit_SelectLoop(self, node: SelectLoop) -> int:
        """Execute select loop for interactive menu selection."""
        # Delegate to ControlFlowExecutor
        return self.control_flow_executor.execute_select(node, self.context, self)


    def visit_EnhancedTestStatement(self, node: EnhancedTestStatement) -> int:
        """Execute enhanced test: [[ expression ]]"""
        from ..core import UnboundVariableError
        from ..expansion.arithmetic import ShellArithmeticError
        from .enhanced_test_evaluator import TestExpressionEvaluator

        # with_redirections also owns any process substitutions used as
        # redirect targets (cleaned up when the statement finishes).
        with self.io_manager.with_redirections(node.redirects):
            try:
                evaluator = TestExpressionEvaluator(self.shell)
                result = evaluator.evaluate(node.expression)
                return 0 if result else 1
            except UnboundVariableError as e:
                # set -u: an unset variable in a numeric-operator operand
                # aborts the shell (bash), like a bare `$undef`.
                from .strategies import report_unbound_variable
                return report_unbound_variable(self.state, e)
            except ShellArithmeticError as e:
                # A -eq/-lt/... operand that fails to evaluate ([[ 08 -eq 8 ]],
                # [[ @@ -eq 2 ]]): bash reports the error and the statement
                # fails with status 1 — execution continues.
                print(f"psh: [[: {e}", file=self.state.stderr)
                return 1
            except (ValueError, TypeError, OSError) as e:
                print(f"psh: [[: {e}", file=sys.stderr)
                return 2  # Syntax error

    # Array operations

    def visit_ArrayInitialization(self, node: ArrayInitialization) -> int:
        """Execute array initialization: arr=(a b c)"""
        # Delegate to ArrayOperationExecutor
        return self.array_executor.execute_array_initialization(node)

    def visit_ArrayElementAssignment(self, node: ArrayElementAssignment) -> int:
        """Execute array element assignment: arr[i]=value"""
        # Delegate to ArrayOperationExecutor
        return self.array_executor.execute_array_element_assignment(node)

    # Fallback for unimplemented nodes

    def generic_visit(self, node: ASTNode) -> int:
        """Fallback for unimplemented node types."""
        node_name = type(node).__name__
        print(f"ExecutorVisitor: Unimplemented node type: {node_name}",
              file=sys.stderr)
        return 1
