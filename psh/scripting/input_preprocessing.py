#!/usr/bin/env python3
"""Input preprocessing for PSH shell.

This module handles preprocessing of shell input before tokenization,
including line continuation processing according to POSIX specification.
"""

from typing import List, Optional, Tuple


def process_line_continuations(text: str,
                               drop_dangling_at_eof: bool = False) -> str:
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

    Only a bare backslash-newline (``\\<LF>``) is a continuation. A
    ``\\<CR><LF>`` is NOT joined — the backslash escapes the CR (a literal CR
    word character) and the LF is a command boundary, exactly as bash treats
    it. (The file reader's dos2unix normalization already strips a trailing CR
    before this runs, so that documented divergence is unaffected; the
    CR-keeping stdin/``-c`` paths now match bash here.)

    ``drop_dangling_at_eof`` selects bash's STREAM-input rule for a
    continuation with nothing after it: when *text* is the final gathered
    buffer of an input that reads through a byte stream (a script file,
    stdin, a ``/dev/fd`` process-substitution script), a trailing backslash
    at true end of input is DISCARDED — ``echo hi \\`` at EOF runs
    ``echo hi``. String-fed inputs (``-c``, ``eval``, ``source``) keep the
    backslash as a literal word character instead (bash does the same), so
    they pass False. The drop obeys the same context rules as joining: a
    single-quoted or comment backslash is literal either way, and a QUOTED
    heredoc body keeps its trailing backslash. (Probe-verified against
    bash 5.2, tmp/contcarry/.)

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
        heredoc_terminator_matches,
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
            if heredoc_terminator_matches(line, word, strip_tabs):
                pending.pop(0)
            elif not quoted:
                while _ends_with_continuation(line):
                    if i < len(lines):
                        line = _drop_continuation(line) + lines[i]
                        i += 1
                    elif drop_dangling_at_eof:
                        # Dangling continuation at true end of input: a
                        # stream-read unquoted heredoc body drops it (bash).
                        line = _drop_continuation(line)
                    else:
                        break
            out.append(line)
            continue

        # Command text: join continuations. The trailing backslash must be
        # outside single quotes and outside a comment (a comment, when
        # present, always runs to the end of the line).
        while (_ends_with_continuation(line)
                and not eol_backslash_is_literal(line, quote)):
            if i < len(lines):
                line = _drop_continuation(line) + lines[i]
                i += 1
            elif drop_dangling_at_eof:
                # Dangling continuation at true end of input: stream
                # sources drop it (bash) — `echo hi \` at EOF runs `echo hi`.
                line = _drop_continuation(line)
            else:
                break
        out.append(line)
        markers, quote = scan_line_heredoc_markers(line, quote)
        pending.extend(markers)

    return '\n'.join(out)


def _ends_with_continuation(line: str) -> bool:
    """True when *line* ends with an unescaped backslash (an odd-length
    trailing run).

    A trailing ``\\<CR>`` is deliberately NOT a continuation: bash only honors
    a bare backslash-newline pair, so ``\\<CR><LF>`` is a backslash escaping the
    CR (a literal CR word character) followed by a command boundary, never a
    join. On the file path a lone trailing CR is already dropped by the reader's
    documented dos2unix normalization, so no CR reaches here; on the CR-keeping
    stdin/``-c`` paths this rule matches bash instead of splicing the lines.
    """
    run = len(line) - len(line.rstrip('\\'))
    return run % 2 == 1


def _drop_continuation(line: str) -> str:
    """Remove the trailing continuation backslash."""
    return line[:-1]
