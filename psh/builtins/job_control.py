"""Job control builtin commands."""
import os
import signal
from typing import TYPE_CHECKING, List, Optional, Tuple

from ..core.job_state import (
    JobSpecOutcome,
    JobState,
    jobspec_error_messages,
)
from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


@builtin
class JobsBuiltin(Builtin):
    """List active jobs."""

    @property
    def name(self) -> str:
        return "jobs"

    @property
    def synopsis(self) -> str:
        return "jobs [-lprs] [jobspec ...] or jobs -x command [args]"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Execute the jobs builtin."""
        # `-x command [args]`: substitute whole-word %jobspecs with their pgid
        # and run the command (bash). -x must appear alone.
        x_words, x_error = self._extract_x_command(args, shell)
        if x_error:
            return 1
        if x_words is not None:
            return self._run_x_command(x_words, shell)

        opts, operands = self.parse_flags(args, shell, flags='lnprs')
        if opts is None:
            return 2  # bash: invalid option is a usage error

        manager = shell.job_manager

        # Refresh job state before listing. Under job control (`set -m` / an
        # interactive shell) an external `kill -STOP`/`-CONT` and a completion
        # are reflected; without monitor, bash notices neither (an
        # externally-stopped job still lists as Running) but DOES reap a
        # finished job silently — so we always reap completions, but only track
        # stops under monitor. Safe in every mode: refresh_job_states waits per
        # job process group, so it can never steal a command/process-substitution
        # child out from under a later `wait` (see its docstring).
        monitor = bool(shell.state.options.get('monitor'))
        manager.refresh_job_states(track_stops=monitor)

        # With operands, list ONLY the named jobs and diagnose any that do not
        # resolve (bash: "no such job" / "ambiguous job spec", rc=1). Without
        # operands, list every job. A bare integer operand is a job number.
        exit_status = 0
        if operands:
            jobs_to_list = []
            for spec in operands:
                result = manager.resolve_job_spec(spec, bare='jobnum')
                if result.outcome is JobSpecOutcome.FOUND and result.job is not None:
                    jobs_to_list.append(result.job)
                else:
                    for msg in jobspec_error_messages(result, spec,
                                                      jobs_style=True):
                        self.error(msg, shell)
                    exit_status = 1
        else:
            jobs_to_list = [manager.jobs[job_id]
                            for job_id in sorted(manager.jobs.keys())]

        # -r/-s restrict to Running/Stopped jobs. When both are given bash lets
        # the LAST-specified flag win (`jobs -rs` -> stopped, `jobs -sr` ->
        # running), so consult the option order rather than the flag booleans.
        state_filter = self._state_filter(args)
        if state_filter is not None:
            jobs_to_list = [job for job in jobs_to_list
                            if job.state == state_filter]

        # A completed job is listed by `jobs` exactly ONCE, then reaped —
        # EXCEPT in `-c` mode. Verified vs bash 5.2 (stdout/stderr separated,
        # all four read paths): script-file and stdin `jobs` list the finished
        # job (`[1]+ Exit 1 false` / `Done`) on stdout; `-c` reaps it eagerly so
        # `jobs` stdout is empty (bash announces it on stderr instead — the
        # deferred -c+monitor boundary notice; see the jobsnx ledger); an
        # interactive shell's prompt notice reaps it before `jobs` too (psh's
        # REPL removes it, so nothing is left to list). So suppress the
        # completed entry only under command_mode (the 'c' in $-); removal below
        # is unconditional either way.
        if shell.state.options.get('command_mode'):
            jobs_to_list = [job for job in jobs_to_list
                            if job.state != JobState.DONE]

        # -n: only jobs whose status changed since the user was last notified of
        # it (bash). `notified` is the shared J_NOTIFIED predicate — cleared on
        # any transition (Job.update_state), set below when a job is displayed.
        if opts['n']:
            jobs_to_list = [job for job in jobs_to_list if not job.notified]

        for job in jobs_to_list:
            self._render_job(job, opts, manager, shell)
            # Displaying a job (with or without -n) marks the user notified of
            # its current status, so a following `jobs -n` omits it until the
            # status changes again (bash: `jobs; jobs -n` -> second is empty).
            job.notified = True

        # bash reaps a completed job when `jobs` runs — silently (it is never
        # part of the listing above; a completion is reported through the async
        # stderr notice, not `jobs` stdout). The job is removed and its per-pid
        # status retained for a later `wait <pid>`
        # (`(exit 7)& p=$!; sleep .3; jobs; wait $p` -> 7). This happens on any
        # `jobs` invocation, in every shell mode.
        for job in list(manager.jobs.values()):
            if job.state == JobState.DONE:
                job.notified = True
                manager.remember_job_statuses(job)
                manager.remove_job(job.job_id)
        return exit_status

    def _extract_x_command(self, args: List[str],
                           shell: 'Shell') -> 'Tuple[Optional[List[str]], bool]':
        """Recognise the `-x` form of `jobs`.

        Returns ``(command_words, error)``. ``command_words`` is the argument
        list following a lone ``-x`` (possibly empty, for a bare ``jobs -x``),
        or ``None`` when no ``-x`` option is present. ``error`` is True — after
        printing bash's diagnostic — when ``-x`` was combined with any other
        option (``jobs -lx``, ``jobs -l -x``): bash allows no other options
        with ``-x``.
        """
        seen_other = False
        i = 1
        while i < len(args):
            arg = args[i]
            if arg == '--' or not arg.startswith('-') or len(arg) == 1:
                break
            if 'x' in arg[1:]:
                # -x found. It must be the only option, uncombined.
                if seen_other or arg[1:].replace('x', '', 1):
                    self.error("no other options allowed with `-x'", shell)
                    return None, True
                return list(args[i + 1:]), False
            seen_other = True
            i += 1
        return None, False

    def _run_x_command(self, words: List[str], shell: 'Shell') -> int:
        """Substitute %jobspecs in ``words`` with their pgid and run the result.

        A bare ``jobs -x`` (no command) is a no-op with rc 0 (bash). The
        substituted argv is re-quoted and run through the shell so the command
        goes through the normal resolution order (functions, builtins,
        externals) and executes in the current shell — `jobs -x cd /tmp`
        changes the shell's cwd, matching bash.
        """
        if not words:
            return 0
        import shlex

        manager = shell.job_manager
        substituted = [self._substitute_jobspec(w, manager) for w in words]
        cmdline = ' '.join(shlex.quote(w) for w in substituted)
        return shell.run_command(cmdline, add_to_history=False)

    @staticmethod
    def _substitute_jobspec(word: str, manager) -> str:
        """Replace a whole-word ``%jobspec`` with the job's pgid (bash `jobs -x`).

        Only a word that is itself a resolvable jobspec is substituted. A plain
        word, a substring like ``pre%1``, an adjacent pair like ``%1%2``, or an
        unresolved ``%99`` is passed through unchanged (bash leaves it literal;
        `jobs -x echo %99` prints ``%99`` with rc 0).
        """
        if not word.startswith('%'):
            return word
        result = manager.resolve_job_spec(word)
        if result.outcome is JobSpecOutcome.FOUND and result.job is not None:
            return str(result.job.pgid)
        return word

    @staticmethod
    def _state_filter(args: List[str]) -> 'Optional[JobState]':
        """The Running/Stopped filter from -r/-s, last-specified wins (bash).

        Scans the leading option arguments (parse_flags already validated them,
        so every option char is one of l/p/r/s) and returns the JobState the
        final r/s selects, or None when neither was given.
        """
        state_filter: Optional[JobState] = None
        for arg in args[1:]:
            if arg == '--' or not arg.startswith('-') or len(arg) == 1:
                break
            for ch in arg[1:]:
                if ch == 'r':
                    state_filter = JobState.RUNNING
                elif ch == 's':
                    state_filter = JobState.STOPPED
        return state_filter

    def _render_job(self, job, opts, manager, shell: 'Shell') -> None:
        """Emit one job in the requested format (-p PIDs / -l long / plain)."""
        if opts['p']:
            # Show only PIDs (-p wins over -l, like bash)
            for proc in job.processes:
                self.write_line(str(proc.pid), shell)
        elif opts['l']:
            # Long format: add the PID column (bash jobs -l). For pipeline
            # jobs the remaining process PIDs follow on indented lines.
            pids = [proc.pid for proc in job.processes] or [job.pgid]
            line = job.format_status(job == manager.current_job,
                                     job == manager.previous_job,
                                     pid=pids[0])
            self.write_line(line, shell)
            for pid in pids[1:]:
                self.write_line(f"     {pid}", shell)
        else:
            self.write_line(
                job.format_status(job == manager.current_job,
                                  job == manager.previous_job),
                shell)


@builtin
class FgBuiltin(Builtin):
    """Bring job to foreground."""

    @property
    def name(self) -> str:
        return "fg"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Execute the fg builtin."""
        jm = shell.job_manager
        # bash checks the job-control flag (psh: `set -m`/monitor) FIRST, before
        # resolving any jobspec — so `fg %99` without job control reports
        # "no job control", never "no such job".
        if not shell.state.options.get('monitor'):
            self.error("no job control", shell)
            return 1

        # Strip a leading `--` (end of options): `fg -- %1` targets %1, `fg --`
        # alone falls back to the current job.
        operands = args[1:]
        if operands and operands[0] == '--':
            operands = operands[1:]

        # Determine which job to foreground. A bare integer operand is a JOB
        # NUMBER (bash: `fg 1` == `fg %1`), unlike wait/kill where it is a PID.
        if not operands:
            # No argument - use current job. bash names the missing jobspec
            # "current" in its diagnostic.
            job = jm.current_job
            if job is None:
                self.error("current: no such job", shell)
                return 1
        else:
            result = jm.resolve_job_spec(operands[0], bare='jobnum')
            if result.outcome is not JobSpecOutcome.FOUND or result.job is None:
                for msg in jobspec_error_messages(result, operands[0]):
                    self.error(msg, shell)
                return 1
            job = result.job

        # Refresh the target job's state first. A job stopped by an external
        # `kill -STOP` is never reaped by a non-interactive shell (no SIGCHLD
        # reaper), so fg would still think it RUNNING, skip the SIGCONT below,
        # waitpid it, reap the pending stop, and return 128+SIGSTOP with the job
        # left stopped. Refreshing lets fg see STOPPED, send SIGCONT, and resume
        # it to completion (bash: rc 0). Safe per-group (see refresh_job_states).
        # fg is reached only under monitor, so tracking the stop is correct.
        jm.refresh_one_job(job, track_stops=True)

        # Print the command being resumed
        self.write_line(job.command, shell)

        # Give it terminal control FIRST, before sending SIGCONT — a resumed
        # job that reads the terminal before the transfer would be stopped
        # again by SIGTTIN. The transfer is best-effort: with monitor on but no
        # controlling terminal (a `set -m` non-interactive shell), bash still
        # foregrounds and WAITS for the job, so a failed transfer must not abort.
        jm.set_foreground_job(job)
        job.foreground = True
        transferred = jm.transfer_terminal_control(job.pgid, "fg builtin")

        try:
            # Continue a stopped job (SIGCONT to its process group).
            if job.state == JobState.STOPPED:
                job.mark_running()
                job.state = JobState.RUNNING
                os.killpg(job.pgid, signal.SIGCONT)

            exit_status = jm.wait_for_job(job)
        finally:
            # ALWAYS clear foreground-job bookkeeping, even if wait_for_job
            # raised. Reclaim the terminal only when we actually transferred it
            # (otherwise a failed wait would strand the terminal with the
            # possibly-dead job's process group). Route through
            # finish_foreground_job so a job re-stopped during fg is promoted to
            # %+ (bash's stopped-job priority), not left where it was.
            jm.finish_foreground_job(transferred, job)

        # Remove job if completed
        if job.state == JobState.DONE:
            jm.remove_job(job.job_id)

        return exit_status


@builtin
class BgBuiltin(Builtin):
    """Resume job in background."""

    @property
    def name(self) -> str:
        return "bg"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Execute the bg builtin.

        bash accepts multiple jobspecs (``bg %1 %2``) and resumes each; psh
        used to look at only ``args[1]``.
        """
        jm = shell.job_manager
        # bash checks the job-control flag (psh: `set -m`/monitor) FIRST.
        if not shell.state.options.get('monitor'):
            self.error("no job control", shell)
            return 1

        # Strip a leading `--` (end of options): `bg -- %1` targets %1, `bg --`
        # alone falls back to the current job.
        specs = args[1:]
        if specs and specs[0] == '--':
            specs = specs[1:]
        if not specs:
            job = jm.current_job
            if job is None:
                self.error("current: no such job", shell)
                return 1
            return self._resume_in_background(job, shell)

        # A bare integer operand is a JOB NUMBER (bash: `bg 1` == `bg %1`).
        exit_status = 0
        for spec in specs:
            result = jm.resolve_job_spec(spec, bare='jobnum')
            if result.outcome is not JobSpecOutcome.FOUND or result.job is None:
                for msg in jobspec_error_messages(result, spec):
                    self.error(msg, shell)
                exit_status = 1
                continue
            self._resume_in_background(result.job, shell)
        return exit_status

    def _resume_in_background(self, job, shell: 'Shell') -> int:
        """Resume one stopped job in the background (SIGCONT to its group).

        The resume line carries the job's real marker (`+` current, `-`
        previous, ` ` otherwise) at print time — bash's, not a hardcoded `+`.
        """
        if job.state == JobState.STOPPED:
            jm = shell.job_manager
            job.mark_running()
            job.state = JobState.RUNNING
            job.foreground = False

            os.killpg(job.pgid, signal.SIGCONT)
            marker = ('+' if job is jm.current_job
                      else '-' if job is jm.previous_job else ' ')
            self.write_line(f"[{job.job_id}]{marker} {job.command} &", shell)
        return 0


@builtin
class WaitBuiltin(Builtin):
    """Wait for processes to complete."""

    @property
    def name(self) -> str:
        return "wait"

    @property
    def synopsis(self) -> str:
        # bash's exact usage synopsis (also printed on option errors).
        return "wait [-fn] [-p var] [id ...]"

    @property
    def description(self) -> str:
        return "Wait for process completion and return exit status"

    @property
    def help(self) -> str:
        return """wait: wait [-fn] [-p var] [id ...]
    Wait for process completion and return exit status.

    With no arguments, waits for all currently active child processes.
    With arguments, waits for specified processes or jobs.

    Options:
      -n          Wait for the NEXT single job/process to finish.
      -p VAR      Store the finished job's PID in the variable VAR.
      -f          Wait for the job to terminate (accepted for bash
                  compatibility; psh already waits for termination).

    Arguments can be:
      pid         Process ID to wait for
      %job_id     Job specification (e.g., %1, %+, %-)

    Returns the exit status of the last process waited for.
    If a specified pid is not a child of this shell, returns 127.

    Examples:
      wait              # Wait for all background jobs
      wait %1           # Wait for job 1
      wait 1234         # Wait for process 1234
      wait %+ %-        # Wait for current and previous jobs"""

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Execute the wait builtin."""
        # Parse leading options via the shared getopt-style walker: -n (return
        # when the NEXT job finishes) and -f (wait for termination) are boolean;
        # -p VAR stores the finished job's PID in VAR. The old hand-rolled loop
        # matched only the exact words -n/-p, so it rejected clusters (`-np V`)
        # and mis-classified `-x`/`-f` as bad pids (rc 127) where bash reports
        # an invalid option (rc 2) — parse_flags matches bash. -f is a no-op:
        # a non-interactive psh already waits for termination.
        opts, operands = self.parse_flags(args, shell, flags='nf', value_flags='p')
        if opts is None:
            return 2  # bash: invalid option / missing value is a usage error
        wait_n = opts['n']
        pid_var = opts['p']

        # bash validates the -p VAR name only AFTER a complete option scan
        # (an invalid option elsewhere wins: `wait -p 1bad -x` reports -x —
        # probe-pinned), then fails rc 1 WITHOUT waiting. Same identifier
        # policy as read/mapfile targets (posix => ASCII-only).
        if pid_var is not None:
            from ..lexer.unicode_support import is_valid_name
            if not is_valid_name(pid_var, shell.state.options.get('posix', False)):
                self.error(f"`{pid_var}': not a valid identifier", shell)
                return 1

        # bash unsets the -p VAR up front (before waiting) and sets it only when
        # a job is actually reported. So a wait that reports nothing — a
        # non-child pid, an invalid pid, %nonexistent, or a bare wait-for-all —
        # leaves VAR UNSET (not merely unchanged, and not empty). Clear it here;
        # the report paths below set it via set_variable only on a real pid.
        if pid_var is not None:
            shell.state.scope_manager.unset_variable(pid_var)

        if wait_n:
            return self._wait_for_next(operands, pid_var, shell)
        if not operands:
            # No arguments - wait for all children. VAR stays unset (cleared
            # above): there is no single reported job.
            return self._wait_for_all(shell)
        # Wait for specific processes/jobs
        return self._wait_for_specific(operands, pid_var, shell)

    def _wait_for_next(self, operands: List[str], pid_var, shell: 'Shell') -> int:
        """`wait -n`: return when the NEXT single job completes (bash).

        With no operands, wait for any one of the shell's jobs; with operands,
        wait for the first of those jobs/PIDs. Returns that job's exit status,
        or 127 when there is nothing (left) to wait for. With ``-p VAR`` the
        completed job's PID is stored in VAR.
        """
        import os

        from ..core.job_state import JobState
        jm = shell.job_manager

        # Restrict to the requested jobs (operands), or all jobs when none.
        target_pids = self._resolve_wait_pids(operands, shell) if operands else None

        def matches(job) -> bool:
            return target_pids is None or any(p.pid in target_pids for p in job.processes)

        def finish(job) -> int:
            if pid_var is not None and job.processes:
                shell.state.set_variable(pid_var, str(job.processes[-1].pid))
            status = 0
            if job.processes and job.processes[-1].status is not None:
                status = self._extract_exit_status(job.processes[-1].status)
            # Retain the reaped job's per-pid status so a LATER explicit
            # `wait <pid>` returns it, as bash does (`( exit 6 )& p=$!;
            # wait -n; wait $p` -> 6, not 127). Like the explicit-wait paths,
            # a subsequent bare `wait` still clears this (clear_remembered_
            # statuses); only `wait -n` was previously dropping it.
            jm.remember_job_statuses(job)
            jm.remove_job(job.job_id)
            return status

        # A job already reaped by the SIGCHLD path counts as the next to report.
        for job in list(jm.jobs.values()):
            if job.state == JobState.DONE and matches(job):
                return finish(job)

        # Nothing left to wait for -> 127 (bash).
        if not any(job.state == JobState.RUNNING and matches(job)
                   for job in jm.jobs.values()):
            return 127

        # Reap children until a matching JOB completes (the first to finish).
        while True:
            try:
                pid, status = os.waitpid(-1, os.WUNTRACED)
            except (ChildProcessError, OSError):
                return 127
            if pid == 0:
                continue
            reaped = jm.get_job_by_pid(pid)
            if reaped is None:
                continue  # orphan not tracked as a job
            reaped.update_process_status(pid, status)
            reaped.update_state()
            if reaped.state == JobState.DONE and matches(reaped):
                return finish(reaped)

    def _resolve_wait_pids(self, operands: List[str], shell: 'Shell') -> set:
        """The set of process PIDs named by wait operands (PIDs and %jobspecs)."""
        pids: set = set()
        for spec in operands:
            if spec.startswith('%'):
                job = shell.job_manager.parse_job_spec(spec)
                if job is not None:
                    pids.update(p.pid for p in job.processes)
            else:
                try:
                    pids.add(int(spec))
                except ValueError:
                    pass
        return pids

    def _wait_for_all(self, shell: 'Shell') -> int:
        """Wait for all child processes to complete.

        POSIX/bash: `wait` with no operands returns 0 once all children have
        terminated — a failing background job does NOT leak into $? (only the
        operand form `wait PID`/`wait %job` reports a waited job's status). We
        still reap and clean up every job for its side effects.
        """
        # Reap jobs that already completed (the SIGCHLD handler may have reaped
        # them before wait was called) and clean them up.
        done_jobs = [job for job in shell.job_manager.jobs.values()
                     if job.state == JobState.DONE]
        for job in done_jobs:
            shell.job_manager.remove_job(job.job_id)

        # Wait for all still-running jobs.
        while shell.job_manager.count_active_jobs() > 0:
            active_jobs = [job for job in shell.job_manager.jobs.values()
                          if job.state == JobState.RUNNING]

            if not active_jobs:
                break

            for job in active_jobs:
                shell.job_manager.wait_for_job(job)
                if job.state == JobState.DONE:
                    shell.job_manager.remove_job(job.job_id)

        # Also reap any orphaned processes not tracked as jobs.
        while True:
            try:
                pid, _status = os.waitpid(-1, os.WNOHANG)
                if pid == 0:
                    break
            except (ChildProcessError, OSError):
                break

        # A bare `wait` resets the retained bg-status table: a job it reaped is
        # NOT retained, and any status retained by a prior explicit `wait <pid>`
        # is forgotten (bash: `wait $p; wait; wait $p` → 5, then 127).
        shell.job_manager.clear_remembered_statuses()

        return 0

    def _wait_for_specific(self, specs: List[str], pid_var,
                           shell: 'Shell') -> int:
        """Wait for specific processes or jobs.

        With ``-p VAR`` (``pid_var``), VAR is set to the pid of the job whose
        exit status is returned — the LAST operand (bash). This applies with or
        without ``-n``; the earlier code assigned VAR only on the ``-n`` path.
        """
        exit_status = 0
        reported_pid = None

        for spec in specs:
            if spec.startswith('%'):
                # Job specification
                job = shell.job_manager.parse_job_spec(spec)
                if job is None:
                    self.error(f"{spec}: no such job", shell)
                    exit_status = 127
                    continue

                if job.processes:
                    reported_pid = job.processes[-1].pid
                if job.state == JobState.DONE:
                    # Already completed - get exit status from last process
                    if job.processes:
                        last_proc = job.processes[-1]
                        if last_proc.status is not None:
                            exit_status = self._extract_exit_status(last_proc.status)
                elif job.state == JobState.STOPPED:
                    # Don't wait for stopped jobs
                    self.error(f"{spec}: job is stopped", shell)
                    exit_status = 1
                else:
                    # Wait for job to complete
                    exit_status = shell.job_manager.wait_for_job(job)

                # Clean up if done, retaining the status for a repeated wait
                # (explicit wait paths retain; a bare `wait` does not).
                if job.state == JobState.DONE:
                    shell.job_manager.remember_job_statuses(job)
                    shell.job_manager.remove_job(job.job_id)

            else:
                # Process ID
                try:
                    pid = int(spec)
                except ValueError:
                    self.error(f"{spec}: not a valid process id", shell)
                    exit_status = 127
                    continue

                # -p VAR is set only once the pid is confirmed to be (or to
                # have been) our child. bash leaves VAR unset for a pid that is
                # not a child, so reported_pid is assigned inside each
                # child-confirmed branch below — never before this check.
                # Check if it's a known job
                job = shell.job_manager.get_job_by_pid(pid)
                if job:
                    reported_pid = pid
                    # Wait for the entire job containing this PID
                    if job.state != JobState.DONE:
                        if job.state == JobState.STOPPED:
                            self.error(f"pid {pid}: job is stopped", shell)
                            exit_status = 1
                        else:
                            exit_status = shell.job_manager.wait_for_job(job)
                    else:
                        # Already done - find exit status
                        for proc in job.processes:
                            if proc.pid == pid and proc.status is not None:
                                exit_status = self._extract_exit_status(proc.status)
                                break

                    # Clean up if done, retaining the status for a repeated
                    # explicit wait (a bare `wait` clears it — see _wait_for_all).
                    if job.state == JobState.DONE:
                        shell.job_manager.remember_job_statuses(job)
                        shell.job_manager.remove_job(job.job_id)
                else:
                    # A job reaped by a PRIOR explicit `wait <pid>` and removed
                    # leaves a remembered exit status keyed by pid: a repeated
                    # explicit `wait <pid>` returns it (bash), rather than "not
                    # a child" / 127. (A job reaped by a bare `wait` is not
                    # retained, and a bare `wait` clears prior retention.)
                    remembered = shell.job_manager.get_remembered_status(pid)
                    if remembered is not None:
                        reported_pid = pid
                        exit_status = remembered
                        continue

                    # Try to wait for the specific PID
                    try:
                        _, status = os.waitpid(pid, os.WNOHANG)
                        if status != 0:
                            # Process already terminated
                            reported_pid = pid
                            exit_status = self._extract_exit_status(status)
                        else:
                            # Process still running - wait for it
                            try:
                                _, status = os.waitpid(pid, 0)
                                reported_pid = pid
                                exit_status = self._extract_exit_status(status)
                            except (ChildProcessError, OSError):
                                self.error(f"pid {pid} is not a child of this shell", shell)
                                exit_status = 127
                    except (ChildProcessError, OSError):
                        self.error(f"pid {pid} is not a child of this shell", shell)
                        exit_status = 127

        # -p VAR: store the pid of the job whose status is returned (the last
        # resolved operand). bash sets this with or without -n.
        if pid_var is not None and reported_pid is not None:
            shell.state.set_variable(pid_var, str(reported_pid))

        return exit_status

    def _extract_exit_status(self, status: int) -> int:
        """Extract exit status from waitpid status."""
        from ..core.job_state import exit_status_from_wait_status
        return exit_status_from_wait_status(status)
