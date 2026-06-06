"""Shared constants for AST visitor implementations."""

# test/[ ] operator operand classification, shared by the analysis visitors so
# the "an operand after this operator need not be quoted / is compared a certain
# way" knowledge lives in one place.
NUMERIC_COMPARISON_OPERATORS = frozenset({'-eq', '-ne', '-lt', '-le', '-gt', '-ge'})
STRING_COMPARISON_OPERATORS = frozenset({'=', '!='})
FILE_TEST_OPERATORS = frozenset({'-f', '-d', '-e', '-s', '-r', '-w', '-x'})
# Operators after which an operand is the value being tested.
TEST_OPERATORS = (
    FILE_TEST_OPERATORS | STRING_COMPARISON_OPERATORS | NUMERIC_COMPARISON_OPERATORS
)

# Commands considered dangerous — union of all three visitors' lists
DANGEROUS_COMMANDS = {
    'eval': 'Dynamic code execution - high risk of injection',
    'source': 'Loading external scripts - verify source is trusted',
    '.': 'Loading external scripts - verify source is trusted',
    'exec': 'Process replacement - ensure arguments are validated',
}

# Commands that modify system state in sensitive ways
SENSITIVE_COMMANDS = {
    'chmod': 'File permission changes',
    'chown': 'File ownership changes',
    'rm': 'File deletion',
    'dd': 'Low-level disk operations',
    'mkfs': 'Filesystem creation',
    'fdisk': 'Disk partitioning',
}

# Shell builtins — union of enhanced_validator and linter lists
SHELL_BUILTINS = {
    # I/O
    'echo', 'printf', 'read',
    # Navigation
    'cd', 'pwd', 'dirs', 'pushd', 'popd',
    # Variables
    'export', 'unset', 'set', 'declare', 'typeset', 'local', 'readonly',
    'shift', 'getopts',
    # Control
    'exit', 'return', 'break', 'continue', 'eval', 'exec',
    'source', '.', 'true', 'false', ':',
    # Job control
    'jobs', 'fg', 'bg', 'wait', 'kill', 'disown', 'suspend',
    # History
    'history', 'fc',
    # Aliases
    'alias', 'unalias',
    # Completion
    'complete', 'compgen', 'compopt',
    # Introspection
    'command', 'builtin', 'enable', 'help', 'type', 'hash',
    # Signals / limits
    'trap', 'umask', 'ulimit', 'times',
    # Test
    'test', '[', '[[', ']]',
    # Other
    'shopt', 'caller', 'bind', 'let', 'logout',
}

# Common external commands (for linter "unknown command" checks)
COMMON_COMMANDS = {
    'ls', 'cp', 'mv', 'rm', 'mkdir', 'rmdir', 'touch', 'cat', 'grep',
    'sed', 'awk', 'find', 'xargs', 'sort', 'uniq', 'head', 'tail',
    'wc', 'cut', 'tr', 'diff', 'patch', 'tar', 'gzip', 'gunzip',
    'zip', 'unzip', 'curl', 'wget', 'ssh', 'scp', 'rsync', 'git',
    'make', 'gcc', 'python', 'python3', 'perl', 'ruby', 'node',
    'npm', 'pip', 'apt', 'yum', 'brew', 'systemctl', 'service',
}

# Common command typos (for enhanced validator)
COMMON_TYPOS = {
    # grep typos
    'gerp': 'grep', 'grpe': 'grep', 'rgep': 'grep',

    # Basic commands
    'sl': 'ls', 'l': 'ls', 'll': 'ls -l',
    'mr': 'rm', 'r': 'rm',
    'vm': 'mv', 'v': 'mv',
    'pc': 'cp', 'c': 'cp',
    'dc': 'cd',

    # echo/cat
    'ech': 'echo', 'ehco': 'echo', 'eho': 'echo',
    'cta': 'cat', 'ca': 'cat',

    # Programming languages
    'pyton': 'python', 'pythn': 'python', 'phyton': 'python',
    'pyhton': 'python', 'pytho': 'python',
    'noed': 'node', 'ndoe': 'node',
    'jaav': 'java', 'jva': 'java',

    # Package managers
    'atp': 'apt', 'apt-gte': 'apt-get',
    'ymu': 'yum', 'ym': 'yum',
    'nmp': 'npm', 'npn': 'npm',
    'ppi': 'pip', 'ipp': 'pip',

    # Git
    'gti': 'git', 'gi': 'git', 'got': 'git',

    # Make
    'maek': 'make', 'mkae': 'make',

    # Others
    'ifconfig': 'ip',  # Modern alternative
    'service': 'systemctl',  # Modern alternative
}
