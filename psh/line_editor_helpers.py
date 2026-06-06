"""Pure helpers for the line editor.

Extracted from ``LineEditor`` (which is otherwise a single cohesive, stateful
class) to isolate logic that has no dependency on editor state and is therefore
worth testing on its own.
"""


def convert_multiline_to_single(multiline_cmd: str) -> str:
    """Convert a multi-line command to a single-line representation.

    Used when recalling a multi-line history entry into the single-line editor:
    control structures and function bodies are re-joined with ``;`` separators,
    and plain backslash-continued input is joined with spaces. Pure function —
    no editor state involved.
    """
    # Split into lines and strip whitespace
    lines = [line.strip() for line in multiline_cmd.split('\n')]

    # Analyze the command structure to determine proper joining
    first_line = lines[0] if lines else ""

    # For control structures, join with semicolons
    if any(first_line.startswith(kw) for kw in ['for ', 'while ', 'if ', 'case ']):
        result = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if not line:  # Skip empty lines
                i += 1
                continue

            # Handle for loops specially
            if line.startswith('for ') and i + 1 < len(lines) and lines[i + 1] == 'do':
                result.append(line + '; do')
                i += 2  # Skip the 'do' line
            elif line.startswith('while ') and i + 1 < len(lines) and lines[i + 1] == 'do':
                result.append(line + '; do')
                i += 2  # Skip the 'do' line
            elif line == 'do':
                # Standalone 'do' - was already handled
                i += 1
            elif line == 'done':
                result.append('; done')
                i += 1
            elif line == 'then':
                result[-1] += '; then'
                i += 1
            elif line == 'else':
                result.append('; else')
                i += 1
            elif line == 'fi':
                result.append('; fi')
                i += 1
            elif line == 'esac':
                result.append('; esac')
                i += 1
            elif line.endswith(';;'):
                # Don't add extra semicolon
                if result and not result[-1].endswith((';', 'then', 'do', 'else', ')')):
                    result.append('; ' + line)
                else:
                    result.append(' ' + line)
                i += 1
            elif line.endswith(')') and not line.startswith('('):
                # Case pattern
                if result and result[-1] != first_line:
                    result.append(' ' + line)
                else:
                    result.append(' ' + line)
                i += 1
            else:
                # Regular command line
                if result and not result[-1].endswith((';', 'then', 'do', 'else')):
                    result.append('; ' + line)
                else:
                    result.append(' ' + line if result else line)
                i += 1

        return ''.join(result)

    # For function definitions
    elif first_line.endswith('()') or first_line.endswith('() {'):
        # Join function body with semicolons
        if first_line.endswith('()'):
            result = first_line + ' { '
            body_start = 1
        else:
            result = first_line + ' '
            body_start = 1

        for i in range(body_start, len(lines)):
            line = lines[i]
            if line == '}':
                result += '; }'
            elif line:
                if not result.endswith((' { ', '; ')):
                    result += '; '
                result += line

        return result

    # For simple multi-line with backslash continuation
    else:
        # Just join with spaces
        return ' '.join(lines)
