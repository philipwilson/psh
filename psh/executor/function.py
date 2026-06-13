"""
Function operations support for the PSH executor.

This module handles function definition and execution operations.
"""

from typing import TYPE_CHECKING, List, Optional

from ..core import LoopBreak, LoopContinue, UnboundVariableError
from ..core.exceptions import FunctionReturn

if TYPE_CHECKING:
    from psh.visitor import ASTVisitor

    from ..ast_nodes import FunctionDef, Redirect
    from ..shell import Shell
    from .context import ExecutionContext


class FunctionOperationExecutor:
    """
    Handles function definition and execution.

    This class encapsulates logic for:
    - Function definition (execute_function_def)
    - Function execution (execute_function_call): positional parameter
      setup, function-scoped redirections, running the body, and
      handling `return` / control-flow exceptions
    """

    def __init__(self, shell: 'Shell'):
        """Initialize the function operation executor with a shell instance."""
        self.shell = shell
        self.function_manager = shell.function_manager

    def execute_function_def(self, node: 'FunctionDef') -> int:
        """
        Define a function.

        Args:
            node: The FunctionDef AST node

        Returns:
            Exit status code (0 for success)
        """
        self.function_manager.define_function(node.name, node.body,
                                              redirects=node.redirects)
        return 0

    def execute_function_call(self, name: str, args: List[str],
                             context: 'ExecutionContext',
                             visitor: 'ASTVisitor[int]',
                             redirects: Optional[List['Redirect']] = None) -> int:
        """
        Execute a function call.

        Args:
            name: Function name
            args: Function arguments (including $0)
            context: Execution context
            visitor: The visitor to use for executing the function body
            redirects: Optional redirections to apply

        Returns:
            Exit status code
        """
        func = self.function_manager.get_function(name)
        if not func:
            return 127  # Command not found

        # Extract the actual body from the Function object
        func_body = func.body

        # Save current context
        old_function = context.current_function
        old_positional_params = self.shell.state.positional_params[:]


        # Set up function context
        context.current_function = name

        # Push new variable scope for the function
        self.shell.state.scope_manager.push_scope(name)

        # Set up positional parameters ($1, $2, etc.). $#/$@/$* need no
        # separate bookkeeping: every special-parameter read derives from
        # state.positional_params (state.get_special_variable), so this
        # one assignment IS the whole swap. (Until 2026-06-13 this also
        # wrote shell variables literally named '#', '@' and '*' — never
        # read by anything, but they leaked into `set` output.)
        self.shell.state.positional_params = args

        # NOTE: $0 is deliberately NOT changed on function entry — bash keeps
        # $0 as the script/shell name inside functions (${FUNCNAME[0]} is the
        # function name). The function name lives on function_stack below.

        # Push function onto stack for return builtin
        self.shell.state.function_stack.append(name)

        try:
            # Execute function body, applying any definition-attached
            # redirections (f() { ...; } > file) at each call (bash).
            if func.redirects:
                with self.shell.io_manager.with_redirections(func.redirects):
                    exit_code = visitor.visit(func_body)
            else:
                exit_code = visitor.visit(func_body)
            return exit_code
        except FunctionReturn as fr:
            # Handle return statement
            return fr.exit_code
        except (LoopBreak, LoopContinue):
            # Let break/continue exceptions propagate to calling loop context
            raise
        except UnboundVariableError:
            # Let unbound variable errors propagate
            raise
        except Exception as e:
            # Last-resort guard: a defect inside the function body. Keep the
            # shell alive (or re-raise under strict-errors) — see
            # report_internal_defect for the policy.
            from ..core import report_internal_defect
            return report_internal_defect(
                self.shell.state, e, prefix=f"{name}: ",
                stream=self.shell.state.stderr)
        finally:
            # Pop function scope
            self.shell.state.scope_manager.pop_scope()

            # Pop function from stack
            if self.shell.state.function_stack:
                self.shell.state.function_stack.pop()

            # Restore context (restoring positional_params restores
            # $#/$@/$* with it — they are derived, never stored)
            context.current_function = old_function
            self.shell.state.positional_params = old_positional_params
