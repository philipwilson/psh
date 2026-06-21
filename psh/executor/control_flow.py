"""
Control flow execution support for the PSH executor.

This module handles execution of control structures including:
- If/elif/else conditionals
 - While loops
 - Until loops
- For loops (standard and C-style)
- Case statements
- Select loops
- Break and continue statements
"""

import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING, Iterator, List, Optional

from ..core import LoopBreak, LoopContinue, ReadonlyVariableError
from ..expansion.arithmetic import evaluate_arithmetic

if TYPE_CHECKING:
    from psh.visitor import ASTVisitor

    from ..ast_nodes import (
        BreakStatement,
        CaseConditional,
        ContinueStatement,
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
    def _compound_redirections(self, node) -> Iterator[None]:
        """Apply the construct's redirections around its whole body.

        Redirects on a compound command apply to every command in the body
        and are restored when the body finishes (delegates to the io manager's
        per-block save/restore).
        """
        with self.io_manager.with_redirections(node.redirects):
            yield

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
        caller handles the local break/continue). A LoopBreak's exit_status
        (the out-of-range case) is carried forward through the propagation.
        """
        if exc.level > 1 and context.loop_depth > 1:
            if isinstance(exc, LoopBreak):
                raise LoopBreak(exc.level - 1, exit_status=exc.exit_status)
            raise type(exc)(exc.level - 1)

    @staticmethod
    def _break_status(lb: 'LoopBreak', current: int) -> int:
        """The loop's exit status after catching a LoopBreak: the break's own
        status when set (out-of-range `break 0` → 1), else the body status."""
        return lb.exit_status if lb.exit_status is not None else current

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
        with self._compound_redirections(node), self._pipeline_context_disabled(context):
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
        with self._loop_depth(context), self._compound_redirections(node), \
                self._pipeline_context_disabled(context):
            while True:
                # Evaluate condition (set -e is suppressed in conditions)
                with context.errexit_suppressed():
                    condition_status = visitor.visit(node.condition)
                if condition_status != 0:
                    break

                # Execute body
                try:
                    exit_status = visitor.visit(node.body)
                except LoopContinue as lc:
                    self._reraise_loop_control(lc, context)
                    continue
                except LoopBreak as lb:
                    exit_status = self._break_status(lb, exit_status)
                    self._reraise_loop_control(lb, context)
                    break
        return exit_status

    def execute_until(self, node: 'UntilLoop', context: 'ExecutionContext',
                      visitor: 'ASTVisitor[int]') -> int:
        """Execute until loop (runs until condition succeeds)."""
        exit_status = 0
        with self._loop_depth(context), self._compound_redirections(node), \
                self._pipeline_context_disabled(context):
            while True:
                with context.errexit_suppressed():
                    condition_status = visitor.visit(node.condition)
                if condition_status == 0:
                    break
                try:
                    exit_status = visitor.visit(node.body)
                except LoopContinue as lc:
                    self._reraise_loop_control(lc, context)
                    continue
                except LoopBreak as lb:
                    exit_status = self._break_status(lb, exit_status)
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
        exit_status = 0
        # Expand items - handle all types of expansion, respecting quote types
        expanded_items = self._expand_loop_items(node)

        with self._loop_depth(context), self._compound_redirections(node), \
                self._pipeline_context_disabled(context):
            for item in expanded_items:
                # bash runs the DEBUG trap before binding the loop variable on
                # EACH iteration (so `trap d DEBUG; for i in 1 2; do echo x;
                # done` fires d before every `i=…` and every `echo`).
                self.shell.trap_manager.execute_debug_trap()
                # Set loop variable
                try:
                    self.state.set_variable(node.variable, item)
                except ReadonlyVariableError:
                    print(f"psh: {node.variable}: readonly variable", file=self.state.stderr)
                    return 1

                # Execute body
                try:
                    exit_status = visitor.visit(node.body)
                except LoopContinue as lc:
                    self._reraise_loop_control(lc, context)
                    continue
                except LoopBreak as lb:
                    exit_status = self._break_status(lb, exit_status)
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
            # bash runs the DEBUG trap before each arithmetic step of a C-style
            # for: the init, every condition test, and every update (plus the
            # body commands fire their own). So `for ((i=0;i<1;i++)); do echo w;
            # done` fires D before init, cond, echo, update, then the final cond.
            self.shell.trap_manager.execute_debug_trap()
            # Evaluate init expression (before redirects, matching prior
            # behavior: an init error returns 1 without opening redirects).
            if node.init_expr:
                try:
                    evaluate_arithmetic(node.init_expr, self.shell)
                except (ValueError, ArithmeticError) as e:
                    print(f"psh: ((: {e}", file=self.state.stderr)
                    return 1

            # Redirects apply to the whole loop; pipeline context is
            # neutralized for the body (uniform with while/for — see
            # _pipeline_context_disabled).
            with self._compound_redirections(node), self._pipeline_context_disabled(context):
                while True:
                    # Evaluate condition
                    self.shell.trap_manager.execute_debug_trap()
                    if node.condition_expr:
                        try:
                            result = evaluate_arithmetic(node.condition_expr, self.shell)
                            if result == 0:  # Zero means false
                                break
                        except (ValueError, ArithmeticError) as e:
                            print(f"psh: ((: {e}", file=self.state.stderr)
                            exit_status = 1
                            break

                    # Execute body. A continue falls through to the update
                    # expression (C-style semantics); a break exits the loop.
                    try:
                        exit_status = visitor.visit(node.body)
                    except LoopContinue as lc:
                        self._reraise_loop_control(lc, context)
                    except LoopBreak as lb:
                        exit_status = self._break_status(lb, exit_status)
                        self._reraise_loop_control(lb, context)
                        break

                    # Evaluate update expression
                    self.shell.trap_manager.execute_debug_trap()
                    if node.update_expr:
                        try:
                            evaluate_arithmetic(node.update_expr, self.shell)
                        except (ValueError, ArithmeticError) as e:
                            print(f"psh: ((: {e}", file=self.state.stderr)
                            exit_status = 1
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
        # bash runs the DEBUG trap before the `case` command (the subject eval).
        self.shell.trap_manager.execute_debug_trap()

        # Expand the expression
        expr = node.expr
        if '$' in expr:
            expr = self.expansion_manager.expand_string_variables(expr)

        # Redirects apply to the whole case; pipeline context is neutralized
        # for commands inside the construct.
        with self._compound_redirections(node), self._pipeline_context_disabled(context):
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
        exit_status = 0
        with self._loop_depth(context):
            # Expand items - handle all types of expansion, respecting quote types
            expanded_items = self._expand_loop_items(node)

            # Empty list - exit immediately
            if not expanded_items:
                return 0

            with self._compound_redirections(node), self._pipeline_context_disabled(context):
                try:
                    # Get PS3 prompt (default "#? " if not set)
                    ps3 = self.state.get_variable("PS3", "#? ")

                    while True:
                        # Display menu to stderr
                        self._display_select_menu(expanded_items)

                        # Show prompt and read input
                        try:
                            sys.stderr.write(ps3)
                            sys.stderr.flush()

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
                                    raise EOFError

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
                            self._reraise_loop_control(lc, context)
                            continue
                        except LoopBreak as lb:
                            exit_status = self._break_status(lb, exit_status)
                            self._reraise_loop_control(lb, context)
                            break
                except KeyboardInterrupt:
                    sys.stderr.write("\n")
                    exit_status = 130

        return exit_status

    def execute_break(self, node: 'BreakStatement', context: 'ExecutionContext') -> int:
        """Execute a break statement.

        Raises LoopBreak with the resolved level, or returns a status when
        the statement does not transfer control (outside a loop, or a bad
        argument in an interactive shell). See _resolve_loop_control_level
        for the bash-matched argument semantics.
        """
        if context.loop_depth == 0:
            # bash: warn and continue with status 0 (the argument is not even
            # validated when there is no enclosing loop).
            print("break: only meaningful in a `for', `while', or `until' loop",
                  file=self.shell.stderr)
            return 0
        level = self._resolve_loop_control_level(node, 'break')
        if level is None:
            return self.state.last_exit_code
        if level == 0:
            # Out-of-range (break 0/negative): bash exits ALL enclosing loops
            # with status 1 (error already reported by the resolver).
            raise LoopBreak(context.loop_depth, exit_status=1)
        raise LoopBreak(level)

    def execute_continue(self, node: 'ContinueStatement', context: 'ExecutionContext') -> int:
        """Execute a continue statement (see execute_break for argument rules).

        A non-positive count is a bash quirk: ``continue 0`` reports
        "loop count out of range" and EXITS the loop (like ``break 1``), so
        the out-of-range path raises LoopBreak for both statements.
        """
        if context.loop_depth == 0:
            print("continue: only meaningful in a `for', `while', or `until' loop",
                  file=self.shell.stderr)
            return 0
        level = self._resolve_loop_control_level(node, 'continue')
        if level is None:
            return self.state.last_exit_code
        if level == 0:
            # Out-of-range (continue 0/negative): bash quirk — like break 0, it
            # exits ALL enclosing loops with status 1 (not "continue").
            raise LoopBreak(context.loop_depth, exit_status=1)
        raise LoopContinue(level)

    def _resolve_loop_control_level(self, node, name: str) -> Optional[int]:
        """Resolve a break/continue level argument at runtime (bash semantics).

        Returns the positive level to act on; 0 for the non-positive
        "loop count out of range" case (error already reported, caller exits
        the loop one level); or None when the statement must NOT transfer
        control because a hard argument error was reported (non-numeric / too
        many arguments — a non-interactive shell aborts via sys.exit, an
        interactive one sets the status and falls through).
        """
        if not node.level_words:
            # No raw argument: honor a literal level set on the node (the
            # combinator parser and hand-built ASTs use the int field).
            return node.level

        from ..expansion.word_expansion_types import LOOP_ITEM
        fields: List[str] = []
        for word in node.level_words:
            fields.extend(
                self.expansion_manager.expand_word_to_fields(word, LOOP_ITEM))

        if not fields:
            # The argument expanded to nothing (e.g. unset $n) — no argument.
            return node.level
        if len(fields) > 1:
            self._report_loop_control_arg_error(f"{name}: too many arguments", 1)
            return None

        arg = fields[0]
        try:
            level = int(arg)
        except ValueError:
            self._report_loop_control_arg_error(
                f"{name}: {arg}: numeric argument required", 128)
            return None

        if level <= 0:
            # bash: report "loop count out of range" and (the caller then)
            # exits ALL enclosing loops with status 1. Signalled by returning 0.
            print(f"{name}: {arg}: loop count out of range",
                  file=self.shell.stderr)
            return 0
        return level

    def _report_loop_control_arg_error(self, message: str, status: int) -> None:
        """Report a hard break/continue argument error. A non-interactive
        shell aborts with the given status (break/continue are POSIX special
        builtins); an interactive shell records the status and continues."""
        print(message, file=self.shell.stderr)
        self.state.last_exit_code = status
        if self.shell.state.is_script_mode:
            sys.exit(status)

    # Helper methods

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
                sys.stderr.write(f"{i}) {item}\n")
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
                        sys.stderr.write(entry.ljust(col_width))
                sys.stderr.write("\n")
