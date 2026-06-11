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
from typing import TYPE_CHECKING, List, Optional

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
        # Apply redirections to entire if statement
        with self.io_manager.with_redirections(node.redirects):
            # Temporarily disable pipeline context for commands inside control structure
            old_pipeline = context.in_pipeline
            context.in_pipeline = False
            try:
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
            finally:
                context.in_pipeline = old_pipeline

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
        context.loop_depth += 1
        try:
            # Apply redirections for entire loop
            with self.io_manager.with_redirections(node.redirects):
                # Temporarily disable pipeline context for commands inside control structure
                old_pipeline = context.in_pipeline
                context.in_pipeline = False
                try:
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
                            if lc.level > 1 and context.loop_depth > 1:
                                raise LoopContinue(lc.level - 1)
                            continue
                        except LoopBreak as lb:
                            if lb.level > 1 and context.loop_depth > 1:
                                raise LoopBreak(lb.level - 1)
                            break

                finally:
                    context.in_pipeline = old_pipeline
        finally:
            context.loop_depth -= 1
        return exit_status

    def execute_until(self, node: 'UntilLoop', context: 'ExecutionContext',
                      visitor: 'ASTVisitor[int]') -> int:
        """Execute until loop (runs until condition succeeds)."""
        exit_status = 0
        context.loop_depth += 1
        try:
            with self.io_manager.with_redirections(node.redirects):
                old_pipeline = context.in_pipeline
                context.in_pipeline = False
                try:
                    while True:
                        with context.errexit_suppressed():
                            condition_status = visitor.visit(node.condition)
                        if condition_status == 0:
                            break
                        try:
                            exit_status = visitor.visit(node.body)
                        except LoopContinue as lc:
                            if lc.level > 1 and context.loop_depth > 1:
                                raise LoopContinue(lc.level - 1)
                            continue
                        except LoopBreak as lb:
                            if lb.level > 1 and context.loop_depth > 1:
                                raise LoopBreak(lb.level - 1)
                            break
                finally:
                    context.in_pipeline = old_pipeline
        finally:
            context.loop_depth -= 1
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
        context.loop_depth += 1
        try:
            # Expand items - handle all types of expansion, respecting quote types
            expanded_items = self._expand_loop_items(node)

            # Apply redirections for entire loop
            with self.io_manager.with_redirections(node.redirects):
                # Temporarily disable pipeline context for commands inside control structure
                old_pipeline = context.in_pipeline
                context.in_pipeline = False
                try:
                    for item in expanded_items:
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
                            if lc.level > 1 and context.loop_depth > 1:
                                raise LoopContinue(lc.level - 1)
                            continue
                        except LoopBreak as lb:
                            if lb.level > 1 and context.loop_depth > 1:
                                raise LoopBreak(lb.level - 1)
                            break

                finally:
                    context.in_pipeline = old_pipeline
        finally:
            context.loop_depth -= 1
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
        context.loop_depth += 1

        # Evaluate init expression
        if node.init_expr:
            try:
                evaluate_arithmetic(node.init_expr, self.shell)
            except (ValueError, ArithmeticError) as e:
                print(f"psh: ((: {e}", file=self.state.stderr)
                context.loop_depth -= 1
                return 1

        # Apply redirections for entire loop
        with self.io_manager.with_redirections(node.redirects):
            try:
                while True:
                    # Evaluate condition
                    if node.condition_expr:
                        try:
                            result = evaluate_arithmetic(node.condition_expr, self.shell)
                            if result == 0:  # Zero means false
                                break
                        except (ValueError, ArithmeticError) as e:
                            print(f"psh: ((: {e}", file=self.state.stderr)
                            exit_status = 1
                            break

                    # Execute body
                    try:
                        exit_status = visitor.visit(node.body)
                    except LoopContinue as lc:
                        if lc.level > 1 and context.loop_depth > 1:
                            raise LoopContinue(lc.level - 1)
                    except LoopBreak as lb:
                        if lb.level > 1 and context.loop_depth > 1:
                            raise LoopBreak(lb.level - 1)
                        break

                    # Evaluate update expression
                    if node.update_expr:
                        try:
                            evaluate_arithmetic(node.update_expr, self.shell)
                        except (ValueError, ArithmeticError) as e:
                            print(f"psh: ((: {e}", file=self.state.stderr)
                            exit_status = 1
                            break

            finally:
                context.loop_depth -= 1

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
        # Expand the expression
        expr = node.expr
        if '$' in expr:
            expr = self.expansion_manager.expand_string_variables(expr)

        # Apply redirections
        with self.io_manager.with_redirections(node.redirects):
            # Temporarily disable pipeline context for commands inside control structure
            old_pipeline = context.in_pipeline
            context.in_pipeline = False
            try:
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

                            # Legacy string path (rare: only when the
                            # combinator parser couldn't build a Word)
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
            finally:
                context.in_pipeline = old_pipeline

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
        context.loop_depth += 1

        # Expand items - handle all types of expansion, respecting quote types
        expanded_items = self._expand_loop_items(node)

        # Empty list - exit immediately
        if not expanded_items:
            context.loop_depth -= 1
            return 0

        # Apply redirections for entire loop
        with self.io_manager.with_redirections(node.redirects):
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
                        if lc.level > 1 and context.loop_depth > 1:
                            raise LoopContinue(lc.level - 1)
                        continue
                    except LoopBreak as lb:
                        if lb.level > 1 and context.loop_depth > 1:
                            raise LoopBreak(lb.level - 1)
                        break
            except KeyboardInterrupt:
                sys.stderr.write("\n")
                exit_status = 130
            finally:
                context.loop_depth -= 1

        return exit_status

    def execute_break(self, node: 'BreakStatement', context: 'ExecutionContext') -> int:
        """
        Execute break statement.

        Args:
            node: The BreakStatement AST node
            context: Current execution context

        Returns:
            Never returns normally, always raises LoopBreak
        """
        if context.loop_depth == 0:
            # bash: warn and continue with status 0 (subsequent statements
            # still execute; raising here used to print the warning twice)
            print("break: only meaningful in a `for' or `while' loop", file=self.shell.stderr)
            return 0
        raise LoopBreak(node.level)

    def execute_continue(self, node: 'ContinueStatement', context: 'ExecutionContext') -> int:
        """
        Execute continue statement.

        Args:
            node: The ContinueStatement AST node
            context: Current execution context

        Returns:
            Never returns normally, always raises LoopContinue
        """
        if context.loop_depth == 0:
            # bash: warn and continue with status 0 (see execute_break)
            print("continue: only meaningful in a `for' or `while' loop", file=self.shell.stderr)
            return 0
        raise LoopContinue(node.level)

    # Helper methods

    def _expand_loop_items(self, node) -> List[str]:
        """Expand items for a for or select loop, handling all expansion types."""
        expanded_items = []
        quote_types = getattr(node, 'item_quote_types', [None] * len(node.items))

        for i, item in enumerate(node.items):
            quote_type = quote_types[i] if i < len(quote_types) else None

            # Check if this is an array expansion
            if '$' in item and self.expansion_manager.variable_expander.is_array_expansion(item):
                # Expand array to list of items
                array_items = self.expansion_manager.variable_expander.expand_array_to_list(item)
                expanded_items.extend(array_items)
            else:
                # Perform full expansion on the item
                expanded_items.extend(self._expand_single_item(item, quote_type))

        return expanded_items

    def _expand_single_item(self, item: str, quote_type: Optional[str]) -> List[str]:
        """Expand a single item based on its type and quote context."""
        # Determine the type of the item (check arithmetic first since it starts with $()
        if item.startswith('$((') and item.endswith('))'):
            # Arithmetic expansion
            result = self.expansion_manager.execute_arithmetic_expansion(item)
            # Arithmetic expansion always produces a single value
            return [str(result)]
        elif item.startswith('$(') and item.endswith(')'):
            # Command substitution
            output = self.expansion_manager.execute_command_substitution(item)
            # For quoted command substitution, don't word split
            if quote_type == '"':
                return [output if output else ""]
            else:
                # Split on whitespace for word splitting
                return output.split() if output else []
        elif item.startswith('`') and item.endswith('`'):
            # Backtick command substitution
            output = self.expansion_manager.execute_command_substitution(item)
            # For quoted command substitution, don't word split
            if quote_type == '"':
                return [output if output else ""]
            else:
                # Split on whitespace for word splitting
                return output.split() if output else []
        elif '$' in item:
            # Variable expansion
            expanded = self.expansion_manager.expand_string_variables(item)

            if quote_type == '"':
                # Double-quoted: no word splitting, no glob expansion
                return [expanded if expanded else ""]
            elif quote_type == "'":
                # Single-quoted: no expansion at all (but shouldn't happen here since we have $)
                return [item]
            else:
                # Unquoted: word splitting and glob expansion
                return self._word_split_and_glob(expanded)
        else:
            # No special expansion needed
            if quote_type in ['"', "'"]:
                # Quoted: no glob expansion
                return [item]
            else:
                # Unquoted: glob via the canonical path (honors nullglob,
                # [^...], POSIX classes, globstar, etc.).
                return self.shell.expansion_manager._glob_words([item])

    def _word_split_and_glob(self, text: str) -> List[str]:
        """Perform word splitting and glob expansion on text.

        Delegates globbing to the canonical ExpansionManager path so the
        for/select loop matches simple-command behavior: empty fields from
        non-whitespace IFS are preserved, and nullglob is honored.
        """
        ifs = self.state.get_variable('IFS', ' \t\n')
        words = self.shell.expansion_manager.word_splitter.split(text, ifs)
        return self.shell.expansion_manager._glob_words(words)

    def _match_shell_pattern(self, string: str, pattern: str) -> bool:
        """Full-match a string against a shell pattern.

        Delegates to the canonical engine (expansion/pattern.py), which
        honors backslash escapes (including those glob_escape added for
        quoted text), bracket classes, and extglob when enabled.
        """
        from ..expansion.pattern import match_shell_pattern
        return match_shell_pattern(
            string, pattern,
            extglob_enabled=self.state.options.get('extglob', False))

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
