"""Trap/signal discipline for in-process backgrounded compound bodies.

reappraisal #18 Tier-1 T1-4. A backgrounded subshell ``( ... ) &``, brace group
``{ ...; } &`` or function call ``f &`` runs in a forked subshell environment
and must gain the same trap/signal discipline the main shell already has. Four
symptoms were fixed by a single shared runner
(``child_policy.run_background_shell_child``):

  1. a body-set trap for a MANAGED signal (TERM/INT/HUP/QUIT) never installed an
     OS handler, so ``kill -TERM $!`` killed the child instead of firing it;
  2. the pending-trap queue was not pumped for the body's own traps;
  3. the EXIT trap was dropped on normal completion (brace group / function);
  4. the EXIT trap was dropped on death from an untrapped fatal signal.

Plus three POSIX asynchronous-list rules (job control off): a backgrounded
reader gets stdin from /dev/null; an untrapped bg job ignores SIGINT/SIGQUIT;
and ``wait <pid>`` on an already-reaped known job returns its remembered status.

Pinned to bash 5.2. These run psh in subprocesses and synchronize via marker
files (no bare-sleep races); the job_control path is auto-marked serial by
conftest.
"""

import os
import subprocess
import sys

import pytest

# psh is an editable install pointing at the MAIN tree; a subprocess
# `python -m psh` launched with a foreign cwd would import MAIN, not this
# worktree. Prepend the worktree root so the subprocess always exercises the
# code under test (campaign env gotcha).
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _env_with_worktree():
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = _REPO_ROOT + (os.pathsep + existing if existing else "")
    return env

# A busy-wait-with-cap helper injected into every script: poll for a marker
# file so nothing spins forever and no bare sleep races a fork.
PRELUDE = r'''
waitfor() {  # waitfor FILE  -- poll up to ~6s for FILE to exist
  i=0
  while [ ! -e "$1" ] && [ "$i" -lt 600 ]; do
    i=$((i+1)); sleep 0.01
  done
}
'''


def _run(shell_argv, script, tmp_path, stdin=None):
    d = tmp_path / "sync"
    d.mkdir(exist_ok=True)
    full = f'D="{d}"\n' + PRELUDE + script
    path = tmp_path / "case.sh"
    path.write_text(full)
    return subprocess.run(shell_argv + [str(path)], capture_output=True,
                          text=True, timeout=30, input=stdin,
                          env=_env_with_worktree())


def run_psh(script, tmp_path, stdin=None):
    return _run([sys.executable, '-m', 'psh'], script, tmp_path, stdin)


def run_bash(script, tmp_path, stdin=None):
    bash = '/opt/homebrew/bin/bash' if os.path.exists('/opt/homebrew/bin/bash') else 'bash'
    return _run([bash], script, tmp_path, stdin)


# Body templates: install a SIG trap that records a marker to break a capped
# busy-wait, signalled from the parent once the child is ready.
def _managed_trap_script(open_close, sig):
    open_, close_ = open_close
    return f'''
{open_}
  trap 'echo caught-{sig}; touch "$D/caught"' {sig}
  touch "$D/ready"
  n=0
  while [ ! -e "$D/caught" ] && [ "$n" -lt 600 ]; do n=$((n+1)); sleep 0.01; done
{close_} &
pid=$!
waitfor "$D/ready"
kill -{sig} "$pid"
wait "$pid"
echo "exit=$?"
'''


BODIES = {
    "subshell": ("(", ")"),
    "brace": ("{", "}"),
}


class TestManagedSignalBodyTrap:
    """Symptom 1: a body-set trap for a managed signal fires (not killed)."""

    @pytest.mark.parametrize("body", ["subshell", "brace"])
    @pytest.mark.parametrize("sig", ["TERM", "INT", "HUP", "QUIT"])
    def test_body_trap_fires(self, body, sig, tmp_path):
        script = _managed_trap_script(BODIES[body], sig)
        r = run_psh(script, tmp_path)
        assert r.stdout == f"caught-{sig}\nexit=0\n", r.stderr

    @pytest.mark.parametrize("sig", ["TERM", "INT", "USR1"])
    def test_function_body_trap_fires(self, sig, tmp_path):
        script = f'''
bg() {{
  trap 'echo caught-{sig}; touch "$D/caught"' {sig}
  touch "$D/ready"
  n=0
  while [ ! -e "$D/caught" ] && [ "$n" -lt 600 ]; do n=$((n+1)); sleep 0.01; done
}}
bg &
pid=$!
waitfor "$D/ready"
kill -{sig} "$pid"
wait "$pid"
echo "exit=$?"
'''
        r = run_psh(script, tmp_path)
        assert r.stdout == f"caught-{sig}\nexit=0\n", r.stderr


class TestBackgroundExitTrapNormal:
    """Symptom 3: EXIT trap fires when a bg compound completes normally."""

    def test_subshell(self, tmp_path):
        r = run_psh("( trap 'echo bye' EXIT; echo body ) &\nwait $!\necho done", tmp_path)
        assert r.stdout == "body\nbye\ndone\n", r.stderr

    def test_brace(self, tmp_path):
        r = run_psh("{ trap 'echo bye' EXIT; echo body; } &\nwait $!\necho done", tmp_path)
        assert r.stdout == "body\nbye\ndone\n", r.stderr

    def test_function(self, tmp_path):
        r = run_psh("f() { trap 'echo bye' EXIT; echo body; }\nf &\nwait $!\necho done", tmp_path)
        assert r.stdout == "body\nbye\ndone\n", r.stderr


class TestBackgroundExitTrapOnFatalSignal:
    """Symptom 4: EXIT trap fires (then 128+N death) on untrapped fatal signal."""

    @pytest.mark.parametrize("body", ["subshell", "brace"])
    @pytest.mark.parametrize("sig,rc", [("TERM", 143), ("HUP", 129)])
    def test_exit_trap_on_signal(self, body, sig, rc, tmp_path):
        open_, close_ = BODIES[body]
        script = f'''
{open_}
  trap 'echo bye-on-{sig}' EXIT
  touch "$D/ready"
  n=0
  while [ "$n" -lt 600 ]; do n=$((n+1)); sleep 0.01; done
{close_} &
pid=$!
waitfor "$D/ready"
kill -{sig} "$pid"
wait "$pid"
echo "exit=$?"
'''
        r = run_psh(script, tmp_path)
        assert r.stdout == f"bye-on-{sig}\nexit={rc}\n", r.stderr


class TestInheritedTrapNotFired:
    """Must-not-regress: a PARENT trap is reset (not inherited) in the bg child.

    The child ignores the PARENT trap; an untrapped USR1 takes its default
    action and kills the child (128+30 = 158).
    """

    @pytest.mark.parametrize("body", ["subshell", "brace"])
    def test_parent_trap_reset(self, body, tmp_path):
        open_, close_ = BODIES[body]
        script = f'''
trap 'echo PARENT-USR1' USR1
{open_}
  touch "$D/ready"
  n=0
  while [ ! -e "$D/caught" ] && [ "$n" -lt 300 ]; do n=$((n+1)); sleep 0.01; done
  echo child-done
{close_} &
pid=$!
waitfor "$D/ready"
kill -USR1 "$pid" 2>/dev/null
sleep 0.15
touch "$D/caught"
wait "$pid"
echo "exit=$?"
'''
        r = run_psh(script, tmp_path)
        assert "PARENT-USR1" not in r.stdout, r.stdout
        assert r.stdout == "exit=158\n", r.stderr


class TestAsyncStdinFromDevNull:
    """POSIX MED: a backgrounded reader gets stdin from /dev/null, not the
    script's stdin, so it never steals the foreground read's input."""

    def test_bg_read_does_not_steal_stdin(self, tmp_path):
        script = '''
{ read bgline; echo "bg=[$bgline]" > "$D/bgout"; } &
pid=$!
wait "$pid"
read fgline
echo "fg=[$fgline]"
cat "$D/bgout"
'''
        r = run_psh(script, tmp_path, stdin="hello-fg\n")
        assert r.stdout == "fg=[hello-fg]\nbg=[]\n", r.stderr


class TestAsyncIntQuitIgnored:
    """POSIX MED: an untrapped bg job (job control off) ignores INT and QUIT."""

    @pytest.mark.parametrize("sig", ["INT", "QUIT"])
    def test_bg_external_ignores(self, sig, tmp_path):
        # sleep runs to completion (rc 0) because the async list ignores the
        # signal; a settle avoids racing the fork before sleep is blocked.
        script = f'''
sleep 1 &
pid=$!
sleep 0.25
kill -{sig} "$pid"
wait "$pid"
echo "rc=$?"
'''
        r = run_psh(script, tmp_path)
        assert r.stdout == "rc=0\n", r.stderr

    @pytest.mark.parametrize("sig", ["INT", "QUIT"])
    def test_bg_subshell_ignores(self, sig, tmp_path):
        script = f'''
( touch "$D/ready"; n=0; while [ "$n" -lt 100 ]; do n=$((n+1)); sleep 0.01; done; echo sub-done ) &
pid=$!
waitfor "$D/ready"
sleep 0.1
kill -{sig} "$pid"
wait "$pid"
echo "rc=$?"
'''
        r = run_psh(script, tmp_path)
        assert r.stdout == "sub-done\nrc=0\n", r.stderr

    def test_bg_external_term_still_dies(self, tmp_path):
        # TERM is NOT ignored: the job dies with 143. Guards against over-broad
        # ignoring.
        script = '''
sleep 5 &
pid=$!
sleep 0.25
kill -TERM "$pid"
wait "$pid"
echo "rc=$?"
'''
        r = run_psh(script, tmp_path)
        assert r.stdout == "rc=143\n", r.stderr


class TestWaitRemembersStatus:
    """POSIX MED: wait <pid> retention matches bash exactly. An EXPLICIT
    `wait <pid>` retains the status for a repeated explicit wait; a job reaped
    by a BARE `wait` is not retained, and a bare `wait` clears any status
    retained by a prior explicit wait. Unknown pid → 127. Whole matrix pinned
    to bash 5.2 (tmp/probes-r18t1-bg-traps wait-matrix)."""

    def test_repeated_explicit_returns_remembered(self, tmp_path):
        # (explicit, explicit) → 7, 7 : the fix this campaign added.
        r = run_psh("( exit 7 ) & p=$!; wait $p; echo first=$?; wait $p; echo second=$?", tmp_path)
        assert r.stdout == "first=7\nsecond=7\n", r.stderr

    def test_explicit_x3_still_remembered(self, tmp_path):
        r = run_psh("( exit 5 ) & p=$!; wait $p; echo $?; wait $p; echo $?; wait $p; echo $?", tmp_path)
        assert r.stdout == "5\n5\n5\n", r.stderr

    def test_bare_then_explicit_is_127(self, tmp_path):
        # (bare, explicit) → 127 : a job reaped by a bare wait is NOT retained.
        # This is the over-retention regression the verifier caught.
        r = run_psh("( exit 5 ) & p=$!; wait; wait $p; echo rc=$?", tmp_path)
        assert r.stdout == "rc=127\n", r.stderr

    def test_bare_wait_clears_prior_explicit_retention(self, tmp_path):
        # (explicit, bare, explicit) → 5, 0, 127 : a bare wait forgets a status
        # retained by a prior explicit wait.
        r = run_psh("( exit 5 ) & p=$!; wait $p; echo $?; wait; echo $?; wait $p; echo $?", tmp_path)
        assert r.stdout == "5\n0\n127\n", r.stderr

    def test_multi_job_bare_first_both_127(self, tmp_path):
        r = run_psh("(exit 3)& a=$!; (exit 4)& b=$!; wait; wait $a; echo $?; wait $b; echo $?", tmp_path)
        assert r.stdout == "127\n127\n", r.stderr

    def test_multi_job_explicit_each_retained(self, tmp_path):
        r = run_psh("(exit 3)& a=$!; (exit 4)& b=$!; wait $a; echo $?; wait $b; echo $?", tmp_path)
        assert r.stdout == "3\n4\n", r.stderr

    def test_unknown_pid_is_127(self, tmp_path):
        r = run_psh("wait 999999\necho rc=$?", tmp_path)
        assert r.stdout == "rc=127\n"
