"""Multi-line input handler for interactive mode.

This module provides multi-line command support for the interactive shell,
allowing users to naturally type control structures across multiple lines.
"""

from typing import Callable, List, Optional

from .lexer import tokenize
from .line_editor import LineEditor
from .parser import ParseError, parse
from .prompt import PromptExpander
from .token_types import TokenType


class MultiLineInputHandler:
    """Handles multi-line command input for interactive mode."""

    def __init__(self, line_editor: LineEditor, shell):
        self.line_editor = line_editor
        self.shell = shell
        self.buffer: List[str] = []
        self.in_heredoc = False
        self.heredoc_delimiter = None
        self.heredoc_indent = False  # For <<- style
        self.prompt_expander = PromptExpander(shell)
        self.context_stack: List[str] = []  # Track nested construct contexts

    def read_command(self, on_resize: Optional[Callable[[], None]] = None) -> Optional[str]:
        """Read a complete command, possibly spanning multiple lines."""
        self.buffer = []

        # Get SIGWINCH notification fd from signal manager if available
        sigwinch_fd = -1
        sigwinch_drain = None
        if hasattr(self.shell, 'interactive_manager') and self.shell.interactive_manager:
            sigwinch_fd = self.shell.interactive_manager.signal_manager.get_sigwinch_fd()
            sigwinch_drain = self.shell.interactive_manager.signal_manager.drain_sigwinch_notifications

        while True:
            # Determine prompt
            prompt = self._get_prompt()

            # Read one line
            line = self.line_editor.read_line(prompt, sigwinch_fd, sigwinch_drain,
                                              on_resize=on_resize)
            if line is None:  # EOF
                if self.buffer:
                    print("\npsh: syntax error: unexpected end of file")
                    self.reset()
                return None

            # Add line to buffer
            self.buffer.append(line)

            # Check if command is complete
            full_command = '\n'.join(self.buffer)
            if self._is_complete_command(full_command):
                self.reset()
                # Process line continuations before returning
                from .input_preprocessing import process_line_continuations
                return process_line_continuations(full_command)

    def reset(self):
        """Reset multi-line state."""
        self.buffer = []
        self.in_heredoc = False
        self.heredoc_delimiter = None
        self.heredoc_indent = False
        self.context_stack = []

    def _get_prompt(self) -> str:
        """Get the appropriate prompt based on current state."""
        if not self.buffer:
            # Primary prompt
            ps1 = self.shell.variables.get('PS1', '\\u@\\h:\\w\\$ ')
            return self.prompt_expander.expand_prompt(ps1)
        else:
            # Continuation prompt - use context-aware prompt if available
            if self.context_stack:
                # Build nested context prompt (e.g., "for> ", "for if> ", "for then> ")
                context_str = ' '.join(self.context_stack)
                return f"{context_str}> "
            else:
                # Fallback to standard PS2
                ps2 = self.shell.variables.get('PS2', '> ')
                return self.prompt_expander.expand_prompt(ps2)

    def _is_complete_command(self, command: str) -> bool:
        """Check if command is syntactically complete."""
        if not command.strip():
            return True

        # Check for explicit line continuation
        if self._has_line_continuation(command):
            return False

        # Check for active heredoc
        if self._has_unclosed_heredoc(command):
            return False

        # Check for operators at end of line that require continuation
        # But only if we're not inside [[ ]]
        stripped = command.strip()
        if stripped.endswith(('|', '||', '&&')):
            # Count [[ and ]] to see if we're inside
            double_lbracket_count = command.count('[[')
            double_rbracket_count = command.count(']]')
            if double_lbracket_count == double_rbracket_count:
                # Not inside [[ ]], so operators mean continuation
                return False
            # Inside [[ ]], let the parser decide


        # Check for history expansion patterns that should be treated as complete
        # These will be expanded during execution, not during completeness testing
        import re
        history_pattern = r'(?:^|\s)!(?:!|[0-9]+|-[0-9]+|[a-zA-Z][a-zA-Z0-9]*|\?[^?]*\?)(?:\s|$)'
        if re.search(history_pattern, command):
            # Contains history expansion - treat as complete and let execution handle it
            return True

        # Try to tokenize and parse
        try:
            # Use interactive mode (strict=False) for multiline handling
            tokens = tokenize(command, strict=False)
            if not tokens:
                return True

            # Check for incomplete expansions in tokens
            for token in tokens:
                # Check tokens that might contain unclosed expansions
                if token.type in (TokenType.WORD, TokenType.COMMAND_SUB, TokenType.COMMAND_SUB_BACKTICK,
                                TokenType.VARIABLE, TokenType.ARITH_EXPANSION):
                    # Check for unclosed expansions
                    if self._has_unclosed_expansion(token.value):
                        return False

            # Try parsing
            parse(tokens)
            return True

        except SyntaxError as e:
            # Unterminated string or other tokenization error
            if "Unclosed" in str(e) or "Unterminated" in str(e):
                return False
            # Other tokenization errors are complete but invalid
            return True

        except ParseError as e:
            # Check for incomplete constructs
            error_msg = str(e)
            incomplete_patterns = [
                # Updated patterns for human-readable error messages
                "Expected 'do'",
                "Expected 'done'",
                "Expected 'fi'",
                "Expected 'else'",
                "Expected 'then'",
                "Expected 'esac'",
                "Expected 'in'",
                "Expected 'elif'",
                "Expected '{'",
                "Expected '}'",
                "Expected ')'",
                "Expected ']]'",
                "Expected '('",
                "Expected closing",
                "Unexpected EOF",
                "got end of input",
                "Expected pattern",  # For incomplete case statements
                "Expected test operand",
                # New TokenType-based patterns from ParserContext
                "Expected TokenType.DO",
                "Expected TokenType.DONE",
                "Expected TokenType.FI",
                "Expected TokenType.ELSE",
                "Expected TokenType.THEN",
                "Expected TokenType.ESAC",
                "Expected TokenType.IN",
                "Expected TokenType.ELIF",
                "Expected TokenType.LBRACE",
                "Expected TokenType.RBRACE",
                "Expected TokenType.RPAREN",
                "Expected TokenType.DOUBLE_RBRACKET",
                "Expected TokenType.LPAREN",
                # Old patterns for backward compatibility
                "Expected DO",
                "Expected DONE",
                "Expected FI",
                "Expected ELSE",
                "Expected THEN",
                "Expected ESAC",
                "Expected DOUBLE_RBRACKET",
            ]

            for pattern in incomplete_patterns:
                if pattern in error_msg:
                    # Update context stack for contextual prompts
                    self._update_context_stack(command, error_msg)
                    return False

            # Other parse errors mean command is complete but invalid
            # Clear context stack since command is complete (though invalid)
            self.context_stack = []
            return True

    def _has_line_continuation(self, command: str) -> bool:
        """Check if command ends with line continuation."""
        # Don't process empty strings
        if not command:
            return False

        lines = command.splitlines(keepends=True)
        if not lines:
            return False

        # Get the last line (including any trailing newline)
        last_line = lines[-1]

        # If there's a newline, check the content before it
        if last_line.endswith('\n'):
            content = last_line[:-1].rstrip()
        else:
            content = last_line.rstrip()

        if content.endswith('\\'):
            # Count preceding backslashes
            count = 0
            for i in range(len(content) - 2, -1, -1):
                if content[i] == '\\':
                    count += 1
                else:
                    break
            # Odd number of total backslashes means the last one is not escaped
            return (count % 2) == 0

        return False

    def _has_unclosed_heredoc(self, command: str) -> bool:
        """Check if command has an unclosed heredoc."""
        import re

        # First check if << only appears inside arithmetic expressions
        if '<<' in command and '((' in command:
            # Find all arithmetic expression boundaries
            arith_start = []
            arith_end = []
            i = 0
            while i < len(command) - 1:
                if command[i:i+2] == '((':
                    arith_start.append(i)
                    i += 2
                elif command[i:i+2] == '))':
                    arith_end.append(i + 2)
                    i += 2
                else:
                    i += 1

            # Find all << positions
            heredoc_positions = []
            i = 0
            while i < len(command) - 1:
                if command[i:i+2] == '<<':
                    heredoc_positions.append(i)
                    i += 2
                else:
                    i += 1

            # Check if all << are inside arithmetic expressions
            if heredoc_positions and arith_start and arith_end:
                all_inside_arithmetic = True
                for pos in heredoc_positions:
                    inside = False
                    # Check if this << is inside any arithmetic expression
                    for j in range(min(len(arith_start), len(arith_end))):
                        if arith_start[j] < pos < arith_end[j]:
                            inside = True
                            break
                    if not inside:
                        all_inside_arithmetic = False
                        break

                # If all << are inside arithmetic expressions, no heredoc
                if all_inside_arithmetic:
                    return False

        # Find all heredoc start markers (<<EOF, <<-EOF, << EOF, etc.)
        # Also handle escaped delimiters like << \EOF
        heredoc_pattern = r'<<(-?)\s*([\'"]?)(\\\s*)?(\w+)\2'

        lines = command.split('\n')
        heredoc_delimiters = []

        for line in lines:
            # Skip if line is inside a heredoc
            if any(d for d in heredoc_delimiters if not d['closed']):
                # Check if this line closes a heredoc
                for delimiter in heredoc_delimiters:
                    if not delimiter['closed']:
                        # For <<- style, strip leading tabs
                        check_line = line.lstrip('\t') if delimiter['strip_tabs'] else line
                        if check_line.rstrip() == delimiter['word']:
                            delimiter['closed'] = True
                            break
            else:
                # Look for new heredoc markers
                for match in re.finditer(heredoc_pattern, line):
                    strip_tabs = bool(match.group(1))  # '-' present
                    has_backslash = bool(match.group(3))  # Escaped delimiter
                    word = match.group(4)
                    heredoc_delimiters.append({
                        'word': word,
                        'strip_tabs': strip_tabs,
                        'closed': False,
                        'escaped': has_backslash
                    })

        # Check if any heredocs remain unclosed
        return any(d for d in heredoc_delimiters if not d['closed'])

    def _has_unclosed_expansion(self, text: str) -> bool:
        """Check if text contains unclosed expansions."""
        # Track open/close counts for each expansion type

        # Command substitution $()
        depth = 0
        i = 0
        while i < len(text):
            if i + 1 < len(text) and text[i:i+2] == '$(':
                depth += 1
                i += 2
            elif text[i] == ')' and depth > 0:
                depth -= 1
                i += 1
            else:
                i += 1
        if depth > 0:
            return True

        # Arithmetic expansion $(())
        i = 0
        while i < len(text):
            if i + 2 < len(text) and text[i:i+3] == '$((':
                # Find the closing ))
                j = i + 3
                paren_count = 2
                while j < len(text) and paren_count > 0:
                    if text[j] == '(':
                        paren_count += 1
                    elif text[j] == ')':
                        paren_count -= 1
                    j += 1
                if paren_count > 0:
                    return True
                i = j
            else:
                i += 1

        # Brace expansion {...}
        brace_depth = 0
        in_brace_expansion = False
        i = 0
        while i < len(text):
            if text[i] == '{':
                # Check if this looks like a brace expansion
                # Look for comma or .. sequence
                j = i + 1
                while j < len(text) and text[j] not in '{}':
                    if text[j] == ',' or (j + 1 < len(text) and text[j:j+2] == '..'):
                        in_brace_expansion = True
                        break
                    j += 1
                if in_brace_expansion:
                    brace_depth += 1
                i += 1
            elif text[i] == '}' and brace_depth > 0:
                brace_depth -= 1
                if brace_depth == 0:
                    in_brace_expansion = False
                i += 1
            else:
                i += 1
        if brace_depth > 0:
            return True

        # Parameter expansion ${...}
        i = 0
        while i < len(text):
            if i + 1 < len(text) and text[i:i+2] == '${':
                # Find the closing }
                j = i + 2
                brace_count = 1
                while j < len(text) and brace_count > 0:
                    if text[j] == '{':
                        brace_count += 1
                    elif text[j] == '}':
                        brace_count -= 1
                    j += 1
                if brace_count > 0:
                    return True
                i = j
            else:
                i += 1

        # Backtick command substitution
        backtick_count = text.count('`')
        if backtick_count % 2 != 0:
            return True

        return False

    def _extract_context_from_error(self, error_msg: str) -> Optional[str]:
        """Extract parsing context from error message.

        Args:
            error_msg: Parser error message

        Returns:
            Context keyword (e.g., 'for', 'if', 'then') or None
        """
        # Map error patterns to context keywords
        # Some patterns map to specific contexts, others need buffer analysis
        patterns = {
            "Expected 'fi'": 'if',
            "Expected TokenType.FI": 'if',
            "Expected FI": 'if',

            "Expected 'esac'": 'case',
            "Expected TokenType.ESAC": 'case',
            "Expected ESAC": 'case',

            "Expected 'then'": 'if',  # if condition, waiting for then
            "Expected TokenType.THEN": 'if',
            "Expected THEN": 'if',

            "Expected 'done'": None,  # Could be for, while, or until - need buffer check
            "Expected TokenType.DONE": None,
            "Expected DONE": None,

            "Expected 'do'": None,  # Could be for, while, until, or select - need buffer check
            "Expected TokenType.DO": None,
            "Expected DO": None,

            "Expected '}'": 'function',  # Function body or brace group
            "Expected TokenType.RBRACE": 'function',

            "Expected ')'": None,  # Could be subshell or function - need buffer check
            "Expected TokenType.RPAREN": None,

            "Expected ']]'": 'test',  # Enhanced test expression
            "Expected TokenType.DOUBLE_RBRACKET": 'test',
            "Expected DOUBLE_RBRACKET": 'test',
        }

        # Check each pattern
        for pattern, context in patterns.items():
            if pattern in error_msg:
                return context

        return None

    def _update_context_stack(self, command: str, error_msg: str):
        """Update context stack based on command buffer and error message.

        Args:
            command: Full command buffer so far
            error_msg: Parser error message
        """
        # Extract basic context from error
        error_context = self._extract_context_from_error(error_msg)

        # Clear and rebuild context stack from buffer analysis
        self.context_stack = []

        # Analyze buffer to find open constructs
        # We need to track both opening and closing keywords
        words = command.split()

        # Stack to track nesting (can have multiple contexts at different levels)
        temp_stack = []

        i = 0
        while i < len(words):
            word = words[i].strip()

            # Check for opening keywords
            if word in ('for', 'while', 'until', 'select'):
                # Add loop context
                temp_stack.append({'type': word, 'state': 'condition'})
                i += 1

            elif word == 'if':
                # Add if context
                temp_stack.append({'type': 'if', 'state': 'condition'})
                i += 1

            elif word == 'then':
                # Transition if from condition to then
                for j in range(len(temp_stack) - 1, -1, -1):
                    if temp_stack[j]['type'] in ('if', 'elif') and temp_stack[j]['state'] in ('condition', 'elif'):
                        temp_stack[j]['state'] = 'then'
                        break
                i += 1

            elif word == 'elif':
                # Change last if/then to elif
                for j in range(len(temp_stack) - 1, -1, -1):
                    if temp_stack[j]['type'] in ('if', 'elif', 'then') and temp_stack[j]['state'] in ('then', 'condition', 'elif'):
                        temp_stack[j]['type'] = 'elif'
                        temp_stack[j]['state'] = 'condition'
                        break
                i += 1

            elif word == 'else':
                # Change last if/then to else
                for j in range(len(temp_stack) - 1, -1, -1):
                    if temp_stack[j]['type'] in ('if', 'elif', 'then') and temp_stack[j]['state'] in ('then', 'condition', 'elif'):
                        temp_stack[j]['type'] = 'else'
                        temp_stack[j]['state'] = 'else'
                        break
                i += 1

            elif word == 'do':
                # Transition loop from condition to body
                for j in range(len(temp_stack) - 1, -1, -1):
                    if temp_stack[j]['type'] in ('for', 'while', 'until', 'select') and temp_stack[j]['state'] == 'condition':
                        temp_stack[j]['state'] = 'body'
                        break
                i += 1

            elif word == 'case':
                temp_stack.append({'type': 'case', 'state': 'open'})
                i += 1

            elif word in ('function', '()'):
                # Function definition
                temp_stack.append({'type': 'function', 'state': 'open'})
                i += 1

            elif word == '(':
                # Could be subshell or function
                if i > 0 and words[i-1].replace('()', '').isidentifier():
                    temp_stack.append({'type': 'function', 'state': 'open'})
                else:
                    temp_stack.append({'type': 'subshell', 'state': 'open'})
                i += 1

            elif word == '{':
                temp_stack.append({'type': 'brace', 'state': 'open'})
                i += 1

            elif word == '[[':
                temp_stack.append({'type': 'test', 'state': 'open'})
                i += 1

            # Check for closing keywords that remove contexts
            elif word == 'fi':
                # Close the most recent if/elif/else/then
                for j in range(len(temp_stack) - 1, -1, -1):
                    if temp_stack[j]['type'] in ('if', 'elif', 'else', 'then'):
                        temp_stack.pop(j)
                        break
                i += 1

            elif word == 'done':
                # Close the most recent loop
                for j in range(len(temp_stack) - 1, -1, -1):
                    if temp_stack[j]['type'] in ('for', 'while', 'until', 'select'):
                        temp_stack.pop(j)
                        break
                i += 1

            elif word == 'esac':
                # Close the most recent case
                for j in range(len(temp_stack) - 1, -1, -1):
                    if temp_stack[j]['type'] == 'case':
                        temp_stack.pop(j)
                        break
                i += 1

            elif word == '}':
                # Close the most recent brace group or function
                for j in range(len(temp_stack) - 1, -1, -1):
                    if temp_stack[j]['type'] in ('brace', 'function'):
                        temp_stack.pop(j)
                        break
                i += 1

            elif word == ')':
                # Close the most recent subshell or function
                for j in range(len(temp_stack) - 1, -1, -1):
                    if temp_stack[j]['type'] in ('subshell', 'function'):
                        temp_stack.pop(j)
                        break
                i += 1

            elif word == ']]':
                # Close the most recent test
                for j in range(len(temp_stack) - 1, -1, -1):
                    if temp_stack[j]['type'] == 'test':
                        temp_stack.pop(j)
                        break
                i += 1

            else:
                i += 1

        # Build context stack from temp_stack
        for item in temp_stack:
            # For loops/if, show the current state
            if item['type'] in ('for', 'while', 'until', 'select'):
                self.context_stack.append(item['type'])
            elif item['type'] == 'if':
                # Show 'if' if in condition, 'then' if in body
                if item['state'] == 'then':
                    self.context_stack.append('then')
                else:
                    self.context_stack.append('if')
            elif item['type'] == 'elif':
                if item['state'] == 'then':
                    self.context_stack.append('then')
                else:
                    self.context_stack.append('elif')
            elif item['type'] == 'else':
                self.context_stack.append('else')
            elif item['type'] == 'then':
                self.context_stack.append('then')
            else:
                self.context_stack.append(item['type'])

        # If error_context provides specific info and stack is empty, use it
        if not self.context_stack and error_context:
            self.context_stack.append(error_context)
