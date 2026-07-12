"""Integration tests for subshell-style state inheritance (reappraisal #15 E1).

End-to-end (subprocess) probes for what a forked child — `( )`, $( ),
<( ) — inherits through ShellState.clone_for_child(): $0, FUNCNAME, traps
(listable-but-inert, with the OS-disposition consequences only a real
fork exhibits), source context, the getopts cursor, SECONDS and the
directory stack. Every expectation here is bash-5.2-verified
(tmp/e1_truth_table.sh); the everyday idioms are also pinned in
tests/behavioral/golden_cases.yaml.

Signal-delivery cases send signals only inside the spawned psh process
tree (a python3 grandchild kills its own parent), so they are
parallel-safe.
"""

import signal
import subprocess
import sys

PSH = [sys.executable, '-m', 'psh']

# Kills the invoking process's PARENT (the forked psh child) with the named
# signal — the portable way to signal a subshell from inside it.
KILL_PARENT = (sys.executable + ' -c "import os,signal,sys;'
               'os.kill(os.getppid(), getattr(signal, \'SIG\'+sys.argv[1]))"')


def run_psh(cmd, *args, timeout=10):
    return subprocess.run(PSH + ['-c', cmd] + list(args),
                          capture_output=True, text=True, timeout=timeout)


class TestDollarZeroInheritance:
    """$0 must survive into children — the $(dirname "$0") idiom."""

    def test_dirname_dollar_zero_in_script(self, tmp_path):
        script = tmp_path / 'sub' / 't.sh'
        script.parent.mkdir()
        script.write_text('SCRIPT_DIR=$(dirname "$0")\necho "dir=$SCRIPT_DIR"\n')
        result = subprocess.run(PSH + [str(script)], capture_output=True,
                                text=True, timeout=10, cwd=tmp_path)
        assert result.stdout == f"dir={script.parent}\n"

    def test_dollar_zero_in_subshell_and_cmdsub(self):
        result = run_psh('(echo $0); echo $(echo $0)', 'myname')
        assert result.stdout == "myname\nmyname\n"


class TestFuncnameInheritance:
    def test_funcname_visible_in_children(self):
        result = run_psh('f() { (echo "sub=${FUNCNAME[0]}"); '
                         'echo "cs=$(echo ${FUNCNAME[0]})"; }; f')
        assert result.stdout == "sub=f\ncs=f\n"


class TestSourceContextInheritance:
    def test_return_in_subshell_of_sourced_file(self, tmp_path):
        src = tmp_path / 'src.sh'
        src.write_text('(return 7)\necho "after:$?"\n')
        result = run_psh(f'source {src}')
        assert result.stdout == "after:7\n"
        assert result.stderr == ""

    def test_return_in_subshell_of_function(self):
        result = run_psh('f() { (return 5); echo in=$?; }; f')
        assert result.stdout == "in=5\n"
        assert result.stderr == ""

    def test_return_in_cmdsub_of_function(self):
        # return ends the substitution child with its status; `echo after`
        # in the same input never runs (bash).
        result = run_psh('f() { local x; x=$(return 3; echo after); '
                         'echo "rc=$? x=[$x]"; }; f')
        assert result.stdout == "rc=3 x=[]\n"
        assert result.stderr == ""

    def test_return_in_background_subshell_of_function(self):
        result = run_psh('f() { (return 5) & wait $!; echo w=$?; }; f')
        assert result.stdout == "w=5\n"


class TestTrapListingInheritance:
    """POSIX saved=$(trap): children list parent traps but never fire them."""

    def test_cmdsub_lists_parent_traps(self):
        result = run_psh('trap "echo hi" USR1; saved=$(trap); echo "[$saved]"')
        assert result.stdout == "[trap -- 'echo hi' SIGUSR1]\n"

    def test_subshell_lists_parent_traps(self):
        result = run_psh('trap "echo hi" USR1; (trap -p USR1)')
        assert result.stdout == "trap -- 'echo hi' SIGUSR1\n"

    def test_procsub_does_not_list_parent_traps(self):
        # bash: process-substitution children never carry the listing.
        result = run_psh('trap "echo hi" USR1; cat <(trap); echo done')
        assert result.stdout == "done\n"

    def test_first_modification_drops_inherited_but_not_ignored(self):
        result = run_psh('trap "echo A" USR1; trap "" USR2; '
                         '(trap "echo C" TERM; trap)')
        assert result.stdout == ("trap -- 'echo C' SIGTERM\n"
                                 "trap -- '' SIGUSR2\n")


class TestTrapFiringInChildren:
    """OS-level consequences: non-ignored traps reset, ignored stay ignored."""

    def test_parent_trap_does_not_fire_and_child_dies(self):
        # bash: the child takes SIGUSR1's default action (death, 128+n);
        # the parent's action never runs, in parent or child.
        result = run_psh(f"trap 'echo hi' USR1; ( {KILL_PARENT} USR1; "
                         f"echo alive ); echo rc=$?")
        assert result.stdout == f"rc={128 + signal.SIGUSR1}\n"

    def test_child_own_trap_fires(self):
        result = run_psh(f"( trap 'echo own' USR1; {KILL_PARENT} USR1; "
                         f"echo after ); echo rc=$?")
        assert result.stdout == "own\nafter\nrc=0\n"

    def test_ignored_trap_stays_ignored_in_child(self):
        result = run_psh(f"trap '' USR2; ( {KILL_PARENT} USR2; "
                         f"echo alive ); echo rc=$?")
        assert result.stdout == "alive\nrc=0\n"

    def test_ignored_managed_signal_stays_ignored_in_child(self):
        # TERM has a psh-managed handler; the '' disposition must still be
        # re-asserted after the child's blanket signal reset.
        result = run_psh(f"trap '' TERM; ( {KILL_PARENT} TERM; "
                         f"echo alive ); echo rc=$?")
        assert result.stdout == "alive\nrc=0\n"

    def test_parent_exit_trap_not_fired_at_subshell_exit(self):
        result = run_psh('trap "echo pexit" EXIT; (echo sub); echo done')
        assert result.stdout == "sub\ndone\npexit\n"

    def test_child_own_exit_trap_fires_at_subshell_exit(self):
        result = run_psh('(trap "echo cexit" EXIT; echo body); echo after')
        assert result.stdout == "body\ncexit\nafter\n"

    def test_cmdsub_child_own_exit_trap_fires(self):
        result = run_psh('x=$(trap "echo bye" EXIT; echo inner); echo "x=[$x]"')
        assert result.stdout == "x=[inner\nbye]\n"

    def test_errtrace_err_trap_fires_in_subshell(self):
        result = run_psh('set -E; trap "echo E" ERR; (false; echo x)')
        assert result.stdout == "E\nx\n"


class TestOtherAdoptedState:
    def test_seconds_baseline_in_subshell(self):
        result = run_psh('SECONDS=500; (echo $SECONDS)')
        assert result.stdout == "500\n"

    def test_getopts_cluster_continues_in_cmdsub(self):
        result = run_psh('set -- -ab; getopts ab o; echo "first=$o"; '
                         'echo "sub=$(getopts ab o; echo $o)"')
        assert result.stdout == "first=a\nsub=b\n"

    def test_dirs_in_subshell_sees_parent_stack(self):
        result = run_psh('cd /; pushd /tmp >/dev/null; (dirs)')
        # macOS abbreviates nothing here; the stack is "/tmp /".
        assert result.stdout == "/tmp /\n"


class TestInProcessChildShells:
    """The env builtin builds an IN-PROCESS child Shell (no fork): the
    forked-child disposition sync must never run for it — forked-ness is
    passed explicitly from the fork sites, never inferred (a pid check
    also matches an in-process child built inside a forked child)."""

    def test_env_builtin_in_process_child_keeps_parent_traps_working(self):
        # env's child Shell at top level: the disposition sync must not
        # run, and the parent's trap still fires afterwards.
        result = run_psh('trap "echo T" USR1; env true >/dev/null; '
                         f'{KILL_PARENT} USR1; :; echo done')
        assert result.stdout == "T\ndone\n"

    def test_env_inside_subshell_keeps_enclosing_live_traps(self):
        # REGRESSION PIN: env's in-process child built INSIDE a forked
        # subshell. Inferring forked-ness from os.getpid() != shell_pid
        # matched here too and reset the enclosing subshell's live USR1
        # handler to SIG_DFL process-wide — the subshell died with
        # 128+SIGUSR1 instead of running its own trap (bash: own/after/0).
        result = run_psh(f"( trap 'echo own' USR1; env true >/dev/null; "
                         f"{KILL_PARENT} USR1; echo after ); echo rc=$?")
        assert result.stdout == "own\nafter\nrc=0\n"

    def test_env_inside_cmdsub_keeps_enclosing_live_traps(self):
        # Same regression, command-substitution variant (bash: x captures
        # "own after", overall rc 0; the broken branch captured nothing).
        result = run_psh(f"x=$(trap 'echo own' USR1; env true >/dev/null; "
                         f"{KILL_PARENT} USR1; echo after); "
                         'echo "x=[$x]"')
        assert result.returncode == 0
        assert result.stdout == "x=[own\nafter]\n"
