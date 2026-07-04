"""Job control builtin commands."""
import os
import signal
from typing import TYPE_CHECKING, List

from ..executor.job_control import JobState
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
        return "jobs [-lp] [jobspec ...]"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Execute the jobs builtin."""
        opts, _operands = self.parse_flags(args, shell, flags='lp')
        if opts is None:
            return 2  # bash: invalid option is a usage error

        manager = shell.job_manager
        if opts['p']:
            # Show only PIDs (-p wins over -l, like bash)
            for job_id in sorted(manager.jobs.keys()):
                for proc in manager.jobs[job_id].processes:
                    self.write_line(str(proc.pid), shell)
        elif opts['l']:
            # Long format: add the PID column (bash jobs -l). For pipeline
            # jobs the remaining process PIDs follow on indented lines.
            for job_id in sorted(manager.jobs.keys()):
                job = manager.jobs[job_id]
                pids = [proc.pid for proc in job.processes] or [job.pgid]
                line = job.format_status(job == manager.current_job,
                                         job == manager.previous_job,
                                         pid=pids[0])
                self.write_line(line, shell)
                for pid in pids[1:]:
                    self.write_line(f"     {pid}", shell)
        else:
            for line in manager.list_jobs():
                self.write_line(line, shell)
        return 0


@builtin
class FgBuiltin(Builtin):
    """Bring job to foreground."""

    @property
    def name(self) -> str:
        return "fg"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Execute the fg builtin."""
        # Determine which job to foreground
        if len(args) > 1:
            job_spec = args[1]
            job = shell.job_manager.parse_job_spec(job_spec)
            if job is None:
                self.error(f"{job_spec}: no such job", shell)
                return 1
        else:
            # No argument - use current job
            if not shell.job_manager.jobs:
                self.error("no current job", shell)
                return 1
            job = shell.job_manager.current_job
            if job is None:
                self.error("%+: no such job", shell)
                return 1

        # Print the command being resumed
        self.write_line(job.command, shell)

        # Give it terminal control FIRST, before sending SIGCONT — a resumed
        # job that reads the terminal before the transfer would be stopped
        # again by SIGTTIN.
        shell.job_manager.set_foreground_job(job)
        job.foreground = True
        if not shell.job_manager.transfer_terminal_control(job.pgid, "fg builtin"):
            if not shell.state.supports_job_control:
                self.error("no job control in this shell", shell)
            else:
                self.error("can't set terminal control", shell)
            return 1

        # Continue stopped job
        if job.state == JobState.STOPPED:
            # Mark processes as running again
            for proc in job.processes:
                if proc.stopped:
                    proc.stopped = False
            job.state = JobState.RUNNING

            # Send SIGCONT to the process group
            os.killpg(job.pgid, signal.SIGCONT)

        # Wait for it
        exit_status = shell.job_manager.wait_for_job(job)

        # Reclaim the terminal and clear foreground-job bookkeeping
        shell.job_manager.restore_shell_foreground()

        # Remove job if completed
        if job.state == JobState.DONE:
            shell.job_manager.remove_job(job.job_id)

        return exit_status


@builtin
class BgBuiltin(Builtin):
    """Resume job in background."""

    @property
    def name(self) -> str:
        return "bg"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Execute the bg builtin."""
        # Determine which job to background
        if len(args) > 1:
            job_spec = args[1]
            job = shell.job_manager.parse_job_spec(job_spec)
            if job is None:
                self.error(f"{job_spec}: no such job", shell)
                return 1
        else:
            # No argument - use current job
            if not shell.job_manager.jobs:
                self.error("no current job", shell)
                return 1
            job = shell.job_manager.current_job
            if job is None:
                self.error("%+: no such job", shell)
                return 1

        # Resume job in background
        if job.state == JobState.STOPPED:
            # Mark processes as running again
            for proc in job.processes:
                if proc.stopped:
                    proc.stopped = False
            job.state = JobState.RUNNING
            job.foreground = False

            # Send SIGCONT to resume
            os.killpg(job.pgid, signal.SIGCONT)
            self.write_line(f"[{job.job_id}]+ {job.command} &", shell)
        return 0


@builtin
class WaitBuiltin(Builtin):
    """Wait for processes to complete."""

    @property
    def name(self) -> str:
        return "wait"

    @property
    def synopsis(self) -> str:
        return "wait [pid|job_id ...]"

    @property
    def description(self) -> str:
        return "Wait for process completion and return exit status"

    @property
    def help(self) -> str:
        return """wait: wait [pid|job_id ...]
    Wait for process completion and return exit status.

    With no arguments, waits for all currently active child processes.
    With arguments, waits for specified processes or jobs.

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
        # Parse leading options: -n (return when the NEXT job finishes) and
        # -p VAR (store the finished job's PID in VAR). Options precede operands.
        wait_n = False
        pid_var = None
        i = 1
        while i < len(args):
            a = args[i]
            if a == '-n':
                wait_n = True
                i += 1
            elif a == '-p':
                if i + 1 >= len(args):
                    self.error("-p: option requires an argument", shell)
                    return 2
                pid_var = args[i + 1]
                i += 2
            elif a == '--':
                i += 1
                break
            else:
                break
        operands = args[i:]

        if wait_n:
            return self._wait_for_next(operands, pid_var, shell)
        if not operands:
            # No arguments - wait for all children
            return self._wait_for_all(shell)
        # Wait for specific processes/jobs
        return self._wait_for_specific(operands, shell)

    def _wait_for_next(self, operands: List[str], pid_var, shell: 'Shell') -> int:
        """`wait -n`: return when the NEXT single job completes (bash).

        With no operands, wait for any one of the shell's jobs; with operands,
        wait for the first of those jobs/PIDs. Returns that job's exit status,
        or 127 when there is nothing (left) to wait for. With ``-p VAR`` the
        completed job's PID is stored in VAR.
        """
        import os

        from ..executor.job_control import JobState
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

    def _wait_for_specific(self, specs: List[str], shell: 'Shell') -> int:
        """Wait for specific processes or jobs."""
        exit_status = 0

        for spec in specs:
            if spec.startswith('%'):
                # Job specification
                job = shell.job_manager.parse_job_spec(spec)
                if job is None:
                    self.error(f"{spec}: no such job", shell)
                    exit_status = 127
                    continue

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

                # Check if it's a known job
                job = shell.job_manager.get_job_by_pid(pid)
                if job:
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
                        exit_status = remembered
                        continue

                    # Try to wait for the specific PID
                    try:
                        _, status = os.waitpid(pid, os.WNOHANG)
                        if status != 0:
                            # Process already terminated
                            exit_status = self._extract_exit_status(status)
                        else:
                            # Process still running - wait for it
                            try:
                                _, status = os.waitpid(pid, 0)
                                exit_status = self._extract_exit_status(status)
                            except (ChildProcessError, OSError):
                                self.error(f"pid {pid} is not a child of this shell", shell)
                                exit_status = 127
                    except (ChildProcessError, OSError):
                        self.error(f"pid {pid} is not a child of this shell", shell)
                        exit_status = 127

        return exit_status

    def _extract_exit_status(self, status: int) -> int:
        """Extract exit status from waitpid status."""
        from ..executor.job_control import exit_status_from_wait_status
        return exit_status_from_wait_status(status)
