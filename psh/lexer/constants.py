"""Constants and character sets for the lexer."""

import string

# Constants for character sets
VARIABLE_START_CHARS = set(string.ascii_letters + '_')
VARIABLE_CHARS = set(string.ascii_letters + string.digits + '_')
SPECIAL_VARIABLES = set('?$!#@*-') | set(string.digits)

# Escape sequences in different contexts
# In double quotes, bash only processes: \", \\, \$, \`, and \newline
# Other sequences like \n, \t, \r are preserved literally
DOUBLE_QUOTE_ESCAPES = {
    '\"': '\"',
    '\\': '\\',
    '`': '`',
    # Note: \n, \t, \r are NOT processed in double quotes in bash
    # They are preserved as literal \n, \t, \r
}

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
