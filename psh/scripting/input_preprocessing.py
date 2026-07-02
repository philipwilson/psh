#!/usr/bin/env python3
"""Input preprocessing for PSH shell.

This module handles preprocessing of shell input before tokenization,
including line continuation processing according to POSIX specification.
"""

from typing import List, Optional, Tuple


def process_line_continuations(text: str) -> str:
    """
    Process line continuation sequences in shell input.

    According to POSIX, an unquoted backslash-newline pair is removed
    entirely from the input before tokenization. Context decides whether
    the backslash is "unquoted" (matching bash):

    * in command text (including inside double quotes) the pair is a
      continuation — removed;
    * inside single quotes both characters are literal — kept;
    * inside a comment the backslash is comment text and the newline ends
      the comment — kept (joining would swallow the next command line);
    * inside the body of a heredoc with a QUOTED delimiter every character
      is literal — kept (a trailing ``\\`` in a ``<<'EOF'`` body survives);
    * inside the body of a heredoc with an unquoted delimiter the pair is
      removed while the body is read, so a terminator on the joined-away
      next line fuses into the body (bash does the same).

    Examples:
        >>> process_line_continuations("echo hello \\\\\\nworld")
        'echo hello world'

        >>> process_line_continuations("echo 'hello \\\\\\nworld'")
        "echo 'hello \\\\\\nworld'"  # No processing inside single quotes
    """
    if '\\' not in text:
        return text
    from ..utils.heredoc_detection import (
        eol_backslash_is_literal,
        scan_line_heredoc_markers,
    )

    lines = text.split('\n')
    out: List[str] = []
    # Heredocs opened on an earlier command line whose bodies we are now
    # inside, as (terminator, strip_tabs, quoted) triples in body order.
    pending: List[Tuple[str, bool, bool]] = []
    quote: Optional[str] = None  # quote state carried across command lines

    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1

        if pending:
            word, strip_tabs, quoted = pending[0]
            check = line.lstrip('\t') if strip_tabs else line
            if check == word:
                pending.pop(0)
            elif not quoted:
                while _ends_with_continuation(line) and i < len(lines):
                    line = _drop_continuation(line) + lines[i]
                    i += 1
            out.append(line)
            continue

        # Command text: join continuations. The trailing backslash must be
        # outside single quotes and outside a comment (a comment, when
        # present, always runs to the end of the line).
        while (i < len(lines) and _ends_with_continuation(line)
                and not eol_backslash_is_literal(line, quote)):
            line = _drop_continuation(line) + lines[i]
            i += 1
        out.append(line)
        markers, quote = scan_line_heredoc_markers(line, quote)
        pending.extend(markers)

    return '\n'.join(out)


def _ends_with_continuation(line: str) -> bool:
    """True when *line* ends with an unescaped backslash (an odd-length
    trailing run), tolerating the CR of ``\\<CR><LF>`` input."""
    if line.endswith('\r'):
        line = line[:-1]
    run = len(line) - len(line.rstrip('\\'))
    return run % 2 == 1


def _drop_continuation(line: str) -> str:
    """Remove the continuation backslash (and the CR of ``\\<CR><LF>``)."""
    if line.endswith('\r'):
        line = line[:-1]
    return line[:-1]
