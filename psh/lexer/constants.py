"""Constants and character sets for the lexer."""

import string

# Constants for character sets
SPECIAL_VARIABLES = set('?$!#@*-') | set(string.digits)

# Keywords that need context checking
KEYWORDS = {
    'if', 'then', 'else', 'elif', 'fi',
    'while', 'until', 'do', 'done',
    'for', 'in',
    'case', 'esac',
    'select',
    'function',
    'break', 'continue', 'return'
}
