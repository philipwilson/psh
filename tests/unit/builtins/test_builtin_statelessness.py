"""Meta-test: builtin instances are stateless singletons.

Builtin instances are created once at import time by the ``@builtin``
decorator and shared by every Shell in the process (see the statelessness
contract in psh/builtins/base.py). A builtin that stashes state on ``self``
leaks it across shells, subshells, and tests. This battery runs a
representative command through (nearly) every builtin and then asserts that
no instance grew any instance attributes: ``vars(instance) == {}``.
"""

from psh.builtins.registry import registry

# A representative battery: at least one invocation for every builtin that
# can run safely and idempotently inside a captured in-process shell.
# Deliberately excluded: exec (replaces/changes process state), exit
# (terminates), fg/bg (need job-control terminal), read (needs stdin),
# parser-select (switches the active parser).
COMMAND_BATTERY = [
    'echo hello',
    'printf "%s\\n" world',
    'pwd',
    'cd .',
    'pushd / >/dev/null',
    'dirs',
    'popd >/dev/null',
    'true',
    'false',
    ': noop',
    'export PSH_STATELESS_T=1',
    'unset PSH_STATELESS_T',
    'set +x',
    'shift 0',
    'declare -i psh_stateless_n=1',
    'typeset psh_stateless_s=x',
    'readonly psh_stateless_ro=1',
    'local x 2>/dev/null',                    # errors outside function: fine
    'f() { local lv=1; return 3; }; f',
    'for i in 1 2; do break; done',
    'for i in 1 2; do continue; done',
    'getopts ab opt -a',
    'let "psh_stateless_n2 = 1 + 1"',
    'eval "echo evald"',
    'source /dev/null',
    'alias psh_t_alias="echo hi"',
    'alias',
    'unalias psh_t_alias',
    'jobs',
    'wait',
    'disown 2>/dev/null',
    'kill -0 $$ 2>/dev/null',
    'trap -p',  # read-only listing; setting real handlers is xdist-hostile
    'umask',
    'times',
    'ulimit -a >/dev/null',  # query only: setting a limit would hit the runner

    'test -n x',
    '[ -n x ]',
    'type echo',
    'command echo via-command',
    'builtin echo via-builtin',
    'help help >/dev/null',
    'help -d echo >/dev/null',
    'help -s echo >/dev/null',
    'help -m echo >/dev/null',
    'history >/dev/null',
    'version >/dev/null',
    'env >/dev/null',
    'mapfile -t psh_stateless_arr < /dev/null',
    'print stateless 2>/dev/null',
    'shopt -s extglob; shopt -u extglob',
    'hash 2>/dev/null',                       # absent in psh; harmless if added
    'debug off 2>/dev/null',
    'debug-ast off 2>/dev/null',
    'signals >/dev/null 2>&1',
    'parser-config show >/dev/null 2>&1',
    'parser-mode >/dev/null 2>&1',
    'show-ast "echo x" >/dev/null 2>&1',
    'parse-tree "echo x" >/dev/null 2>&1',
    'ast-dot "echo x" >/dev/null 2>&1',
]


def test_builtins_keep_no_instance_state(captured_shell):
    """After a representative battery, every builtin instance has empty vars()."""
    # Sanity: instances start stateless (no __init__-injected attributes).
    for instance in registry.instances():
        assert vars(instance) == {}, (
            f"builtin '{instance.name}' has __init__-time instance state: "
            f"{vars(instance)} — builtins are shared singletons, keep state "
            f"on the shell (see psh/builtins/base.py)"
        )

    for cmd in COMMAND_BATTERY:
        # Exit codes are irrelevant here; the battery includes deliberate
        # error paths. We only care that no builtin grew state.
        captured_shell.run_command(cmd)

    offenders = {
        instance.name: vars(instance)
        for instance in registry.instances()
        if vars(instance)
    }
    assert offenders == {}, (
        f"builtin instances accumulated state on self: {offenders}. "
        f"Builtin instances are process-wide singletons shared by every "
        f"Shell; move this state onto the shell argument "
        f"(see the statelessness contract in psh/builtins/base.py)."
    )


def test_battery_covers_most_builtins():
    """The battery should mention the bulk of registered builtins by name.

    Guard against the battery silently going stale as builtins are added:
    every registered builtin (minus the documented exclusions) must appear
    somewhere in the battery text.
    """
    excluded = {'exec', 'exit', 'fg', 'bg', 'read', 'parser-select'}
    battery_text = ' '.join(COMMAND_BATTERY)
    missing = [
        name for name in registry.names()
        if name not in excluded and name not in battery_text
    ]
    assert missing == [], (
        f"builtins not exercised by the statelessness battery: {missing} — "
        f"add a safe invocation to COMMAND_BATTERY or document an exclusion"
    )
