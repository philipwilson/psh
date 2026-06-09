"""
Executor visitor that executes AST nodes using the visitor pattern.

This visitor provides a clean architecture for command execution while
maintaining compatibility with the existing execution engine.
"""

import sys

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
    BreakStatement,
    CaseConditional,
    ContinueStatement,
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
from ..builtins import FunctionReturn
from ..core import LoopBreak, LoopContinue
from .array import ArrayOperationExecutor
from .command import CommandExecutor
from .context import ExecutionContext
from .control_flow import ControlFlowExecutor
from .function import FunctionOperationExecutor
from .pipeline import PipelineExecutor
from .subshell import SubshellExecutor


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

        # Command executor - handles simple command execution
        self.command_executor = CommandExecutor(shell)
        self.command_executor._visitor = self

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
                exit_status = self.visit(item)
                # Update $? after each top-level item
                self.state.last_exit_code = exit_status

                # Check errexit mode (set -e)
                if exit_status != 0 and self.state.options.get('errexit', False):
                    if hasattr(self.shell, 'is_script_mode') and self.shell.is_script_mode:
                        sys.exit(exit_status)
                    break
            except LoopBreak:
                # Break at top level is an error
                print("break: only meaningful in a `for' or `while' loop", file=sys.stderr)
                exit_status = 1
                self.state.last_exit_code = exit_status
            except LoopContinue:
                # Continue at top level is an error
                print("continue: only meaningful in a `for' or `while' loop", file=sys.stderr)
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
                exit_status = self.visit(statement)
                # Update $? after each statement
                self.state.last_exit_code = exit_status

                # Check errexit mode
                # If errexit is set and command failed, stop executing further statements
                if exit_status != 0 and self.state.options.get('errexit', False):
                    # In script mode, exit the process
                    if hasattr(self.shell, 'is_script_mode') and self.shell.is_script_mode:
                        sys.exit(exit_status)
                    # Otherwise, just stop executing further statements in this list
                    break
            except FunctionReturn:
                # Function return should propagate up
                raise
            except (LoopBreak, LoopContinue):
                # Re-raise if we're in a loop, otherwise it's an error
                if self.context.loop_depth > 0:
                    raise
                # Not in a loop - this was already reported by visit_BreakStatement/visit_ContinueStatement
                exit_status = 1
                self.state.last_exit_code = exit_status
                # Don't continue executing statements after break/continue error
                break

        return exit_status

    def visit_AndOrList(self, node: AndOrList) -> int:
        """Execute pipelines with && and || operators."""
        if not node.pipelines:
            return 0

        # Execute first pipeline
        exit_status = self.visit(node.pipelines[0])
        self.state.last_exit_code = exit_status

        # Process remaining pipelines based on operators
        for i, op in enumerate(node.operators):
            if op == '&&' and exit_status == 0:
                # Execute next pipeline only if previous succeeded
                exit_status = self.visit(node.pipelines[i + 1])
            elif op == '||' and exit_status != 0:
                # Execute next pipeline only if previous failed
                exit_status = self.visit(node.pipelines[i + 1])
            # Otherwise skip this pipeline

            self.state.last_exit_code = exit_status

        return exit_status

    def visit_Pipeline(self, node: Pipeline) -> int:
        """Execute a pipeline of commands."""
        # Delegate to PipelineExecutor
        return self.pipeline_executor.execute(node, self.context, self)

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


    def visit_BreakStatement(self, node: BreakStatement) -> int:
        """Execute break statement."""
        # Delegate to ControlFlowExecutor
        return self.control_flow_executor.execute_break(node, self.context)

    def visit_ContinueStatement(self, node: ContinueStatement) -> int:
        """Execute continue statement."""
        # Delegate to ControlFlowExecutor
        return self.control_flow_executor.execute_continue(node, self.context)

    def visit_SubshellGroup(self, node: SubshellGroup) -> int:
        """Execute subshell group (...) in isolated environment."""
        # Delegate to SubshellExecutor
        return self.subshell_executor.execute_subshell(node, self.context, self)

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
        from ..arithmetic import evaluate_arithmetic

        try:
            # Apply redirections if any
            with self.io_manager.with_redirections(node.redirects):
                result = evaluate_arithmetic(node.expression, self.shell)
                # Bash behavior: exit 0 if expression is true (non-zero)
                # exit 1 if expression is false (zero)
                return 0 if result != 0 else 1
        except (ValueError, ArithmeticError) as e:
            print(f"psh: ((: {e}", file=sys.stderr)
            return 1

    def visit_CStyleForLoop(self, node: CStyleForLoop) -> int:
        """Execute C-style for loop: for ((init; cond; update))"""
        # Delegate to ControlFlowExecutor
        return self.control_flow_executor.execute_c_style_for(node, self.context, self)

    def visit_SelectLoop(self, node: SelectLoop) -> int:
        """Execute select loop for interactive menu selection."""
        # Delegate to ControlFlowExecutor
        return self.control_flow_executor.execute_select(node, self.context, self)


    def visit_EnhancedTestStatement(self, node: EnhancedTestStatement) -> int:
        """Execute enhanced test: [[ expression ]]"""
        # Delegate to shell's existing implementation
        return self.shell.execute_enhanced_test_statement(node)

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
