#!/usr/bin/env python3
"""Input preprocessing for PSH shell.

This module handles preprocessing of shell input before tokenization,
including line continuation processing according to POSIX specification.
"""


def process_line_continuations(text: str) -> str:
    """
    Process line continuation sequences in shell input.

    According to POSIX, backslash-newline sequences should be removed
    entirely from the input before any other processing occurs.

    Args:
        text: Raw shell input that may contain line continuations

    Returns:
        Text with line continuations processed (removed)

    Examples:
        >>> process_line_continuations("echo hello \\\\nworld")
        'echo hello world'

        >>> process_line_continuations("echo hello\\\\\\\\\\\\nworld")
        'echo hello\\\\\\\\world'  # \\\\\\\\ -> \\\\, \\n removed

        >>> process_line_continuations("echo 'hello \\\\nworld'")
        "echo 'hello \\\\nworld'"  # No processing inside quotes
    """
    if not text:
        return text

    result = []
    i = 0
    in_single_quote = False
    in_double_quote = False

    while i < len(text):
        char = text[i]

        # Track quote state - handle escaped quotes properly
        if char == "'" and not in_double_quote:
            # Check if this quote is escaped by counting preceding backslashes
            backslash_count = 0
            j = i - 1
            while j >= 0 and text[j] == '\\':
                backslash_count += 1
                j -= 1
            # If even number of backslashes (including 0), quote is not escaped
            if backslash_count % 2 == 0:
                in_single_quote = not in_single_quote
            result.append(char)
            i += 1
            continue
        elif char == '"' and not in_single_quote:
            # Check if this quote is escaped
            backslash_count = 0
            j = i - 1
            while j >= 0 and text[j] == '\\':
                backslash_count += 1
                j -= 1
            # If even number of backslashes, quote is not escaped
            if backslash_count % 2 == 0:
                in_double_quote = not in_double_quote
            result.append(char)
            i += 1
            continue

        # Don't process line continuations inside single quotes
        # (but do process them inside double quotes - bash behavior)
        if in_single_quote:
            result.append(char)
            i += 1
            continue

        # Look for line continuation pattern: unescaped \<newline>
        if char == '\\' and i + 1 < len(text):
            # Count consecutive backslashes
            backslash_count = 0
            j = i
            while j < len(text) and text[j] == '\\':
                backslash_count += 1
                j += 1

            # Check what follows the backslashes
            if j < len(text):
                if text[j] == '\n':
                    # If odd number of backslashes, the last one escapes the newline
                    if backslash_count % 2 == 1:
                        # Line continuation: add all but the last backslash, skip \n
                        result.extend('\\' * (backslash_count - 1))
                        i = j + 1  # Skip past the newline
                        continue
                elif text[j] == '\r' and j + 1 < len(text) and text[j + 1] == '\n':
                    # Handle \r\n line endings
                    if backslash_count % 2 == 1:
                        result.extend('\\' * (backslash_count - 1))
                        i = j + 2  # Skip past \r\n
                        continue

            # Not a line continuation - add all backslashes and continue
            result.extend('\\' * backslash_count)
            i = j
            continue

        # Regular character - add to result
        result.append(char)
        i += 1

    return ''.join(result)
