"""Job control builtin commands."""
import os
import signal
from typing import TYPE_CHECKING, List

from ..job_control import JobState
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
        if len(args) == 1:
            # No arguments - wait for all children
            return self._wait_for_all(shell)
        else:
            # Wait for specific processes/jobs
            return self._wait_for_specific(args[1:], shell)

    def _wait_for_all(self, shell: 'Shell') -> int:
        """Wait for all child processes to complete."""
        exit_status = 0

        # Collect exit statuses from jobs that already completed (reaped by
        # SIGCHLD handler before wait was called) and clean them up.
        done_jobs = [job for job in shell.job_manager.jobs.values()
                     if job.state == JobState.DONE]
        for job in done_jobs:
            if job.processes:
                last_proc = job.processes[-1]
                if last_proc.status is not None:
                    exit_status = self._extract_exit_status(last_proc.status)
            shell.job_manager.remove_job(job.job_id)

        # Wait for all still-running jobs
        while shell.job_manager.count_active_jobs() > 0:
            active_jobs = [job for job in shell.job_manager.jobs.values()
                          if job.state == JobState.RUNNING]

            if not active_jobs:
                break

            for job in active_jobs:
                status = shell.job_manager.wait_for_job(job)
                exit_status = status

                if job.state == JobState.DONE:
                    shell.job_manager.remove_job(job.job_id)

        # Also check for any orphaned processes not in jobs
        while True:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
                if pid == 0:
                    break
                exit_status = self._extract_exit_status(status)
            except (ChildProcessError, OSError):
                break

        return exit_status

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

                # Clean up if done
                if job.state == JobState.DONE:
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

                    # Clean up if done
                    if job.state == JobState.DONE:
                        shell.job_manager.remove_job(job.job_id)
                else:
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
        from ..job_control import exit_status_from_wait_status
        return exit_status_from_wait_status(status)
