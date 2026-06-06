"""Heredoc detection heuristics.

Distinguishes a real ``<<EOF`` heredoc from a ``<<`` bit-shift (arithmetic) or
a ``<<<`` here-string, and tracks whether a heredoc's delimiter has appeared
yet. This is the single source of truth shared by the script/`-c`/stdin path
(`scripting/source_processor.py`) and the interactive multiline path
(`multiline_handler.py`), which previously carried diverged copies.
"""

import re

# A heredoc start: ``<<WORD``, ``<<-WORD``, ``<< WORD``, ``<< 'WORD'``,
# ``<< \WORD``. The look-around rejects a third ``<`` on either side so a
# here-string (``<<<WORD``) is not mistaken for a heredoc.
#   group(1): '-' for <<- (strip leading tabs)
#   group(2): surrounding quote, if the delimiter is quoted
#   group(3): a leading backslash on the delimiter (escaped delimiter)
#   group(4): the delimiter word
HEREDOC_MARKER_RE = re.compile(r'(?<!<)<<(?!<)(-?)\s*([\'"]?)(\\\s*)?(\w+)\2')


def _scan_arith_or_cmdsub(line: str, position: int, opener: str, open_len: int) -> bool:
    """True if *position* falls within a ``opener … )`` region on *line*.

    ``opener`` is ``'$(('`` / ``'$('`` / ``'(('``; ``open_len`` is how many
    parens it contributes to the nesting depth (2 for the arithmetic forms,
    1 for command substitution).
    """
    start = -1
    depth = 0
    i = 0
    while i < len(line):
        if line[i:i + len(opener)] == opener and start < 0:
            # For bare '((' don't re-trigger on the '((' inside a '$(('.
            if opener == '((' and i > 0 and line[i - 1] == '$':
                i += 1
                continue
            if i <= position:
                start = i
                depth = open_len
                i += len(opener)
                continue
            break
        if start >= 0:
            if line[i] == '(':
                depth += 1
            elif line[i] == ')':
                depth -= 1
                if depth == 0:
                    if start <= position <= i:
                        return True
                    start = -1
        i += 1
    return False


def is_inside_expansion(line: str, position: int) -> bool:
    """True if *position* on *line* is inside an expansion where ``<<`` is not
    a heredoc: ``$((…))`` / bare ``((…))`` arithmetic, ``$(…)`` command
    substitution, or ``` `…` ``` backticks.
    """
    if _scan_arith_or_cmdsub(line, position, '$((', 2):
        return True
    if _scan_arith_or_cmdsub(line, position, '$(', 1):
        return True
    if _scan_arith_or_cmdsub(line, position, '((', 2):
        return True

    # Backtick command substitution
    backtick_start = -1
    i = 0
    while i < len(line):
        if line[i] == '`':
            if backtick_start == -1:
                if i <= position:
                    backtick_start = i
            else:
                if backtick_start <= position <= i:
                    return True
                backtick_start = -1
        i += 1
    return False


def has_unclosed_heredoc(command: str) -> bool:
    """True if *command* opens a heredoc whose delimiter has not yet appeared.

    Ignores ``<<`` that is bit-shift (arithmetic) or a ``<<<`` here-string, and
    ``<<`` inside command substitutions/backticks. Used to decide whether more
    input lines are still needed to complete the command.
    """
    # Fast path / arithmetic-only exclusion: if every '<<' is bit-shift inside
    # arithmetic, there is no heredoc at all.
    if not contains_heredoc(command):
        return False

    delimiters = []
    for line in command.split('\n'):
        if any(not d['closed'] for d in delimiters):
            # Inside an open heredoc: does this line close one?
            for d in delimiters:
                if not d['closed']:
                    check = line.lstrip('\t') if d['strip_tabs'] else line
                    if check.rstrip() == d['word']:
                        d['closed'] = True
                        break
        else:
            for match in HEREDOC_MARKER_RE.finditer(line):
                if is_inside_expansion(line, match.start()):
                    continue
                delimiters.append({
                    'word': match.group(4),
                    'strip_tabs': bool(match.group(1)),
                    'closed': False,
                })
    return any(not d['closed'] for d in delimiters)


def contains_heredoc(command_string: str) -> bool:
    """Check if command contains heredoc operators (not bit-shift in arithmetic).

    Returns True if the command contains << that's likely a heredoc,
    False if << only appears inside arithmetic expressions.
    """
    if '<<' not in command_string:
        return False

    # Quick check: if we have arithmetic expressions, check if << is inside them
    # This is a simple heuristic that handles the common case
    if '((' in command_string:
        # Find all arithmetic expression boundaries
        arith_start = []
        arith_end = []
        i = 0
        while i < len(command_string) - 1:
            if command_string[i:i+2] == '((':
                arith_start.append(i)
                i += 2
            elif command_string[i:i+2] == '))':
                arith_end.append(i + 2)
                i += 2
            else:
                i += 1

        # Find all << positions
        heredoc_positions = []
        i = 0
        while i < len(command_string) - 1:
            if command_string[i:i+2] == '<<':
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

    # Default: assume << is a heredoc
    return True
