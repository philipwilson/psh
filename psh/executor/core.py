"""
Executor visitor that executes AST nodes using the visitor pattern.

This visitor provides a clean architecture for command execution while
maintaining compatibility with the existing execution engine.
"""

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, Optional

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
    # Root
    Program,
    SelectLoop,
    SimpleCommand,
    StatementList,
    # Other
    SubshellGroup,
    UntilLoop,
    WhileLoop,
)
from ..core import LoopBreak, LoopContinue
from .array import ArrayOperationExecutor
from .command import CommandExecutor
from .context import ExecutionContext
from .control_flow import ControlFlowExecutor
from .function import FunctionOperationExecutor
from .pipeline import PipelineExecutor
from .subshell import SubshellExecutor

if TYPE_CHECKING:
    from ..shell import Shell


@dataclass(frozen=True)
class SequenceContext:
    """Selects the control-flow policy for a statement sequence.

    The program root and a nested statement list share the SAME common
    sequencing (pending traps, ``$LINENO`` restamp, ``$?`` update, ``set -e``
    exit-vs-break), and differ on exactly three control-flow signals, each a
    named flag here so the divergence is deliberate rather than inferred from
    which container class reached the visitor:

    * ``catch_keyboard_interrupt`` — the root catches ``^C`` (prints a newline,
      sets ``$?`` = 130, and continues to the next statement); a nested list
      lets ``KeyboardInterrupt`` propagate.
    * ``announce_out_of_loop`` — on a ``break``/``continue`` that escapes with
      ``loop_depth == 0``, the root prints the "only meaningful in a loop"
      diagnostic; a nested list fails silently.
    * ``stop_on_out_of_loop`` — after that out-of-loop ``break``/``continue``
      the root continues to the next statement, while a nested list stops.

    ``FunctionReturn`` and ``SystemExit`` propagate from both (the shared loop
    catches neither).
    """
    catch_keyboard_interrupt: bool
    announce_out_of_loop: bool
    stop_on_out_of_loop: bool


# The parsed-program root: report an out-of-loop
# break/continue and keep going; own ^C handling.
ROOT_SEQUENCE = SequenceContext(
    catch_keyboard_interrupt=True,
    announce_out_of_loop=True,
    stop_on_out_of_loop=False,
)
# A nested command body (loop/if/function/group interior): fail an out-of-loop
# break/continue silently and stop the list; let ^C propagate.
NESTED_SEQUENCE = SequenceContext(
    catch_keyboard_interrupt=False,
    announce_out_of_loop=False,
    stop_on_out_of_loop=True,
)


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

    # Top-level and statement-list execution

    def visit_Program(self, node: Program) -> int:
        """Execute a parsed program (the canonical root)."""
        return self._execute_sequence(node.statements, context=ROOT_SEQUENCE)

    def visit_StatementList(self, node: StatementList) -> int:
        """Execute a nested statement list (loop/if/function/group body)."""
        return self._execute_sequence(node.statements, context=NESTED_SEQUENCE)

    def _execute_sequence(self, statements: Iterable[ASTNode], *,
                          context: SequenceContext) -> int:
        """Execute a sequence of statements — the shared mechanics behind the
        program root and every nested statement list.

        Common to both: run pending signal traps at each statement boundary,
        restamp ``$LINENO`` from the statement's absolute source line, update
        ``$?``, and honour ``set -e`` (in script mode a triggering failure
        exits the process; otherwise it stops the sequence). Only failures
        ``visit_AndOrList`` marked errexit-eligible trigger it (POSIX exempts
        condition contexts, non-final ``&&``/``||`` members, and ``!``
        negation). The control-flow-signal divergences between the two
        contexts are named on ``context`` (see :class:`SequenceContext`);
        ``FunctionReturn`` and ``SystemExit`` propagate from both.
        """
        exit_status = 0

        for statement in statements:
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

                if (exit_status != 0 and self.state.options.get('errexit', False)
                        and self.state.errexit_eligible):
                    # Script mode exits the process; otherwise stop the sequence.
                    if self.shell.state.is_script_mode:
                        sys.exit(exit_status)
                    break
            except (LoopBreak, LoopContinue) as e:
                # A break/continue reaching here with loop_depth > 0 belongs to
                # an enclosing loop frame (eval inside a loop, a seeded
                # substitution child) — re-raise so it handles it. (Defensive:
                # the break/continue builtins only raise when loop_depth > 0,
                # so the loop_depth == 0 branch needs a context that reset the
                # depth after the raise — e.g. a trap action.)
                if self.context.loop_depth > 0:
                    raise
                if context.announce_out_of_loop:
                    keyword = "break" if isinstance(e, LoopBreak) else "continue"
                    print(f"{keyword}: only meaningful in a `for', `while', or `until' loop",
                          file=sys.stderr)
                exit_status = 1
                self.state.last_exit_code = exit_status
                if context.stop_on_out_of_loop:
                    break
            except KeyboardInterrupt:
                if not context.catch_keyboard_interrupt:
                    raise
                print()  # New line after ^C
                exit_status = 130
                self.state.last_exit_code = exit_status

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
        from ..ast_nodes import StatementList
        foreground_copy = AndOrList()
        foreground_copy.pipelines = node.pipelines
        foreground_copy.operators = node.operators
        statements = StatementList()
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
            # PipelineExecutor handles the empty pipeline (`time` alone
            # times a null command, status 0) and any `!` negation
            # (`time !` -> 1) uniformly.
            status = self.pipeline_executor.execute(node, self.context, self)
        finally:
            real = time.monotonic() - start_real
            end = os.times()
            # user/sys are process-wide os.times() children deltas. CAVEAT:
            # a background job reaped concurrently during this pipeline
            # contaminates the deltas (its CPU is attributed here). Per-child
            # rusage via wait4() is a later phase (F15 covers the report
            # FORMAT only); the values may over-count under concurrent bg work.
            user = (end.user - start.user) + (end.children_user - start.children_user)
            system = (end.system - start.system) + (end.children_system - start.children_system)
            self._report_time(node, real, user, system)
        return status

    @staticmethod
    def _fmt_time_directive(seconds: float, precision: int, long_form: bool) -> str:
        """One R/U/S time value for TIMEFORMAT: ``[NNm]SS.FFFs`` in long form
        (``%lR`` -> ``0m0.003s``), otherwise plain seconds (``%R`` -> ``0.003``).
        ``precision`` is the digit count after the decimal (0-3)."""
        if long_form:
            minutes = int(seconds // 60)
            return f"{minutes}m{seconds - minutes * 60:.{precision}f}s"
        return f"{seconds:.{precision}f}"

    def _format_timeformat(self, fmt: str, real: float, user: float,
                           system: float) -> str:
        """Render a bash ``TIMEFORMAT`` string.

        Directives: ``%%`` (literal ``%``), ``%[p][l]R/U/S`` (real/user/sys —
        optional precision ``p`` 0-3 default 3, optional ``l`` long form), and
        ``%P`` (CPU percentage ``(user+sys)/real*100`` — 2 decimals, and bash
        accepts NO precision/``l`` modifier on it). An unrecognized directive
        (or a trailing ``%``) keeps a literal ``%`` — a lenient divergence from
        bash's "invalid format character" error for malformed specs like
        ``%3P``, which is outside the documented directive set.
        """
        out = []
        i, n = 0, len(fmt)
        while i < n:
            if fmt[i] != '%':
                out.append(fmt[i])
                i += 1
                continue
            j = i + 1
            if j < n and fmt[j] == '%':
                out.append('%')
                i = j + 1
                continue
            precision: Optional[int] = None
            if j < n and fmt[j].isdigit():
                precision = int(fmt[j])
                j += 1
            long_form = False
            if j < n and fmt[j] == 'l':
                long_form = True
                j += 1
            if j < n and fmt[j] in ('R', 'U', 'S'):
                p = 3 if precision is None else max(0, min(3, precision))
                value = {'R': real, 'U': user, 'S': system}[fmt[j]]
                out.append(self._fmt_time_directive(value, p, long_form))
                i = j + 1
            elif (j < n and fmt[j] == 'P'
                  and precision is None and not long_form):
                pct = (user + system) / real * 100 if real > 0 else 0.0
                out.append(f"{pct:.2f}")
                i = j + 1
            else:
                # Unrecognized/malformed directive: keep the literal '%'.
                out.append('%')
                i += 1
        return ''.join(out)

    def _report_time(self, node: Pipeline, real: float, user: float, system: float) -> None:
        if node.time_posix:
            # `time -p`: POSIX format, seconds with 2 decimals. Independent of
            # TIMEFORMAT (bash: -p forces this format).
            text = f"real {real:.2f}\nuser {user:.2f}\nsys {system:.2f}\n"
        else:
            # Honor $TIMEFORMAT (F15). Passing bash's default format as the
            # get_variable default makes UNSET -> that default; an EMPTY value
            # stays "" -> no report at all; any other value is parsed. bash
            # appends a trailing newline after the formatted string.
            default_fmt = "\nreal\t%3lR\nuser\t%3lU\nsys\t%3lS"
            fmt = self.state.get_variable('TIMEFORMAT', default_fmt)
            if fmt == "":
                return
            text = self._format_timeformat(fmt, real, user, system) + "\n"
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
        from ..core import NamerefCycleError, ReadonlyVariableError, UnboundVariableError
        from ..expansion.arithmetic import evaluate_arithmetic

        # bash runs the DEBUG trap before a (( )) command, with
        # $BASH_COMMAND = its own text.
        self.shell.trap_manager.set_bash_command(f"(({node.expression}))")
        self.shell.trap_manager.execute_debug_trap()

        # Apply redirections if any (a bad target prints bash's diagnostic
        # and yields False, so the arithmetic does not run — status 1).
        # Error handling sits INSIDE the redirection scope so diagnostics
        # honour `(( ... )) 2>/dev/null` like bash (and like the
        # visit_EnhancedTestStatement sibling).
        with self.io_manager.guarded_redirections(node.redirects) as applied:
            if not applied:
                return 1
            try:
                result = evaluate_arithmetic(node.expression, self.shell)
                # Bash behavior: exit 0 if expression is true (non-zero)
                # exit 1 if expression is false (zero)
                return 0 if result != 0 else 1
            except UnboundVariableError as e:
                # set -u: an unset variable in `(( ))` aborts the shell
                # (bash), handled identically to a bare `$undef`.
                from .strategies import report_unbound_variable
                return report_unbound_variable(self.state, e)
            except (ReadonlyVariableError, NamerefCycleError) as e:
                # `readonly r; (( r=9 ))`: bash reports "r: readonly
                # variable", the command fails with status 1, and execution
                # CONTINUES — this must not leak to the buffered-command
                # guard (which would print "unexpected error" and abort a
                # -c list).
                from .strategies import report_assignment_error
                return report_assignment_error(self.state, e)
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
        from ..core import NamerefCycleError, ReadonlyVariableError, UnboundVariableError
        from ..expansion.arithmetic import ShellArithmeticError
        from .enhanced_test_evaluator import TestExpressionEvaluator

        # bash runs the DEBUG trap before a [[ ]] command, with
        # $BASH_COMMAND = its own text (node stamped; rendered lazily).
        self.shell.trap_manager.set_bash_command(node)
        self.shell.trap_manager.execute_debug_trap()

        # guarded_redirections also owns any process substitutions used as
        # redirect targets (cleaned up when the statement finishes). A bad
        # redirect target prints bash's diagnostic and yields False, so the
        # test does not run — status 1, `|| fallback` runs.
        with self.io_manager.guarded_redirections(node.redirects) as applied:
            if not applied:
                return 1
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
            except (ReadonlyVariableError, NamerefCycleError) as e:
                # `[[ $((r=9)) -eq 9 ]]` with readonly r: report the
                # assignment failure and fail the statement (status 1)
                # instead of leaking an "unexpected error" abort.
                from .strategies import report_assignment_error
                return report_assignment_error(self.state, e)
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
