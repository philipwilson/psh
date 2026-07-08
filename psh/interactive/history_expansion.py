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
# A :s/old/new/ (or :&) modifier that parsed correctly but whose `old` was not
# present in the selected line: bash reports this as "substitution failed", a
# distinct error class from a malformed/out-of-range "bad word specifier".
_SUBSTITUTION_FAILED = object()
_NOT_QUICK_SUB = object()  # leading text is not a ^old^new quick substitution


class HistoryExpander:
    """Handles history expansion for the shell."""

    def __init__(self, shell):
        self.shell = shell
        self.state = shell.state
        # Last :s/old/new/ substitution, for the :& (repeat) modifier.
        self._last_sub = None
        # Set by a :p modifier during one expand_history call: print, don't run.
        self._print_only = False

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

        # ^old^new[^] quick substitution: only when it is the FIRST char of the
        # line (bash). Equivalent to !!:s/old/new/. Handled before the scanner.
        if command.startswith('^'):
            quick = self._expand_quick_substitution(command, history,
                                                     report_errors)
            if quick is not _NOT_QUICK_SUB:
                return quick

        # Per-call print-only flag (set by a :p modifier).
        self._print_only = False

        # Track if we made any expansions
        expanded = False
        result = []
        i = 0
        # History IS expanded inside double quotes (bash); only single quotes
        # and a preceding backslash suppress it. Track double-quote state so a
        # single quote inside "..." is treated as literal text, not a span.
        in_dquote = False

        # Process the command character by character to handle quotes properly
        while i < len(command):
            char = command[i]

            # Single quotes suppress history expansion — but NOT when already
            # inside double quotes (a ' inside "..." is literal text, bash).
            if char == "'" and not in_dquote:
                # Consume the single-quoted span verbatim.
                j = i + 1
                while j < len(command) and command[j] != "'":
                    j += 1
                result.append(command[i:j+1] if j < len(command) else command[i:])
                i = j + 1
                continue

            # Double quotes do NOT suppress history expansion (bash) — just
            # toggle the state and keep scanning for ! references inside.
            elif char == '"':
                in_dquote = not in_dquote
                result.append(char)
                i += 1
                continue

            # A backslash quotes the next character for history expansion: \!
            # is a literal ! (no expansion). The backslash is KEPT verbatim
            # (bash's history -p keeps it; the lexer removes it later); keeping
            # \" intact also stops that " from toggling the double-quote state.
            elif char == '\\' and i + 1 < len(command):
                result.append(char)
                result.append(command[i + 1])
                i += 2
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

                        # Apply an optional word designator, then any :modifiers
                        # (:h/:t/:r/:e, :s/:gs/:&, :p) to the event text.
                        selected = self._apply_word_designator(command, j, event_text)
                        if selected is not _BAD_WORD_SPECIFIER:
                            text, j = selected
                            selected = self.apply_modifiers(text, command, j)
                        if selected is _BAD_WORD_SPECIFIER:
                            if report_errors:
                                spec = command[j:self._word_designator_end(command, j)]
                                print(f"psh: {spec}: bad word specifier",
                                      file=sys.stderr)
                            return None
                        if selected[0] is _SUBSTITUTION_FAILED:
                            # A :s/old/new/ whose `old` was not found: bash's
                            # distinct "substitution failed" error class.
                            if report_errors:
                                print(f"psh: {selected[1]}: substitution failed",
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

        # A :p modifier prints the expansion and suppresses execution (bash):
        # print it (always, like bash) and return the empty string so the
        # caller runs nothing.
        if self._print_only:
            print(final_result, file=self.shell.stdout)
            return ''

        # If we made expansions, print the expanded command (only when print_expansion is True)
        if expanded and print_expansion and sys.stdin.isatty():
            print(final_result)

        return final_result

    def _expand_quick_substitution(self, command: str, history, report_errors: bool):
        """Expand a ``^old^new[^]`` quick substitution on the previous command.

        Returns the expanded string, ``None`` on error (no history / no match),
        or the ``_NOT_QUICK_SUB`` sentinel if this is not actually a quick sub
        (so the normal scanner runs — e.g. a bare ``^`` with no second ``^``).
        """
        # ^old^new^   (the final ^ is optional; old must be non-empty)
        rest = command[1:]
        sep = rest.find('^')
        if sep < 0:
            return _NOT_QUICK_SUB
        old = rest[:sep]
        tail = rest[sep + 1:]
        end = tail.find('^')
        new = tail if end < 0 else tail[:end]
        suffix = '' if end < 0 else tail[end + 1:]
        if not old:
            return _NOT_QUICK_SUB
        if not history:
            if report_errors:
                print("psh: :s: substitution failed", file=sys.stderr)
            return None
        last = history[-1]
        if old not in last:
            if report_errors:
                print(f"psh: {command}: substitution failed", file=sys.stderr)
            return None
        self._last_sub = (old, new)
        return last.replace(old, new, 1) + suffix

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
        elif (j < n and command[j] == ':' and j + 1 < n
              and (command[j + 1].isdigit() or command[j + 1] in '-*$^')):
            k = j + 1
            while k < n and (command[k].isdigit() or command[k] in '-*$^'):
                k += 1
            spec = command[j + 1:k]
            end = k
        else:
            # No word designator (a ':' here introduces a :modifier, applied by
            # the caller via _apply_modifiers): the whole event line.
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
        elif spec.startswith('-') and len(spec) > 1:
            # -n (the 0-n abbreviation): words 0 through n (bash). So
            # :-2 == :0-2, :-$ == :0-$, :-0 == :0 (just word 0).
            start = 0
            stop = resolve_index(spec[1:])
            if stop is None:
                return _BAD_WORD_SPECIFIER
        elif '-' in spec:
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

    # --- :modifiers (h/t/r/e/s/g&/p) applied after an event[:word] selection ---

    def apply_modifiers(self, text: str, command: str, k: int):
        """Apply a chain of ``:`` modifiers at ``command[k]`` to ``text``.

        Returns ``(new_text, end_index)``, ``_BAD_WORD_SPECIFIER`` on a
        malformed modifier (e.g. ``:&`` with no previous substitution, or an
        unknown modifier letter), or ``(_SUBSTITUTION_FAILED, spec)`` when a
        ``:s`` old-text is absent (``spec`` is the exact modifier text for the
        "substitution failed" diagnostic). Supported: ``:h`` ``:t`` ``:r`` ``:e``
        (pathname head/tail/root/ext on the whole selection), ``:s/old/new/``
        and ``:gs//`` global, ``:&`` (repeat last sub, ``:g&`` global), and
        ``:p`` (print, don't execute — sets a flag the caller honors).
        """
        n = len(command)
        while k < n and command[k] == ':':
            m = k + 1
            glob = False
            if m < n and command[m] in 'ga':  # global prefix for s / &
                glob = True
                m += 1
            mod = command[m] if m < n else ''
            if mod == 'h':
                text = self._mod_head(text); k = m + 1
            elif mod == 't':
                text = self._mod_tail(text); k = m + 1
            elif mod == 'r':
                text = self._mod_root(text); k = m + 1
            elif mod == 'e':
                text = self._mod_ext(text); k = m + 1
            elif mod == 'p':
                self._print_only = True; k = m + 1
            elif mod in ('s', '&'):
                result = self._mod_subst(text, command, m, glob)
                if result is _BAD_WORD_SPECIFIER:
                    return _BAD_WORD_SPECIFIER
                if result[0] is _SUBSTITUTION_FAILED:
                    # Carry the exact modifier spec (this ':' through the end
                    # index) up for the "substitution failed" diagnostic.
                    return _SUBSTITUTION_FAILED, command[k:result[1]]
                text, k = result
            else:
                return _BAD_WORD_SPECIFIER
        return text, k

    @staticmethod
    def _mod_head(text: str) -> str:
        """``:h`` — strip a trailing pathname component (head/dirname)."""
        idx = text.rfind('/')
        return text[:idx] if idx > 0 else (text if idx < 0 else text[:idx])

    @staticmethod
    def _mod_tail(text: str) -> str:
        """``:t`` — the trailing pathname component (tail/basename)."""
        idx = text.rfind('/')
        return text[idx + 1:] if idx >= 0 else text

    @staticmethod
    def _mod_root(text: str) -> str:
        """``:r`` — remove a trailing ``.suffix`` (in the basename)."""
        dot = text.rfind('.')
        slash = text.rfind('/')
        return text[:dot] if dot > slash else text

    @staticmethod
    def _mod_ext(text: str) -> str:
        """``:e`` — keep only a trailing ``.suffix`` (in the basename)."""
        dot = text.rfind('.')
        slash = text.rfind('/')
        return text[dot:] if dot > slash else text

    def _mod_subst(self, text: str, command: str, m: int, glob: bool):
        """Apply ``s<delim>old<delim>new<delim>`` (at ``command[m]=='s'``) or
        ``&`` (repeat the last substitution). Returns ``(text, end)`` on
        success, ``(_SUBSTITUTION_FAILED, end)`` when ``old`` parsed but is
        absent from ``text``, or ``_BAD_WORD_SPECIFIER`` on a malformed
        modifier / missing previous substitution."""
        n = len(command)
        if command[m] == '&':
            if self._last_sub is None:
                return _BAD_WORD_SPECIFIER
            old, new = self._last_sub
            k = m + 1
        else:
            # s<delim>old<delim>new[<delim>]
            d = m + 1
            if d >= n:
                return _BAD_WORD_SPECIFIER
            delim = command[d]
            # old<delim>new[<delim>] — _scan_until returns the index PAST the
            # delimiter, so `new` resumes exactly where `old` left off.
            old, p = self._scan_until(command, d + 1, delim)
            new, k = self._scan_until(command, p, delim)
            if not old:
                return _BAD_WORD_SPECIFIER
            self._last_sub = (old, new)
        if old not in text:
            # bash reports this as "substitution failed" (not "bad word
            # specifier"); return the end index so the caller can quote the
            # exact modifier spec in the message.
            return _SUBSTITUTION_FAILED, k
        replaced = text.replace(old, new) if glob else text.replace(old, new, 1)
        return replaced, k

    @staticmethod
    def _scan_until(command: str, i: int, delim: str):
        """Scan from ``i`` to the next unescaped ``delim`` (or end). Returns
        ``(text, index_past_delim)``; a ``\\<delim>`` contributes a literal delim."""
        out = []
        n = len(command)
        while i < n and command[i] != delim:
            if command[i] == '\\' and i + 1 < n and command[i + 1] == delim:
                out.append(delim)
                i += 2
                continue
            out.append(command[i])
            i += 1
        # i is at delim (consume it) or at end
        return ''.join(out), (i + 1 if i < n else i)

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
