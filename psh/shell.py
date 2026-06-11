import os
import sys

from .ast_nodes import (
    EnhancedTestStatement,
    StatementList,
    TopLevel,
)
from .builtins import registry as builtin_registry
from .core import ShellState
from .core.functions import FunctionManager
from .executor.job_control import JobManager
from .expansion import ExpansionManager
from .expansion.aliases import AliasManager
from .interactive import InteractiveManager
from .io_redirect import IOManager
from .scripting.base import ScriptManager


class Shell:
    def __init__(self, args=None, script_name=None, debug_ast=False, debug_tokens=False, debug_scopes=False,
                 debug_expansion=False, debug_expansion_detail=False, debug_exec=False, debug_exec_fork=False,
                 norc=False, rcfile=None, validate_only=False, format_only=False, metrics_only=False,
                 security_only=False, lint_only=False, parent_shell=None, ast_format=None,
                 force_interactive=False):
        # Initialize state
        self.state = ShellState(args, script_name, debug_ast,
                              debug_tokens, debug_scopes, debug_expansion, debug_expansion_detail,
                              debug_exec, debug_exec_fork, norc, rcfile)

        # Store validation and visitor modes
        self.validate_only = validate_only
        self.format_only = format_only
        self.metrics_only = metrics_only
        self.security_only = security_only
        self.lint_only = lint_only
        self.ast_format = ast_format

        # Set shell reference in scope manager for arithmetic evaluation
        self.state.scope_manager.set_shell(self)

        self._setup_compatibility_properties()

        self.builtin_registry = builtin_registry

        # Initialize basic managers first
        self.alias_manager = AliasManager()
        self.function_manager = FunctionManager()
        self.job_manager = JobManager()

        # Connect job manager to shell state for option checking
        self.job_manager.set_shell_state(self.state)

        # Inherit from parent shell if provided - MUST be done before creating other managers
        if parent_shell:
            self.env = parent_shell.env.copy()
            # Copy global variables from parent's scope manager
            for name, var in parent_shell.state.scope_manager.global_scope.variables.items():
                # Copy the entire Variable object to preserve attributes
                self.state.scope_manager.global_scope.variables[name] = var.copy()
            # Copy all scopes to inherit local variables and their attributes
            for scope in parent_shell.state.scope_manager.scope_stack[1:]:  # Skip global, already copied
                new_scope = scope.copy()
                self.state.scope_manager.scope_stack.append(new_scope)
            self.function_manager = parent_shell.function_manager.copy()
            self.alias_manager = parent_shell.alias_manager.copy()
            # Copy positional parameters for subshells
            self.state.positional_params = parent_shell.state.positional_params.copy()
            # Inherit shell options (set -e, pipefail, ...) and $? — a
            # subshell starts with the parent's option state and last exit
            # code (bash). Mode flags recomputed later in __init__
            # ('interactive', 'stdin_mode', 'emacs') overwrite their copies.
            self.state.options.update(parent_shell.state.options)
            self.state.last_exit_code = parent_shell.state.last_exit_code
            self.state.is_script_mode = parent_shell.state.is_script_mode
            self.state.pipestatus = list(parent_shell.state.pipestatus)
            self.state.initial_ppid = parent_shell.state.initial_ppid
            self.state.shell_pid = parent_shell.state.shell_pid
            # Sync all exported variables (including local exports) to environment
            self.state.scope_manager.sync_exports_to_environment(self.env)
            # Note: We don't copy jobs - those are shell-specific

        # Now create managers that need references to the shell
        # These will get the correct function_manager reference
        self.expansion_manager = ExpansionManager(self)
        self.io_manager = IOManager(self)
        self.script_manager = ScriptManager(self)
        self.interactive_manager = InteractiveManager(self)

        # Single shared process launcher — the one fork/job-control path for
        # pipelines, external commands, background builtins/functions and
        # subshells (executors must not build their own).
        from .executor.process_launcher import ProcessLauncher
        self.process_launcher = ProcessLauncher(
            self.state, self.job_manager, self.io_manager,
            self.interactive_manager.signal_manager)

        # Initialize history expander
        from .interactive.history_expansion import HistoryExpander
        self.history_expander = HistoryExpander(self)

        # Active parser selection ('recursive_descent' or 'combinator')
        self._active_parser = 'recursive_descent'
        if parent_shell and hasattr(parent_shell, '_active_parser'):
            self._active_parser = parent_shell._active_parser
        elif os.environ.get('PSH_TEST_PARSER'):
            self._active_parser = os.environ['PSH_TEST_PARSER']

        # Initialize trap manager
        from .core import TrapManager
        self.trap_manager = TrapManager(self)

        # Stream references (shell.stdout/.stderr/.stdin) delegate to
        # ShellState properties that track the LIVE sys.* streams unless a
        # caller installs custom ones (capture buffers, subshell pipes).
        # Do not snapshot sys.stdout here — that would freeze init-time
        # objects and miss later replacements.

        # The ExecutorVisitor currently executing, if any. Nested execution
        # (eval, source) reuses it so loop depth and function context carry
        # into the nested commands — `eval break` must break the outer loop.
        self._current_executor = None

        # Determine interactive mode
        is_interactive = force_interactive or sys.stdin.isatty()
        self.state.options['interactive'] = is_interactive

        # stdin_mode: True when reading from stdin (no script file argument)
        # Will be set to False by __main__.py when a script file is given
        self.state.options['stdin_mode'] = not self.state.is_script_mode

        # Load history only for interactive shells (bash doesn't load history in non-interactive mode)
        if is_interactive:
            self.interactive_manager.load_history()

        # Set emacs mode based on interactive status (bash behavior)
        # Interactive: emacs on (for line editing), Non-interactive: emacs off
        self.state.options['emacs'] = is_interactive and not self.is_script_mode

        if not self.is_script_mode and is_interactive and not self.norc:
            from .interactive import load_rc_file
            load_rc_file(self)

    def _setup_compatibility_properties(self):
        """Configure which attribute names delegate to ShellState."""
        self._state_properties = [
            'env', 'variables', 'positional_params', 'script_name',
            'is_script_mode', 'debug_ast', 'debug_tokens', 'norc', 'rcfile',
            'last_exit_code', 'last_bg_pid', 'foreground_pgid', 'command_number',
            'history', 'history_file', 'max_history_size', 'history_index',
            'current_line', 'edit_mode', 'function_stack', 'in_forked_child',
            'stdout', 'stderr', 'stdin'
        ]

    def __getattr__(self, name):
        """Delegate attribute access to ShellState."""
        if hasattr(self.state, name):
            return getattr(self.state, name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def __setattr__(self, name, value):
        """Delegate attribute setting to ShellState for state properties."""
        if name in ('state', '_state_properties', 'builtin_registry',
                   'alias_manager', 'function_manager', 'job_manager', 'expansion_manager',
                   'io_manager', 'script_manager', 'interactive_manager',
                   'history_expander', '_active_parser'):
            super().__setattr__(name, value)
        elif hasattr(self, '_state_properties') and name in self._state_properties:
            setattr(self.state, name, value)
        else:
            super().__setattr__(name, value)

    def execute_command_list(self, command_list: StatementList):
        """Execute a command list"""
        return self._execute_with_visitor(command_list)

    def execute_toplevel(self, toplevel: TopLevel):
        """Execute a top-level script/input containing functions and commands."""
        return self._execute_with_visitor(toplevel)

    def _execute_with_visitor(self, node):
        """Execute an AST node, reusing the active executor when nested.

        Nested execution (eval, source, trap actions) must share the caller's
        ExecutorVisitor: a fresh visitor starts with loop_depth=0, which used
        to make `eval break` report "only meaningful in a loop" instead of
        breaking the enclosing loop.
        """
        if self._current_executor is not None:
            return self._current_executor.visit(node)

        from .executor import ExecutorVisitor
        executor = ExecutorVisitor(self)
        # A forked subshell created inside a set -e-suppressed context
        # (condition, non-final && / || member) seeds the suppression into
        # its fresh visitor so the exemption crosses the fork, as in bash.
        executor.context.errexit_suppress = getattr(self, '_errexit_suppress_seed', 0)
        self._current_executor = executor
        try:
            return executor.visit(node)
        finally:
            self._current_executor = None

    def execute_enhanced_test_statement(self, test_stmt: EnhancedTestStatement) -> int:
        """Execute an enhanced test statement [[...]]."""
        from .executor import TestExpressionEvaluator

        # Apply redirections if present
        if test_stmt.redirects:
            saved_fds = self.io_manager.apply_redirections(test_stmt.redirects)
        else:
            saved_fds = None

        try:
            evaluator = TestExpressionEvaluator(self)
            result = evaluator.evaluate(test_stmt.expression)
            return 0 if result else 1
        except (ValueError, TypeError, OSError) as e:
            print(f"psh: [[: {e}", file=sys.stderr)
            return 2  # Syntax error
        finally:
            if saved_fds:
                self.io_manager.restore_redirections(saved_fds)

    def _handle_visitor_mode_for_command(self, command: str) -> int:
        """Handle visitor modes for -c commands."""
        # Parse the command to get AST
        try:
            from .lexer import tokenize
            from .parser import parse

            tokens = tokenize(command)
            ast = parse(tokens)

            return self._apply_visitor_mode(ast)
        except (ValueError, TypeError) as e:
            print(f"Error parsing command: {e}", file=sys.stderr)
            return 1

    def _handle_visitor_mode_for_script(self, script_path: str) -> int:
        """Handle visitor modes for script files."""
        try:
            # Read and parse the script file
            with open(script_path, 'r') as f:
                content = f.read()

            from .lexer import tokenize
            from .parser import parse

            tokens = tokenize(content)
            ast = parse(tokens)

            return self._apply_visitor_mode(ast)
        except FileNotFoundError:
            print(f"psh: {script_path}: No such file or directory", file=sys.stderr)
            return 1
        except (ValueError, TypeError, OSError) as e:
            print(f"Error processing script: {e}", file=sys.stderr)
            return 1

    def _apply_visitor_mode(self, ast) -> int:
        """Apply the appropriate visitor mode to the AST."""
        if self.validate_only:
            from .visitor import EnhancedValidatorVisitor
            validator = EnhancedValidatorVisitor()
            validator.visit(ast)
            print(validator.get_summary())
            error_count = sum(1 for i in validator.issues if i.severity.value == 'error')
            return 1 if error_count > 0 else 0

        if self.format_only:
            from .visitor import FormatterVisitor
            formatter = FormatterVisitor()
            formatted_code = formatter.visit(ast)
            print(formatted_code)
            return 0

        if self.metrics_only:
            from .visitor import MetricsVisitor
            metrics = MetricsVisitor()
            metrics.visit(ast)
            print(metrics.get_summary())
            return 0

        if self.security_only:
            from .visitor import SecurityVisitor
            security = SecurityVisitor()
            security.visit(ast)
            print(security.get_summary())
            issue_count = len(security.issues)
            return 1 if issue_count > 0 else 0

        if self.lint_only:
            from .visitor import LinterVisitor
            linter = LinterVisitor()
            linter.visit(ast)
            print(linter.get_summary())
            issue_count = len(linter.issues)
            return 1 if issue_count > 0 else 0

        return 0

    @property
    def active_parser(self) -> str:
        """Name of the active parser implementation.

        Either 'recursive_descent' (default) or 'combinator'. Public accessor so
        callers do not reach into the private `_active_parser` field.
        """
        return self._active_parser

    @active_parser.setter
    def active_parser(self, name: str) -> None:
        self._active_parser = name

    def add_history(self, command: str) -> None:
        """Record a command in the interactive history.

        Public entry point so callers do not walk
        interactive_manager.history_manager.add_to_history directly.
        """
        self.interactive_manager.history_manager.add_to_history(command)

    def run_command(self, command_string: str, add_to_history=True):
        """Execute a command string using the unified input system."""
        from .scripting.input_sources import StringInput

        # Use the unified execution system for consistency
        input_source = StringInput(command_string, "<command>")
        return self.script_manager.execute_from_source(input_source, add_to_history)



