"""History expansion implementation for PSH.

This module implements bash-compatible history expansion, processing history
references like !!, !n, !-n, and !string before commands are tokenized.
"""

import re
import sys
from typing import List, Optional

# A line containing one of these history references (!!, !n, !-n, !word,
# !?word?) must be passed straight to execution rather than parse-tested for
# completeness or recorded verbatim in history. This single source of truth is
# shared by the multiline/line-editor completeness checks and the
# source-processor history filtering (previously copied inline at four sites).
HISTORY_REFERENCE_RE = re.compile(
    r'(?:^|\s)!(?:!|[0-9]+|-[0-9]+|[a-zA-Z][a-zA-Z0-9]*|\?[^?]*\?)(?:\s|$)'
)


def contains_history_reference(text: str) -> bool:
    """Return True if *text* contains a history reference (``!!``, ``!n``, …)."""
    return HISTORY_REFERENCE_RE.search(text) is not None


# Sentinels used by the event/word-designator resolvers below to distinguish
# "no such event" and "malformed word designator" from a normal string result.
_EVENT_NOT_FOUND = object()
_BAD_WORD_SPECIFIER = object()


class HistoryExpander:
    """Handles history expansion for the shell."""

    def __init__(self, shell):
        self.shell = shell
        self.state = shell.state

    def expand_history(
        self,
        command: str,
        print_expansion: bool = True,
        report_errors: bool = True,
    ) -> Optional[str]:
        """Expand history references in a command string.

        Args:
            command: The command string to expand
            print_expansion: Whether to print the expanded command to stdout
            report_errors: Whether to print "event not found" errors

        Supports:
        - !! : Previous command
        - !n : Command number n
        - !-n : n commands back
        - !string : Most recent command starting with string
        - !?string? : Most recent command containing string
        """
        # Skip expansion if history expansion is disabled
        if not self.state.options.get('histexpand', True):
            return command

        # Get history from the shell
        history = self.state.history

        # Track if we made any expansions
        expanded = False
        result = []
        i = 0

        # Process the command character by character to handle quotes properly
        while i < len(command):
            char = command[i]

            # Handle single quotes - no expansion inside
            if char == "'":
                # Find the closing quote
                j = i + 1
                while j < len(command) and command[j] != "'":
                    j += 1
                # Include the entire quoted string
                result.append(command[i:j+1] if j < len(command) else command[i:])
                i = j + 1
                continue

            # Handle double quotes - no history expansion inside
            elif char == '"':
                # Find the closing quote, handling escapes
                j = i + 1
                while j < len(command):
                    if command[j] == '"' and (j == i + 1 or command[j-1] != '\\'):
                        break
                    j += 1
                # Include the entire quoted string
                result.append(command[i:j+1] if j < len(command) else command[i:])
                i = j + 1
                continue

            # Handle history expansion
            elif char == '!' and i + 1 < len(command) and command[i+1] != '=':
                # Skip if we're inside [...] bracket expression (for glob patterns like [!abc])
                # Look backwards for [ without closing ]
                j = i - 1
                bracket_depth = 0
                in_bracket = False
                while j >= 0:
                    if command[j] == ']':
                        bracket_depth += 1
                    elif command[j] == '[':
                        if bracket_depth == 0:
                            in_bracket = True
                            break
                        else:
                            bracket_depth -= 1
                    j -= 1

                if in_bracket:
                    # We're inside [...], don't do history expansion
                    result.append(char)
                    i += 1
                    continue

                # Skip if we're inside ${...} parameter expansion
                # Look backwards for ${ without closing }
                j = i - 1
                brace_depth = 0
                while j >= 0:
                    if command[j] == '}':
                        brace_depth += 1
                    elif command[j] == '{' and j > 0 and command[j-1] == '$':
                        if brace_depth == 0:
                            # We're inside ${...}, skip history expansion
                            result.append(char)
                            i += 1
                            break
                        else:
                            brace_depth -= 1
                    j -= 1
                else:
                    # Check if we're inside $((...)) arithmetic expansion
                    # Look backwards for $(( without closing ))
                    j = i - 1
                    paren_depth = 0
                    while j >= 1:
                        if j < len(command) - 1 and command[j] == ')' and command[j+1] == ')':
                            paren_depth += 1
                            j -= 1  # Skip the extra )
                        elif j > 0 and command[j-1] == '$' and command[j] == '(' and j < len(command) - 1 and command[j+1] == '(':
                            if paren_depth == 0:
                                # We're inside $((...)), skip history expansion
                                result.append(char)
                                i += 1
                                break
                            else:
                                paren_depth -= 1
                            j -= 1  # Skip the extra (
                        j -= 1
                    else:
                        # Not inside ${...} or $((...)), continue with history expansion.
                        #
                        # A history reference is an EVENT designator (!!, !n, !-n,
                        # !string, !?string?) optionally followed by a WORD
                        # designator (:n, :^, :$, :*, :n-m, ...). The shorthands
                        # !^, !$ and !* are an implicit !! event plus a word
                        # designator. Resolve the event first, then apply any
                        # word designator to the event's command line.
                        resolved = self._resolve_event(command, i, history)
                        if resolved is None:
                            # ! not followed by a recognized event pattern: treat
                            # it as a literal character (e.g. [[ ! ... ]], a!=b).
                            result.append(char)
                            i += 1
                            continue

                        event_text, event_label, j = resolved
                        if event_text is _EVENT_NOT_FOUND:
                            if report_errors:
                                print(f"psh: {event_label}: event not found",
                                      file=sys.stderr)
                            return None

                        # Apply an optional word designator to the event text.
                        selected = self._apply_word_designator(command, j, event_text)
                        if selected is _BAD_WORD_SPECIFIER:
                            if report_errors:
                                spec = command[j:self._word_designator_end(command, j)]
                                print(f"psh: {spec}: bad word specifier",
                                      file=sys.stderr)
                            return None

                        text, j = selected
                        expanded = True
                        result.append(text)
                        i = j
                        continue

                # If we broke from the while loop (we're inside ${...}), skip regular char processing
                continue

            # Regular character
            result.append(char)
            i += 1

        final_result = ''.join(result)

        # If we made expansions, print the expanded command (only when print_expansion is True)
        if expanded and print_expansion and sys.stdin.isatty():
            print(final_result)

        return final_result

    def _resolve_event(self, command: str, i: int, history):
        """Resolve the event designator beginning at ``command[i]`` (a ``!``).

        Returns a ``(event_text, event_label, end_index)`` tuple where
        ``end_index`` is the index just past the event token (positioned at any
        following word designator), or ``None`` if ``!`` does not begin a
        recognized event pattern (so the caller treats it as a literal).

        ``event_text`` is the matched command line, or the ``_EVENT_NOT_FOUND``
        sentinel if the event reference matched no history entry.
        """
        n = len(command)
        c1 = command[i + 1] if i + 1 < n else ''

        # !! - previous command
        if c1 == '!':
            if history:
                return history[-1], '!!', i + 2
            return _EVENT_NOT_FOUND, '!!', i + 2

        # !$, !^, !*, !:n - implicit !! event plus a word designator. The word
        # designator itself is handled by _apply_word_designator, which is
        # invoked at the same end index, so we leave the cursor on the sigil
        # (or on the ':' introducing a numeric designator).
        if c1 in '$^*:':
            if history:
                return history[-1], '!!', i + 1
            return _EVENT_NOT_FOUND, '!' + c1, i + 1

        # !n / !-n - numeric event reference
        if c1 == '-' or c1.isdigit():
            j = i + 1
            if command[j] == '-':
                j += 1
            while j < n and command[j].isdigit():
                j += 1
            if j == i + 1 or (command[i + 1] == '-' and j == i + 2):
                return None  # bare !- with no digits
            num = int(command[i + 1:j])
            label = f'!{command[i + 1:j]}'
            if num > 0:
                if num <= len(history):
                    return history[num - 1], label, j
                return _EVENT_NOT_FOUND, label, j
            else:
                if abs(num) <= len(history):
                    return history[num], label, j
                return _EVENT_NOT_FOUND, label, j

        # !?string? - most recent command containing string
        if c1 == '?':
            j = i + 2
            while j < n and command[j] != '?':
                j += 1
            search_str = command[i + 2:j]
            end = j + 1 if j < n else j  # skip closing '?'
            for k in range(len(history) - 1, -1, -1):
                if search_str in history[k]:
                    return history[k], f'!?{search_str}?', end
            return _EVENT_NOT_FOUND, f'!?{search_str}?', end

        # !string - most recent command starting with string
        j = i + 1
        while j < n and not command[j].isspace() and command[j] not in '!?;|&(){}[]<>:':
            j += 1
        if j > i + 1:
            prefix = command[i + 1:j]
            for k in range(len(history) - 1, -1, -1):
                if history[k].startswith(prefix):
                    return history[k], f'!{prefix}', j
            return _EVENT_NOT_FOUND, f'!{prefix}', j

        # ! not followed by a recognized pattern (e.g. trailing !, "! ").
        return None

    @staticmethod
    def _split_words(line: str):
        """Split a history line into words for word designators.

        Like bash, splitting respects quoting: a single- or double-quoted
        span is one word and the quote characters are kept as part of the word
        (history stores the literal typed line). Whitespace otherwise
        separates words.
        """
        words = []
        cur = []
        in_word = False
        quote = None
        i = 0
        n = len(line)
        while i < n:
            ch = line[i]
            if quote:
                cur.append(ch)
                if ch == quote:
                    quote = None
                i += 1
                continue
            if ch in '\'"':
                quote = ch
                cur.append(ch)
                in_word = True
            elif ch.isspace():
                if in_word:
                    words.append(''.join(cur))
                    cur = []
                    in_word = False
            else:
                cur.append(ch)
                in_word = True
            i += 1
        if in_word:
            words.append(''.join(cur))
        return words

    def _word_designator_end(self, command: str, j: int) -> int:
        """Return the index just past the word designator starting at ``j``.

        Used only to build the "bad word specifier" error string. ``j`` points
        at the sigil (``$``/``^``/``*``) or at the ``:`` introducing a numeric
        designator.
        """
        n = len(command)
        if j < n and command[j] in '$^*':
            return j + 1
        k = j
        if k < n and command[k] == ':':
            k += 1
        while k < n and (command[k].isdigit() or command[k] in '-*$^'):
            k += 1
        return k

    def _apply_word_designator(self, command: str, j: int, event_text: str):
        """Apply an optional word designator at ``command[j]`` to ``event_text``.

        Returns a ``(selected_text, end_index)`` tuple, or the
        ``_BAD_WORD_SPECIFIER`` sentinel on a malformed/out-of-range designator.

        Supported designators (words are 0-indexed; word 0 is the command):
        ``:0`` ``:n`` ``:^`` ``:$`` ``:*`` ``:n-m`` ``:n-`` ``:n*``, and the
        bare sigils ``^`` ``$`` ``*`` (shorthand for ``:1`` ``:$`` ``:1-$``).
        With no designator the whole event line is returned unchanged.
        """
        n = len(command)
        words = self._split_words(event_text)
        # last index of an *argument* word ($ in bash = last word overall).
        last = len(words) - 1

        # Determine the designator text and its end index.
        spec = None
        end = j
        if j < n and command[j] in '$^*':
            # Bare sigil shorthand: !$ !^ !*
            spec = command[j]
            end = j + 1
        elif j < n and command[j] == ':':
            k = j + 1
            while k < n and (command[k].isdigit() or command[k] in '-*$^'):
                k += 1
            spec = command[j + 1:k]
            end = k
        else:
            # No word designator: whole line.
            return event_text, j

        # Resolve the designator to a (start, stop) inclusive word range.
        def resolve_index(token):
            if token == '$':
                return last
            if token == '^':
                return 1
            if token.isdigit():
                return int(token)
            return None

        if spec == '^':
            start = stop = 1
        elif spec == '$':
            start = stop = last
        elif spec in ('*',):
            # All arguments: words 1..last. Empty (not an error) if no args.
            if last < 1:
                return '', end
            start, stop = 1, last
        elif '-' in spec and not spec.startswith('-'):
            # n-m or n-  (range)
            lo, _, hi = spec.partition('-')
            start = resolve_index(lo)
            if hi == '':
                # n- : word n through the second-to-last word
                stop = last - 1
            else:
                stop = resolve_index(hi)
            if start is None or stop is None:
                return _BAD_WORD_SPECIFIER
        elif spec.endswith('*') and spec[:-1].isdigit():
            # n* : word n through last
            start = int(spec[:-1])
            stop = last
        elif spec == '' or spec is None:
            return _BAD_WORD_SPECIFIER
        else:
            idx = resolve_index(spec)
            if idx is None:
                return _BAD_WORD_SPECIFIER
            start = stop = idx

        # Validate the range against the available words. Bash is strict:
        # an out-of-range single index or range end is a bad word specifier,
        # EXCEPT that :* / n* / n- yielding nothing is allowed when there are
        # simply no further words.
        if start < 0 or stop < 0 or start > last or stop > last or start > stop:
            # An empty :* (no args) was already handled above. A "n-" or "n*"
            # that lands past the end with start<=last+... follows bash: out of
            # range is a bad specifier.
            return _BAD_WORD_SPECIFIER

        return ' '.join(words[start:stop + 1]), end

    def is_history_expansion_char(self, char: str) -> bool:
        """Check if a character might start a history expansion."""
        return char == '!'

    def get_history_list(self) -> List[str]:
        """Get the current history list."""
        return self.state.history.copy()

    def get_history_item(self, index: int) -> Optional[str]:
        """Get a specific history item by index (1-based)."""
        if 1 <= index <= len(self.state.history):
            return self.state.history[index - 1]
        return None
