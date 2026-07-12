"""Shared constants for AST visitor implementations."""

import re

from ..core.assignment_utils import SHELL_NAME

# A ``NAME=value`` assignment word: a valid shell identifier immediately
# followed by ``=``. Single-sourced from the canonical ``SHELL_NAME`` so the
# three analysis visitors agree — previously the linter, metrics and enhanced
# validator each carried their own drifting predicate (one accepted hyphens,
# treating ``a-b=c`` as a definition of variable ``a-b``).
_ASSIGNMENT_WORD_RE = re.compile(rf'^{SHELL_NAME}=')


def is_assignment(arg: str) -> bool:
    """True if *arg* is a ``NAME=value`` variable-assignment word.

    NAME must be a valid shell identifier (letter/underscore then
    letters/digits/underscores). Rejects ``=x`` (no name) and ``a-b=c``
    (a hyphen is not valid in a variable name). Array-element assignments
    (``a[0]=x``) never arrive here as bare arg strings — the parser lifts them
    into ``ArrayElementAssignment`` nodes. Append assignments (``FOO+=x``) are
    intentionally NOT matched (so ``split('=', 1)[0]`` yields a clean name),
    matching the historical linter/enhanced-validator behaviour.
    """
    return bool(_ASSIGNMENT_WORD_RE.match(arg))


def is_world_writable_permission(perm: str) -> bool:
    """True if a chmod permission argument makes a file world-writable.

    Shared by SecurityVisitor and EnhancedValidatorVisitor so the check is
    single-sourced and correct: an octal mode is world-writable iff the
    other-write bit (2) is set in its last digit (757, 776, 737, ... — not
    just 777/666), and the symbolic forms add other/all the write bit.
    """
    if re.match(r'^\d{3,4}$', perm):
        return int(perm[-1]) & 2 != 0
    return 'o+w' in perm or 'a+w' in perm or 'o=w' in perm


# test/[ ] operator operand classification, shared by the analysis visitors so
# the "an operand after this operator need not be quoted / is compared a certain
# way" knowledge lives in one place. The operand-position logic that combines
# these lives in word_analysis.unquoted_test_operands (which also adds the extra
# unary/binary forms that routine covers); there is deliberately no pre-built
# union constant here — the old TEST_OPERATORS union's only consumer was the
# linter walk that unquoted_test_operands replaced (reappraisal #19 T10).
NUMERIC_COMPARISON_OPERATORS = frozenset({'-eq', '-ne', '-lt', '-le', '-gt', '-ge'})
STRING_COMPARISON_OPERATORS = frozenset({'=', '!='})
FILE_TEST_OPERATORS = frozenset({'-f', '-d', '-e', '-s', '-r', '-w', '-x'})

# Dynamic-code-execution commands, mapped to the danger they pose. Used by
# SecurityVisitor (emits HIGH) and EnhancedValidatorVisitor (emits a warning);
# both apply their own severity to this ONE membership+reason table. This is NOT
# the linter's caution table — the linter keeps its own remediation-suggestion
# table (LINTER_CAUTION_COMMANDS below), which deliberately includes ``rm`` and
# omits ``source``/``.`` because its role is "commands to use carefully + how",
# not "commands that execute arbitrary code". Kept side by side here so the
# relationship is explicit and the two no longer live in separate files.
DANGEROUS_COMMANDS = {
    'eval': 'Dynamic code execution - high risk of injection',
    'source': 'Loading external scripts - verify source is trusted',
    '.': 'Loading external scripts - verify source is trusted',
    'exec': 'Process replacement - ensure arguments are validated',
}

# The linter's "use with caution" table: command -> remediation suggestion.
# Distinct in both membership and message from DANGEROUS_COMMANDS above (see the
# note there); the linter emits a WARNING carrying the suggestion.
LINTER_CAUTION_COMMANDS = {
    'rm': "Consider using 'rm -i' for interactive confirmation",
    'eval': "Eval can execute arbitrary code, ensure input is trusted",
    'exec': "Exec replaces the current shell, use with caution",
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

# Variables the shell (or bash) always has defined: an analysis visitor must not
# flag a reference to one of these as "undefined". Single-sourced so the linter's
# undefined-variable suppression and the enhanced validator's
# VariableTracker.special_vars agree (previously the linter suppressed only 11
# names while the tracker knew ~50, so ``echo "$HOSTNAME"`` warned under --lint
# but was clean under --validate). Includes the single-character special
# parameters (``?``, ``$``, ``!``, ``#``, ``@``, ``*``, ``-``, ``_``, ``0``); the
# linter only consults the identifier-shaped subset (it never tracks ``$?`` etc.),
# while the tracker needs the full set for lookups.
PREDEFINED_VARIABLES = frozenset({
    # Special parameters
    '?', '$', '!', '#', '@', '*', '-', '_', '0',
    # Environment / shell-maintained variables
    'HOME', 'PATH', 'PWD', 'OLDPWD', 'SHELL', 'USER',
    'HOSTNAME', 'HOSTTYPE', 'OSTYPE', 'MACHTYPE',
    'RANDOM', 'LINENO', 'SECONDS', 'HISTCMD',
    'BASH_VERSION', 'BASH', 'IFS', 'PS1', 'PS2', 'PS3', 'PS4',
    'PPID', 'UID', 'EUID', 'GROUPS', 'SHELLOPTS',
    'PIPESTATUS', 'FUNCNAME', 'BASH_SOURCE', 'BASH_LINENO',
    'REPLY', 'HISTFILE', 'HISTSIZE', 'HISTFILESIZE',
    'LANG', 'LC_ALL', 'LC_COLLATE', 'LC_CTYPE', 'LC_MESSAGES',
    'TERM', 'COLUMNS', 'LINES',
})

# Shell builtins — commands a script under analysis may legitimately assume
# are builtins. This set is deliberately BASH-scoped, not psh-scoped: the
# analysis visitors (linter "called but not defined", metrics builtin/external
# classification, enhanced validator's typo check) inspect scripts that are
# usually written FOR bash, so bash builtins psh does not implement (caller,
# compgen, enable, hash, ...) must not be flagged as unknown commands.
# It additionally contains every builtin psh's own registry provides
# (including psh-specific debug builtins like parse-tree), so scripts written
# for psh analyze cleanly too. Both directions are pinned by
# tests/unit/visitor/test_shell_builtins_pinned.py: a new registry builtin
# must be added here, and any bash-only entry must appear in that test's
# expected list.
SHELL_BUILTINS = {
    # I/O
    'echo', 'printf', 'read',
    # Navigation
    'cd', 'pwd', 'dirs', 'pushd', 'popd',
    # Variables
    'export', 'unset', 'set', 'declare', 'typeset', 'local', 'readonly',
    'shift', 'getopts', 'env', 'mapfile',
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
    'trap', 'umask', 'ulimit', 'times', 'signals',
    # Test
    'test', '[', '[[', ']]',
    # Other
    'shopt', 'caller', 'bind', 'let', 'logout', 'print', 'version',
    # psh-specific debug/introspection builtins
    'ast-dot', 'debug', 'debug-ast', 'parse-tree', 'parser-config',
    'parser-mode', 'parser-select', 'show-ast',
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
