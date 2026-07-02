"""Constants and character sets for the lexer."""

import string

# Constants for character sets
SPECIAL_VARIABLES = set('?$!#@*-') | set(string.digits)

# Keywords that need context checking. break/continue/return are NOT here:
# they are ordinary builtins in bash (definable as functions, redirectable,
# composable in pipelines/lists), not reserved words.
KEYWORDS = {
    'if', 'then', 'else', 'elif', 'fi',
    'while', 'until', 'do', 'done',
    'for', 'in',
    'case', 'esac',
    'select',
    'function',
    'time',
}
