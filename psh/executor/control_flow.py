"""
Control flow execution support for the PSH executor.

This module handles execution of control structures including:
- If/elif/else conditionals
 - While loops
 - Until loops
- For loops (standard and C-style)
- Case statements
- Select loops

(break/continue themselves are ordinary builtins — psh/builtins/loop_control.py
— that raise LoopBreak/LoopContinue; the loops here catch them.)
"""
import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING, Iterator, List, Optional, Union

from ..core import LoopBreak, LoopContinue, NamerefCycleError, ReadonlyVariableError, report_internal_defect
from ..core.options import xtrace_quote
from ..expansion.arithmetic import evaluate_arithmetic
from ..lexer.unicode_support import is_valid_name

if TYPE_CHECKING:
    from psh.visitor import ASTVisitor

    from ..ast_nodes import (
        CaseConditional,
        CStyleForLoop,
        ForLoop,
        IfConditional,
        SelectLoop,
        UntilLoop,
        WhileLoop,
    )
    from ..shell import Shell
    from .context import ExecutionContext


class ControlFlowExecutor:
    """
    Handles execution of control flow structures.

    This class encapsulates all logic for executing control structures
    including conditionals, loops, and flow control statements.
    """

    def __init__(self, shell: 'Shell'):
        """Initialize the control flow executor with a shell instance."""
        self.shell = shell
        self.state = shell.state
        self.expansion_manager = shell.expansion_manager
        self.io_manager = shell.io_manager

    # ------------------------------------------------------------------
    # Shared scaffolding helpers
    #
    # Every compound construct (if/while/until/for/c-style-for/case/select)
    # shares the same boilerplate: apply the node's redirections around the
    # whole body, neutralize the enclosing pipeline context while running the
    # body, track loop nesting depth, and translate break/continue level
    # counts as they unwind through nested loops. These helpers own that
    # boilerplate so each construct's method reads as its real control logic.
    # ------------------------------------------------------------------

    @contextmanager
    def _compound_redirections(self, node) -> Iterator[bool]:
        """Apply the construct's redirections around its whole body.

        Redirects on a compound command apply to every command in the body
        and are restored when the body finishes. Delegates to the io manager's
        redirect-error chokepoint (``guarded_redirections``): a bad redirect
        target prints bash's diagnostic and yields ``False``, and the caller
        must then skip the body and ``return 1`` (so ``|| fallback`` runs, and
        under ``set -e`` the failing construct still aborts). Yields ``True``
        when redirects applied cleanly.
        """
        with self.io_manager.guarded_redirections(node.redirects) as applied:
            yield applied

    @contextmanager
    def _pipeline_context_disabled(self, context: 'ExecutionContext') -> Iterator[None]:
        """Run the body as if it were NOT a pipeline member.

        A compound command can itself be a pipeline member (``for ...; done |
        cat``); the compound runs in a forked subshell. Inside its body,
        external commands must fork normally rather than exec-replacing that
        subshell, so ``in_pipeline`` is cleared for the duration of the body
        and restored afterward.
        """
        old_pipeline = context.in_pipeline
        context.in_pipeline = False
        try:
            yield
        finally:
            context.in_pipeline = old_pipeline

    @contextmanager
    def _loop_depth(self, context: 'ExecutionContext') -> Iterator[None]:
        """Track loop nesting depth for break/continue level handling."""
        context.loop_depth += 1
        try:
            yield
        finally:
            context.loop_depth -= 1

    @staticmethod
    def _reraise_loop_control(exc, context: 'ExecutionContext') -> None:
        """Re-raise a break/continue exception decremented one nesting level.

        When a ``break N`` / ``continue N`` (N > 1) reaches a loop that is not
        the outermost target, it must keep propagating outward with its level
        count reduced by one. Outside that case nothing is re-raised (the
        caller handles the local break/continue). The signal's exit_status
        (0 for a successful break/continue, 1 for the out-of-range case) is
        carried forward through the propagation.
        """
        if exc.level > 1 and context.loop_depth > 1:
            raise type(exc)(exc.level - 1, exit_status=exc.exit_status)

    @staticmethod
    def _signal_status(sig: 'Union[LoopBreak, LoopContinue]', current: int) -> int:
        """The loop's exit status after a break/continue signal from the BODY.

        bash: the loop reports the status of the last command executed in
        the body — and a break/continue IS such a command, so a successful
        one resets the loop's status to 0 (`for i in 0 1; do false &&
        break; done` ends with the test's 1, but `[ ... ] && break` taken
        ends with the break's 0). Out-of-range `break 0` carries 1. A
        manually raised signal (exit_status=None) keeps the body status.
        """
        return sig.exit_status if sig.exit_status is not None else current

    def execute_if(self, node: 'IfConditional', context: 'ExecutionContext',
                   visitor: 'ASTVisitor[int]') -> int:
        """
        Execute if/then/else statement.

        Args:
            node: The IfConditional AST node
            context: Current execution context
            visitor: Visitor for executing child nodes

        Returns:
            Exit status code
        """
        # Redirects apply to the whole if; pipeline context is neutralized
        # for commands inside the construct.
        with self._compound_redirections(node) as applied, \
                self._pipeline_context_disabled(context):
            if not applied:
                return 1
            # Evaluate main condition (set -e is suppressed in conditions)
            with context.errexit_suppressed():
                condition_status = visitor.visit(node.condition)

            if condition_status == 0:
                return visitor.visit(node.then_part)

            # Check elif conditions
            for elif_condition, elif_then in node.elif_parts:
                with context.errexit_suppressed():
                    elif_status = visitor.visit(elif_condition)
                if elif_status == 0:
                    return visitor.visit(elif_then)

            # Execute else part if present
            if node.else_part:
                return visitor.visit(node.else_part)

            return 0

    def execute_while(self, node: 'WhileLoop', context: 'ExecutionContext',
                      visitor: 'ASTVisitor[int]') -> int:
        """
        Execute while loop.

        Args:
            node: The WhileLoop AST node
            context: Current execution context
            visitor: Visitor for executing child nodes

        Returns:
            Exit status code
        """
        exit_status = 0
        with self._loop_depth(context), \
                self._compound_redirections(node) as applied, \
                self._pipeline_context_disabled(context):
            if not applied:
                return 1
            while True:
                # Evaluate condition (set -e is suppressed in conditions).
                # The condition is inside the loop for break/continue too:
                # `while break; do ...; done` exits THIS loop, rc 0 (bash).
                try:
                    with context.errexit_suppressed():
                        condition_status = visitor.visit(node.condition)
                except LoopContinue as lc:
                    # bash: continue in a WHILE condition re-evaluates it,
                    # and (like a body continue) resets the loop's pending
                    # status to the continue's own 0 — a later body run
                    # overrides it again. Pinned by the truth table in
                    # tmp/probes-r17t1-break (cond_continue_after_fail_body).
                    exit_status = self._signal_status(lc, exit_status)
                    self._reraise_loop_control(lc, context)
                    continue
                except LoopBreak as lb:
                    # bash quirk (verified against bash 5.2, the project
                    # oracle): a SUCCESSFUL break in a WHILE condition resets
                    # the loop's status to 0, but a failed `break 0` there
                    # keeps the last body status (the failure status 1 is NOT
                    # reported — while_break0_cond / d8 in the truth table).
                    if lb.exit_status == 0:
                        exit_status = 0
                    self._reraise_loop_control(lb, context)
                    break
                if condition_status != 0:
                    break

                # Execute body
                try:
                    exit_status = visitor.visit(node.body)
                except LoopContinue as lc:
                    exit_status = self._signal_status(lc, exit_status)
                    self._reraise_loop_control(lc, context)
                    continue
                except LoopBreak as lb:
                    exit_status = self._signal_status(lb, exit_status)
                    self._reraise_loop_control(lb, context)
                    break
        return exit_status

    def execute_until(self, node: 'UntilLoop', context: 'ExecutionContext',
                      visitor: 'ASTVisitor[int]') -> int:
        """Execute until loop (runs until condition succeeds)."""
        exit_status = 0
        with self._loop_depth(context), \
                self._compound_redirections(node) as applied, \
                self._pipeline_context_disabled(context):
            if not applied:
                return 1
            while True:
                # break/continue in the condition act on THIS loop, but with
                # the WHILE polarity mirrored (verified against bash 5.2, the
                # project oracle; truth table in tmp/probes-r17t1-break): the
                # continue/break returns 0, which reads as the condition
                # SUCCEEDING, so the loop ends normally keeping the last body
                # status. NOTE: bash 3.2 diverges specifically on
                # until-condition-continue — it does NOT abandon the list
                # there (see the LoopContinue arm just below); psh pins 5.2.
                try:
                    with context.errexit_suppressed():
                        condition_status = visitor.visit(node.condition)
                except LoopContinue as lc:
                    # `until continue; do ...; done` TERMINATES in bash
                    # (d5/d10/e3 — psh used to loop forever here), keeping
                    # the last body status.
                    self._reraise_loop_control(lc, context)
                    break
                except LoopBreak as lb:
                    # Successful break: condition "succeeded" — keep the
                    # body status (until_cond_break_after_fail_body → 1).
                    # Failed `break 0` (status 1): the condition failed, so
                    # the until does NOT end normally; the failure status is
                    # reported (d4_until_break0_cond → 1).
                    if lb.exit_status:
                        exit_status = lb.exit_status
                    self._reraise_loop_control(lb, context)
                    break
                if condition_status == 0:
                    break
                try:
                    exit_status = visitor.visit(node.body)
                except LoopContinue as lc:
                    exit_status = self._signal_status(lc, exit_status)
                    self._reraise_loop_control(lc, context)
                    continue
                except LoopBreak as lb:
                    exit_status = self._signal_status(lb, exit_status)
                    self._reraise_loop_control(lb, context)
                    break
        return exit_status

    def execute_for(self, node: 'ForLoop', context: 'ExecutionContext',
                    visitor: 'ASTVisitor[int]') -> int:
        """
        Execute for loop.

        Args:
            node: The ForLoop AST node
            context: Current execution context
            visitor: Visitor for executing child nodes

        Returns:
            Exit status code
        """
        # The loop variable must be a valid name. bash rejects an invalid one
        # ("`NAME': not a valid identifier", status 1) before running the body
        # or expanding the word list. Single identifier policy via
        # unicode_support: under ``set -o posix`` names are ASCII-only as bash
        # requires; otherwise psh's lenient Unicode-letter rule applies (a
        # documented divergence — bash rejects Unicode names in both modes).
        if not is_valid_name(node.variable,
                             self.state.options.get('posix', False)):
            print(f"psh: `{node.variable}': not a valid identifier",
                  file=self.shell.stderr)
            return 1

        exit_status = 0
        with self._loop_depth(context), \
                self._compound_redirections(node) as applied, \
                self._pipeline_context_disabled(context):
            if not applied:
                return 1
            # Expand the item list INSIDE the redirect scope (F4): a command
            # substitution in the words (`for x in $(cat); do ...; done <
            # input`) must read the loop's redirected stdin, not the outer
            # one. Quote types are respected. A brace-budget overflow in the
            # iterable is an expected error, reported cleanly (not the
            # top-level "unexpected error" guard) — see _report_loop_*.
            from ..expansion.brace_expansion import BraceExpansionError
            try:
                expanded_items = self._expand_loop_items(node)
            except BraceExpansionError as e:
                return self._report_loop_brace_overflow(e)
            # The `for VAR in WORDS` header body is loop-invariant (the
            # variable name and the expanded word list don't change across
            # iterations), so render it ONCE, lazily, the first time we
            # trace — not once per iteration. Kept lazy (rather than hoisted
            # unconditionally) so a trace-off loop pays nothing, and the
            # `xtrace` CHECK stays inside the loop so a body toggling
            # `set +x`/`set -x` mid-loop is honored per iteration (bash does).
            # PS4 is re-expanded every iteration below: it can carry
            # per-iteration expansions ($(...), $n), which bash re-evaluates.
            xtrace_body: Optional[str] = None
            for item in expanded_items:
                # set -x: bash re-traces the `for VAR in WORDS` header on EACH
                # iteration (the expanded word list, quoted).
                if self.state.options.get('xtrace'):
                    if xtrace_body is None:
                        words = ' '.join(
                            xtrace_quote(w) for w in expanded_items)
                        xtrace_body = f"for {node.variable} in {words}"
                    ps4 = self.expansion_manager.expand_ps4()
                    self.state.stderr.write(
                        f"{ps4}{xtrace_body}".rstrip() + "\n")
                # bash runs the DEBUG trap before binding the loop variable on
                # EACH iteration (so `trap d DEBUG; for i in 1 2; do echo x;
                # done` fires d before every `i=…` and every `echo`), with
                # $BASH_COMMAND = the pre-expansion header (`for i in $v` —
                # the stamped node renders as the header lazily on read).
                self.shell.trap_manager.set_bash_command(node)
                self.shell.trap_manager.execute_debug_trap()
                # Set loop variable. A readonly variable or a cyclic nameref
                # rejects the binding: bash reports (error / warning form
                # respectively), the loop is abandoned with status 1, and
                # execution continues.
                try:
                    self.state.set_variable(node.variable, item)
                except (ReadonlyVariableError, NamerefCycleError) as e:
                    from .strategies import report_assignment_error
                    return report_assignment_error(self.state, e)

                # Execute body
                try:
                    exit_status = visitor.visit(node.body)
                except LoopContinue as lc:
                    exit_status = self._signal_status(lc, exit_status)
                    self._reraise_loop_control(lc, context)
                    continue
                except LoopBreak as lb:
                    exit_status = self._signal_status(lb, exit_status)
                    self._reraise_loop_control(lb, context)
                    break
        return exit_status

    def execute_c_style_for(self, node: 'CStyleForLoop', context: 'ExecutionContext',
                            visitor: 'ASTVisitor[int]') -> int:
        """
        Execute C-style for loop: for ((init; cond; update))

        Args:
            node: The CStyleForLoop AST node
            context: Current execution context
            visitor: Visitor for executing child nodes

        Returns:
            Exit status code
        """
        exit_status = 0
        with self._loop_depth(context):
            # Redirects apply to the whole loop, INCLUDING the init expression
            # (F4): `for ((i=$(cat); ...)); do ...; done < num` must read the
            # loop's redirected stdin. Install them first, then run the init
            # DEBUG trap and init evaluation inside the scope. Pipeline context
            # is neutralized for the body (uniform with while/for — see
            # _pipeline_context_disabled).
            with self._compound_redirections(node) as applied, \
                    self._pipeline_context_disabled(context):
                if not applied:
                    return 1

                # bash runs the DEBUG trap before each arithmetic step of a
                # C-style for: the init, every condition test, and every update
                # (plus the body commands fire their own). So `for
                # ((i=0;i<1;i++)); do echo w; done` fires D before init, cond,
                # echo, update, then the final cond. $BASH_COMMAND is the step's
                # own text: ((i=0)), ((i<1)), ...
                self._set_arith_step_bash_command(node.init_expr)
                self.shell.trap_manager.execute_debug_trap()
                # Evaluate init expression.
                if node.init_expr:
                    try:
                        evaluate_arithmetic(node.init_expr, self.shell)
                    except (ReadonlyVariableError, NamerefCycleError,
                            ValueError, ArithmeticError) as e:
                        # A bad init expr (`readonly z; for ((z=0; ...))`, or an
                        # evaluation failure): the loop never runs; bash reports
                        # and continues with status 1.
                        return self._arith_step_error_status(e)

                while True:
                    # Evaluate condition
                    self._set_arith_step_bash_command(node.condition_expr)
                    self.shell.trap_manager.execute_debug_trap()
                    if node.condition_expr:
                        try:
                            result = evaluate_arithmetic(node.condition_expr, self.shell)
                            if result == 0:  # Zero means false
                                break
                        except (ReadonlyVariableError, NamerefCycleError,
                                ValueError, ArithmeticError) as e:
                            # A bad condition expr stops the loop with status 1
                            # (bash reports; execution continues after).
                            exit_status = self._arith_step_error_status(e)
                            break

                    # Execute body. A continue falls through to the update
                    # expression (C-style semantics); a break exits the loop.
                    try:
                        exit_status = visitor.visit(node.body)
                    except LoopContinue as lc:
                        exit_status = self._signal_status(lc, exit_status)
                        self._reraise_loop_control(lc, context)
                    except LoopBreak as lb:
                        exit_status = self._signal_status(lb, exit_status)
                        self._reraise_loop_control(lb, context)
                        break

                    # Evaluate update expression
                    self._set_arith_step_bash_command(node.update_expr)
                    self.shell.trap_manager.execute_debug_trap()
                    if node.update_expr:
                        try:
                            evaluate_arithmetic(node.update_expr, self.shell)
                        except (ReadonlyVariableError, NamerefCycleError,
                                ValueError, ArithmeticError) as e:
                            # A bad update expr stops the loop with status 1;
                            # the body has already run this iteration (bash).
                            exit_status = self._arith_step_error_status(e)
                            break

        return exit_status

    def execute_case(self, node: 'CaseConditional', context: 'ExecutionContext',
                     visitor: 'ASTVisitor[int]') -> int:
        """
        Execute case statement.

        Args:
            node: The CaseConditional AST node
            context: Current execution context
            visitor: Visitor for executing child nodes

        Returns:
            Exit status code
        """
        # Redirects apply to the whole case, INCLUDING the subject eval (F4):
        # `case "$(cat)" in ... esac < input` must read the redirected stdin.
        # Install them first, then run the DEBUG trap / subject expansion /
        # xtrace header inside the scope. Pipeline context is neutralized for
        # commands inside the construct.
        with self._compound_redirections(node) as applied, \
                self._pipeline_context_disabled(context):
            if not applied:
                return 1

            # bash runs the DEBUG trap before the `case` command (the subject
            # eval), with $BASH_COMMAND = the pre-expansion header `case $x in`
            # (the stamped node renders as the header lazily on read).
            self.shell.trap_manager.set_bash_command(node)
            self.shell.trap_manager.execute_debug_trap()

            # Expand the subject. The parser carries a Word (per-part quote
            # context), so expand it quote-aware — tilde/parameter/command/
            # arithmetic expansion and quote removal, but NO splitting/globbing
            # — and a single-quoted subject stays literal. Manually built ASTs
            # (subject_word=None) fall back to legacy flat-string re-expansion.
            if node.subject_word is not None:
                expr = self.expansion_manager.expand_word_as_subject(node.subject_word)
            else:
                expr = node.expr
                if '$' in expr:
                    expr = self.expansion_manager.expand_string_variables(expr)

            # set -x: bash traces the `case WORD in` header (expanded, quoted).
            if self.state.options.get('xtrace'):
                ps4 = self.expansion_manager.expand_ps4()
                self.state.stderr.write(f"{ps4}case {xtrace_quote(expr)} in\n")

            # Try each case item
            fall_through = False
            for case_item in node.items:
                matched = fall_through
                if not matched:
                    # Check if any pattern matches
                    for pattern_obj in case_item.patterns:
                        if getattr(pattern_obj, 'word', None) is not None:
                            # Word AST path: per-part quote context
                            # (quoted text matches literally).
                            pat = self.expansion_manager.expand_word_as_pattern(
                                pattern_obj.word)
                            if self._match_shell_pattern(expr, pat):
                                matched = True
                                break
                            continue

                        # Fallback audit 2026-06-12 — classification
                        # (b), parser migration bridge: the combinator
                        # parser emits CasePattern(word=None) when
                        # build_word_from_token rejects the pattern
                        # token (e.g. a $(...) pattern containing a
                        # function definition), and CasePattern's word
                        # field defaults to None for manual ASTs.
                        # Exercised by tests/unit/executor/
                        # test_legacy_ast_fallbacks.py.
                        pattern_str = pattern_obj.pattern
                        expanded_pattern = pattern_str
                        if '$' in pattern_str:
                            expanded_pattern = self.expansion_manager.expand_string_variables(pattern_str)

                        if self._match_shell_pattern(expr, expanded_pattern):
                            matched = True
                            break

                fall_through = False

                if matched:
                    # Execute the commands for this case
                    exit_status = visitor.visit(case_item.commands)

                    # Handle terminator
                    if case_item.terminator == ';;':
                        # Normal termination
                        return exit_status
                    elif case_item.terminator == ';&':
                        # Fall through: execute next case unconditionally
                        fall_through = True
                        continue
                    elif case_item.terminator == ';;&':
                        # Continue testing patterns
                        continue

                    return exit_status

            # No pattern matched
            return 0

    def execute_select(self, node: 'SelectLoop', context: 'ExecutionContext',
                       visitor: 'ASTVisitor[int]') -> int:
        """
        Execute select loop for interactive menu selection.

        Args:
            node: The SelectLoop AST node
            context: Current execution context
            visitor: Visitor for executing child nodes

        Returns:
            Exit status code
        """
        # Same NAME rule as the for loop (bash: "`X': not a valid
        # identifier", status 1, execution continues with the next
        # statement) — the parser accepts any word-like subject and defers
        # validity here.
        if not is_valid_name(node.variable,
                             self.state.options.get('posix', False)):
            print(f"psh: `{node.variable}': not a valid identifier",
                  file=self.shell.stderr)
            return 1

        exit_status = 0
        with self._loop_depth(context):
            with self._compound_redirections(node) as applied, \
                    self._pipeline_context_disabled(context):
                if not applied:
                    return 1
                # Expand the item list INSIDE the redirect scope (F4) so a
                # command substitution in the words reads the loop's
                # redirected stdin. Respects quote types. A brace-budget
                # overflow is reported cleanly (see _report_loop_brace_overflow).
                from ..expansion.brace_expansion import BraceExpansionError
                try:
                    expanded_items = self._expand_loop_items(node)
                except BraceExpansionError as e:
                    return self._report_loop_brace_overflow(e)

                # Empty list - exit immediately
                if not expanded_items:
                    return 0
                try:
                    # Get PS3 prompt (default "#? " if not set)
                    ps3 = self.state.get_variable("PS3", "#? ")

                    while True:
                        # Display menu to stderr
                        self._display_select_menu(expanded_items)

                        # Show prompt and read input
                        try:
                            self.state.stderr.write(ps3)
                            self.state.stderr.flush()

                            # Read input line
                            if hasattr(self.shell, 'stdin') and self.shell.stdin:
                                # Use shell's stdin if available (set by I/O redirection)
                                reply = self.shell.stdin.readline()
                            else:
                                # Use sys.stdin as fallback
                                if sys.stdin is None or sys.stdin.closed:
                                    raise EOFError
                                try:
                                    reply = sys.stdin.readline()
                                except (OSError, ValueError):
                                    # Handle case where stdin is not available in test environment
                                    raise EOFError from None

                            if not reply:  # EOF
                                raise EOFError
                            reply = reply.rstrip('\n')
                        except (EOFError, KeyboardInterrupt):
                            # Ctrl+D or Ctrl+C exits the loop; bash reports the
                            # failed read with a non-zero status and prints the
                            # terminating newline on STDOUT.
                            print()
                            exit_status = 1
                            break

                        # Set REPLY variable
                        self.state.set_variable("REPLY", reply)

                        # Process selection
                        if reply.strip().isdigit():
                            choice = int(reply.strip())
                            if 1 <= choice <= len(expanded_items):
                                # Valid selection
                                selected = expanded_items[choice - 1]
                                self.state.set_variable(node.variable, selected)
                            else:
                                # Out of range
                                self.state.set_variable(node.variable, "")
                        else:
                            # Non-numeric input
                            self.state.set_variable(node.variable, "")

                        # Execute loop body
                        try:
                            exit_status = visitor.visit(node.body)
                        except LoopContinue as lc:
                            exit_status = self._signal_status(lc, exit_status)
                            self._reraise_loop_control(lc, context)
                            continue
                        except LoopBreak as lb:
                            exit_status = self._signal_status(lb, exit_status)
                            self._reraise_loop_control(lb, context)
                            break
                except KeyboardInterrupt:
                    self.state.stderr.write("\n")
                    exit_status = 130

        return exit_status

    # Helper methods

    def _arith_step_error_status(self, exc: Exception) -> int:
        """Map a C-style-``for`` arithmetic-step failure to the loop's status.

        The init, condition and update expressions of ``for ((...))`` all
        fail the same way (bash): a readonly / nameref-cycle assignment is
        reported via ``report_assignment_error`` (bash's message + flow), and
        any other evaluation failure (``ValueError``/``ArithmeticError`` —
        e.g. a bad base literal or a residual ``$``) prints ``psh: ((: <msg>``.
        Both yield status 1 and let the shell continue; the CALLER decides
        whether that ends the loop (``return`` before the loop runs, or
        ``break`` out of it)."""
        if isinstance(exc, (ReadonlyVariableError, NamerefCycleError)):
            from .strategies import report_assignment_error
            return report_assignment_error(self.state, exc)
        print(f"psh: ((: {exc}", file=self.state.stderr)
        return 1

    def _set_arith_step_bash_command(self, expr: Optional[str]) -> None:
        """$BASH_COMMAND for one C-style-for arithmetic step (bash reports
        ``((i=0))`` / ``((i<1))`` / ``((i++))``). An absent step records
        nothing (the previous command's text stands)."""
        if expr:
            self.shell.trap_manager.set_bash_command(f"(({expr}))")

    def _report_loop_brace_overflow(self, e) -> int:
        """Report a brace-expansion budget overflow in a for/select iterable.

        A ``BraceExpansionError`` (over ``MAX_EXPANSION_ITEMS``) raised while
        expanding the loop's word list is an EXPECTED shell error, not an
        internal defect. Loop iterables expand via ``expand_word_to_fields``
        OUTSIDE the SimpleCommand try/except, so — unlike ``echo {1..200000}``
        or ``a=({1..200000})`` — it would otherwise escape to the top-level
        source-processor guard and print as ``psh: <loc>: unexpected error:
        ...``, which reads like a psh bug. Route it through the SAME clean
        handler the simple-command path uses (``report_internal_defect``, which
        recognizes it as an expected shell error): ``psh: brace expansion: N
        items exceeds the limit`` on stderr, status 1, the shell continues.
        """
        return report_internal_defect(self.state, e, stream=self.shell.stderr)

    def _expand_loop_items(self, node) -> List[str]:
        """Expand the item list of a for or select loop.

        Items go through the canonical Word expansion engine
        (ExpansionManager.expand_word_to_fields) under the LOOP_ITEM
        policy (an alias of COMMAND_ARGUMENT in
        ``psh/expansion/word_expander.py``), so IFS splitting of
        command substitutions and variables, quote suppression, globbing,
        tilde expansion and empty-expansion elision all match
        simple-command argument semantics — bash tilde-expands
        ``for i in P=~/x`` like a command argument.

        Fallback audit 2026-06-12 — classification (a), kept deliberately:
        both parsers always populate item_words (parallel to items). Since
        A2 (2026-06-13) item_words is a non-Optional List[Word] defaulting
        to []; a manually constructed AST that omits it (an explicitly
        supported educational pattern) therefore has item_words=[], whose
        length will not match node.items, and falls through to iterating
        the items as literal fields. Exercised by
        tests/unit/executor/test_legacy_ast_fallbacks.py.
        """
        item_words = getattr(node, 'item_words', None)
        if not item_words or len(item_words) != len(node.items):
            return list(node.items)

        from ..expansion.word_expansion_types import LOOP_ITEM

        expanded_items: List[str] = []
        for word in item_words:
            expanded_items.extend(
                self.expansion_manager.expand_word_to_fields(word, LOOP_ITEM))
        return expanded_items

    def _match_shell_pattern(self, string: str, pattern: str) -> bool:
        """Full-match a string against a shell pattern.

        Delegates to the canonical engine (expansion/pattern.py), which
        honors backslash escapes (including those glob_escape added for
        quoted text), bracket classes, and extglob when enabled.
        """
        from ..expansion.pattern import match_shell_pattern
        return match_shell_pattern(
            string, pattern,
            extglob_enabled=self.state.options.get('extglob', False),
            ignorecase=self.state.options.get('nocasematch', False))

    def _display_select_menu(self, items: List[str]) -> None:
        """Display the select menu to stderr."""
        # Calculate layout
        num_items = len(items)
        if num_items <= 9:
            # Single column for small lists
            for i, item in enumerate(items, 1):
                self.state.stderr.write(f"{i}) {item}\n")
        else:
            # Multi-column for larger lists
            columns = 2 if num_items <= 20 else 3
            rows = (num_items + columns - 1) // columns

            # Calculate column widths
            col_width = max(len(f"{i}) {items[i-1]}") for i in range(1, num_items + 1)) + 3

            for row in range(rows):
                for col in range(columns):
                    idx = row + col * rows
                    if idx < num_items:
                        entry = f"{idx + 1}) {items[idx]}"
                        self.state.stderr.write(entry.ljust(col_width))
                self.state.stderr.write("\n")
