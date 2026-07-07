"""Job control functionality for psh."""

import errno
import os
import signal
import sys
import termios
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Literal, Optional, Sequence, Tuple, Union, overload


def abnormal_termination_message(status: int) -> Optional[str]:
    """bash's diagnostic for a foreground job killed by a signal.

    Returns the signal's description — ``signal.strsignal()``, the same libc
    text bash reports, e.g. ``Terminated: 15`` on macOS or ``Terminated`` on
    Linux — with ``(core dumped)`` appended when a core was written. Returns
    None for a normal exit, a stop, or the two signals bash deliberately does
    NOT announce (SIGINT and SIGPIPE), so the caller stays silent there.
    """
    if not os.WIFSIGNALED(status):
        return None
    sig = os.WTERMSIG(status)
    if sig in (signal.SIGINT, signal.SIGPIPE):
        return None
    message = signal.strsignal(sig) or f"Signal {sig}"
    if os.WCOREDUMP(status):
        message += " (core dumped)"
    return message


def background_completion_label(status: Optional[int]) -> str:
    """bash's state label for a COMPLETED background job's async notice.

    This is the BACKGROUND analogue of :func:`abnormal_termination_message`
    (the foreground diagnostic), and it differs in two bash-pinned ways
    (probes: tmp/probes-r18t2-interactive/probe_mi3_*):

    * A signal death shows the signal description (``Terminated: 15``,
      ``Killed: 9``, ``Interrupt: 2``, ``Broken pipe: 13`` — libc
      ``strsignal`` text, ``(core dumped)`` appended when a core was
      written). Unlike the foreground case — which stays silent for SIGINT
      and SIGPIPE — the background notice announces SIGINT.
    * A normal exit shows ``Done`` (code 0) or ``Exit N`` (nonzero) — the
      Done/Exit-N split the foreground diagnostic never needs.

    This function names the label for EVERY status, SIGPIPE included
    (``Broken pipe: 13``). The one place bash withholds a bg SIGPIPE notice —
    an INTERACTIVE shell — is handled by the caller
    (:meth:`JobManager._print_completion_notice`), not here, since it is a
    display policy that depends on the shell mode, not on the status.

    ``status`` is the raw waitpid status of the process that set ``$?`` (the
    last in the pipeline); None (never reaped) is treated as a clean Done.
    """
    if status is None:
        return "Done"
    if os.WIFSIGNALED(status):
        sig = os.WTERMSIG(status)
        label = signal.strsignal(sig) or f"Signal {sig}"
        if os.WCOREDUMP(status):
            label += " (core dumped)"
        return label
    if os.WIFEXITED(status):
        code = os.WEXITSTATUS(status)
        return "Done" if code == 0 else f"Exit {code}"
    return "Done"


def exit_status_from_wait_status(status: int) -> int:
    """Convert a raw waitpid() status into a shell exit status.

    Normal exit yields the exit code; death by signal N yields 128+N;
    a stop by signal N also yields 128+N (matching bash's $? for a
    just-stopped foreground job).
    """
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    elif os.WIFSIGNALED(status):
        return 128 + os.WTERMSIG(status)
    elif os.WIFSTOPPED(status):
        return 128 + os.WSTOPSIG(status)
    return 0


class JobState(Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    DONE = "done"


class JobSpecOutcome(Enum):
    """Category of a jobspec resolution (bash's get_job_spec outcomes).

    A bare ``Optional[Job]`` cannot tell "no such job" apart from "ambiguous
    job spec" or "the current/previous job does not exist" — bash prints a
    different diagnostic for each. :meth:`JobManager.resolve_job_spec` returns
    one of these so the job builtins can render the exact bash wording.
    """
    FOUND = "found"
    NO_SUCH_JOB = "no_such_job"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class JobSpecResult:
    """Typed outcome of :meth:`JobManager.resolve_job_spec`.

    ``job`` is set only for :attr:`JobSpecOutcome.FOUND`. ``pattern`` carries
    the search text (the spec without its leading ``%`` and any ``?``) that
    bash names in the ``<pattern>: ambiguous job spec`` diagnostic.
    """
    outcome: JobSpecOutcome
    job: "Optional[Job]" = None
    pattern: str = ""


def jobspec_error_messages(result: JobSpecResult, spec: str,
                           *, jobs_style: bool = False) -> List[str]:
    """The diagnostic line(s) bash prints for a failed jobspec resolution.

    An ambiguous spec yields ``<pattern>: ambiguous job spec``; bash's
    ``jobs`` builtin then additionally prints ``<spec>: no such job`` (two
    lines), while ``kill``/``fg``/``bg``/``disown`` print only the ambiguous
    line — select that with ``jobs_style``. Every other failure yields
    ``<spec>: no such job``. Each string is prefixed with the builtin name by
    the caller's ``self.error``.
    """
    if result.outcome is JobSpecOutcome.AMBIGUOUS:
        messages = [f"{result.pattern}: ambiguous job spec"]
        if jobs_style:
            messages.append(f"{spec}: no such job")
        return messages
    return [f"{spec}: no such job"]


class Process:
    """Represents a single process in a job."""
    def __init__(self, pid: int, command: str):
        self.pid = pid
        self.command = command
        self.status: Optional[int] = None  # Will be set by waitpid
        self.stopped = False
        self.completed = False

    def update_status(self, status: int):
        """Update process status from waitpid result."""
        self.status = status

        if os.WIFSTOPPED(status):
            self.stopped = True
            self.completed = False
        elif os.WIFEXITED(status) or os.WIFSIGNALED(status):
            self.stopped = False
            self.completed = True
        else:
            # Process is running
            self.stopped = False
            self.completed = False


class Job:
    """Represents a job (pipeline or single command)."""
    def __init__(self, job_id: int, pgid: int, command: str):
        self.job_id = job_id
        self.pgid = pgid
        self.command = command
        self.processes: List[Process] = []
        self.state = JobState.RUNNING
        self.foreground = True
        self.notified = False
        self.tmodes: Optional[list] = None  # Terminal modes when suspended

    def add_process(self, pid: int, command: str):
        """Add a process to this job."""
        self.processes.append(Process(pid, command))

    def update_process_status(self, pid: int, status: int):
        """Update status of a specific process."""
        for proc in self.processes:
            if proc.pid == pid:
                proc.update_status(status)
                break

    def all_processes_stopped(self) -> bool:
        """True when the job counts as STOPPED (F10).

        A job is stopped when every process that has NOT completed is stopped —
        NOT when *all* processes are stopped. A pipeline mixing a completed
        member (``stopped=False``) with a stopped member is stopped: none of
        its still-live processes is running. Requiring all-stopped left such a
        pipeline classified as running.

        Only meaningful together with the all-completed check in
        :meth:`update_state` (which handles the empty non-completed set), so
        here an all-completed job returns True harmlessly.
        """
        return all(p.stopped for p in self.processes if not p.completed)

    def all_processes_completed(self) -> bool:
        """Check if all processes in job are completed."""
        return all(p.completed for p in self.processes)

    def any_process_running(self) -> bool:
        """Check if any process is still running."""
        return any(not p.stopped and not p.completed for p in self.processes)

    def update_state(self):
        """Update job state based on process states.

        all-completed -> DONE; else every non-completed process stopped ->
        STOPPED; else RUNNING (F10). The DONE check comes first so the STOPPED
        predicate is only consulted when at least one process is still live.
        """
        if self.all_processes_completed():
            self.state = JobState.DONE
        elif self.all_processes_stopped():
            self.state = JobState.STOPPED
        else:
            self.state = JobState.RUNNING

    def format_status(self, is_current: bool, is_previous: bool,
                      pid: Optional[int] = None) -> str:
        """Format job status for display.

        With ``pid``, include a PID column after the job marker, matching
        bash's ``jobs -l`` format: ``[N]+ 12345 Running    command &``.
        """
        marker = '+' if is_current else '-' if is_previous else ' '
        state_str = {
            JobState.RUNNING: "Running",
            JobState.STOPPED: "Stopped",
            JobState.DONE: "Done"
        }[self.state]

        # Match bash format: [N]+  State                 command &
        suffix = " &" if self.state == JobState.RUNNING and not self.foreground else ""
        if pid is not None:
            return f"[{self.job_id}]{marker} {pid} {state_str:<24}{self.command}{suffix}"
        return f"[{self.job_id}]{marker}  {state_str:<24}{self.command}{suffix}"


class JobManager:
    """Manages all jobs in the shell."""

    # How many completed-job statuses to remember for a later `wait <pid>`.
    # bash bounds this by CHILD_MAX; a fixed cap keeps the table from growing
    # without bound in a long-running shell while covering realistic reuse.
    _MAX_REMEMBERED_STATUSES = 4096

    def __init__(self):
        self.jobs: Dict[int, Job] = {}
        self.next_job_id = 1
        self.current_job: Optional[Job] = None
        self.previous_job: Optional[Job] = None
        # pid -> remembered exit status of a job reaped by an EXPLICIT
        # `wait <pid>` and already removed, so a repeated explicit
        # `wait <pid>` returns the same status bash retains (rather than
        # "not a child" / 127). A bare `wait` clears this table (see
        # clear_remembered_statuses). Insertion-ordered so the oldest
        # entries are evicted first when the cap is reached.
        self.remembered_statuses: "Dict[int, int]" = {}
        self.shell_pgid = os.getpgrp()
        self.shell_tmodes = None
        self.shell_state = None  # Will be set by shell
        # True after confirm_exit_with_stopped_jobs() blocked an exit;
        # cleared by the REPL when another command runs in between
        # (bash's last_shell_builtin two-strikes semantics).
        self._exit_warned = False
        # bash's this_shell_builtin/last_shell_builtin shift register:
        # the builtin name run by the current and previous top-level
        # simple command (None for functions/externals). Shifted by
        # CommandExecutor before each dispatch; the `jobs` builtin in
        # the LAST slot exempts an exit from the stopped-jobs guard.
        self._this_command_builtin: Optional[str] = None
        self._last_command_builtin: Optional[str] = None

        # Save shell's terminal modes
        try:
            self.shell_tmodes = termios.tcgetattr(0)
        except (OSError, termios.error):
            pass

    def set_shell_state(self, state):
        """Set reference to shell state for option checking."""
        self.shell_state = state

    def create_job(self, pgid: int, command: str) -> Job:
        """Create a new job.

        When the job table is empty the counter resets to 1, matching bash
        behavior so that the first user-visible job is always [1].
        """
        if not self.jobs:
            self.next_job_id = 1
        job = Job(self.next_job_id, pgid, command)
        self.jobs[self.next_job_id] = job
        self.next_job_id += 1
        return job

    def remove_job(self, job_id: int):
        """Remove a job from tracking."""
        if job_id in self.jobs:
            job = self.jobs[job_id]

            # Update current/previous references
            if job == self.current_job:
                self.current_job = self.previous_job
                self.previous_job = None
            elif job == self.previous_job:
                self.previous_job = None

            del self.jobs[job_id]

    def remember_job_statuses(self, job: 'Job') -> None:
        """Retain a completed job's per-pid exit status for a later `wait`.

        bash retains a background job's status for a REPEATED explicit
        ``wait <pid>`` — but only for a job reaped by an explicit wait, and
        only until the next bare ``wait`` (see clear_remembered_statuses).
        Called from the explicit-pid / %jobspec wait paths just before the
        job is removed; a bare ``wait`` deliberately does NOT call it, so a
        job it reaps is not retained (bash: `wait; wait $p` → 127).
        """
        if job.state != JobState.DONE:
            return
        for proc in job.processes:
            if proc.status is not None:
                self._remember_status(
                    proc.pid, exit_status_from_wait_status(proc.status))

    def _remember_status(self, pid: int, exit_status: int) -> None:
        """Record a reaped pid's exit status for a later `wait <pid>`."""
        # Refresh position (most-recent last) and evict the oldest if capped.
        self.remembered_statuses.pop(pid, None)
        self.remembered_statuses[pid] = exit_status
        while len(self.remembered_statuses) > self._MAX_REMEMBERED_STATUSES:
            oldest = next(iter(self.remembered_statuses))
            del self.remembered_statuses[oldest]

    def clear_remembered_statuses(self) -> None:
        """Discard all retained bg statuses (a bare ``wait`` resets them).

        bash: once a bare ``wait`` (wait-for-all) runs, a subsequent explicit
        ``wait <pid>`` for a previously-retained job returns 127, not the old
        status (`( exit 5 )& p=$!; wait $p; wait; wait $p` → 5, then 127).
        """
        self.remembered_statuses.clear()

    def get_remembered_status(self, pid: int) -> Optional[int]:
        """Exit status of a reaped, already-removed job's pid, or None."""
        return self.remembered_statuses.get(pid)

    def get_job(self, job_id: int) -> Optional[Job]:
        """Get job by ID."""
        return self.jobs.get(job_id)

    def get_job_by_pid(self, pid: int) -> Optional[Job]:
        """Find job containing the given PID."""
        for job in self.jobs.values():
            for proc in job.processes:
                if proc.pid == pid:
                    return job
        return None

    def get_job_by_pgid(self, pgid: int) -> Optional[Job]:
        """Find job by process group ID."""
        for job in self.jobs.values():
            if job.pgid == pgid:
                return job
        return None

    def set_foreground_job(self, job: Optional[Job]):
        """Set the current foreground job."""
        # Save current job's terminal modes if it exists
        if self.current_job and self.current_job != job:
            try:
                self.current_job.tmodes = termios.tcgetattr(0)
            except (OSError, termios.error):
                pass
            self.previous_job = self.current_job

        self.current_job = job

        # Restore job's terminal modes if it has them. TCSANOW — the
        # drain variants block on a pty whose master isn't being read.
        if job and job.tmodes:
            try:
                termios.tcsetattr(0, termios.TCSANOW, job.tmodes)
            except (OSError, termios.error):
                pass
        elif job is None and self.shell_tmodes:
            # Restore shell's terminal modes
            try:
                termios.tcsetattr(0, termios.TCSANOW, self.shell_tmodes)
            except (OSError, termios.error):
                pass

    def count_active_jobs(self) -> int:
        """Count jobs that are running or stopped."""
        return sum(1 for job in self.jobs.values()
                  if job.state != JobState.DONE)

    def has_stopped_jobs(self) -> bool:
        """True when any job is currently stopped (Ctrl-Z / SIGTSTP)."""
        return any(job.state == JobState.STOPPED for job in self.jobs.values())

    # ------------------------------------------------------------------
    # The stopped-jobs exit guard (bash exit.def)
    #
    # ONE chokepoint answers "should this interactive exit really
    # exit?" for BOTH the exit builtin (builtins/core.py) and the
    # REPL's Ctrl-D EOF path (interactive/repl_loop.py) — bash treats
    # EOF as if the user typed `exit`, so the two are interchangeable
    # for the two-strikes rule (PTY truth table in
    # tmp/probes-r17t2-interactive/probe_stopped_jobs2.py).
    # ------------------------------------------------------------------

    @property
    def exit_warning_pending(self) -> bool:
        """True after a blocked exit, until a command re-arms the guard."""
        return self._exit_warned

    def clear_exit_warning(self) -> None:
        """Re-arm the stopped-jobs exit guard.

        The REPL calls this after any non-blank command runs following a
        warning — bash re-arms whenever ``last_shell_builtin`` stops
        being ``exit`` (blank lines do not re-arm; ``jobs`` re-arms the
        WARNING but simultaneously exempts the next attempt outright —
        see :meth:`confirm_exit_with_stopped_jobs`)."""
        self._exit_warned = False

    def note_simple_command(self, builtin_name: Optional[str]) -> None:
        """Shift bash's last/this_shell_builtin register.

        Called by the CommandExecutor before dispatching every top-level
        simple command that has a command word — with the builtin's name,
        or None for functions and external commands. Pure assignments
        and blank lines never get here (bash: no shift), and commands in
        forked children (pipelines, subshells, substitutions) only shift
        the child's copy. The REPL's Ctrl-D path shifts an ``exit`` in,
        mirroring bash's synthesized exit on EOF."""
        self._last_command_builtin = self._this_command_builtin
        self._this_command_builtin = builtin_name

    def confirm_exit_with_stopped_jobs(self) -> bool:
        """Return True when an interactive exit/EOF may proceed.

        bash exit.def semantics (PTY truth tables in
        tmp/probes-r17t2-interactive/): the FIRST attempt with stopped
        jobs prints "There are stopped jobs." to stderr and is blocked
        (the exit builtin returns 1); a second consecutive attempt —
        exit or Ctrl-D, in any combination — proceeds. Additionally,
        ``jobs`` as the IMMEDIATELY preceding command exempts the
        attempt entirely (no warning even without a first strike: the
        user just looked at the job table — bash's ``last_shell_builtin
        == jobs_builtin`` case); any other command word (builtin,
        function, or external — but not blank lines or pure
        assignments) clears that exemption. Running (non-stopped)
        background jobs never warn (bash's checkjobs shopt is off by
        default). Non-interactive shells, forked children, and ``exit``
        inside a SOURCED file (bash skips the check while sourcing)
        pass straight through."""
        state = self.shell_state
        if state is None or not state.options.get('interactive'):
            return True
        if getattr(state, 'in_forked_child', False):
            return True
        if getattr(state, 'source_depth', 0) > 0:
            return True
        if self._exit_warned or self._last_command_builtin == 'jobs':
            return True
        if not self.has_stopped_jobs():
            return True
        print("There are stopped jobs.", file=self._notification_stream())
        self._exit_warned = True
        return False

    def _notification_stream(self):
        """Stream for asynchronous job-state notices.

        Bash writes job notifications ([1]+ Done ..., [1]+ Stopped ...)
        to the shell's stderr, never stdout — `bash -i -c 'cmd' >file`
        keeps the notices on the terminal. Use the state's stderr (which
        is forked-child/redirect aware) when available.
        """
        if self.shell_state is not None:
            return self.shell_state.stderr
        return sys.stderr

    def report_abnormal_termination(self, job: Job) -> None:
        """Announce a foreground job killed by a signal, the way bash does.

        bash prints e.g. ``Terminated: 15`` / ``Segmentation fault: 11`` to
        stderr — even non-interactively — when a foreground command dies by a
        signal other than SIGINT/SIGPIPE, so a following command isn't preceded
        by unexplained silence. The exit status (128+N) is set by the caller and
        left unchanged; this only adds the diagnostic. The last process's status
        is the one announced (it becomes ``$?``), matching bash.

        (bash additionally prefixes a ``bash: line N: PID`` job header for
        every signal except SIGTERM; psh emits just the signal description,
        which is exact for SIGTERM and carries the same wording otherwise.)

        Silent inside a command/process substitution — bash does not announce
        signal deaths there, only in the main shell and ( ) subshells.
        """
        if self.shell_state is not None and self.shell_state.in_substitution:
            return
        if not job.processes:
            return
        status = job.processes[-1].status
        if status is None:
            return
        message = abnormal_termination_message(status)
        if message is not None:
            print(message, file=self._notification_stream())

    def _sigpipe_suppressed(self, status: Optional[int]) -> bool:
        """True when bash would print NO notice for this completed bg job.

        bash withholds the bg-job notice for a SIGPIPE death — and only
        SIGPIPE — in INTERACTIVE shells (a broken pipe at the terminal is
        usually benign); a non-interactive script announces it as
        ``Broken pipe: 13``. Every other signal/exit is announced in both.
        Verified against bash 5.2.26 (tmp/probes-r18t2-interactive: interactive
        default AND `set -b` stay silent; `-c … wait` announces).
        """
        if status is None or not os.WIFSIGNALED(status):
            return False
        if os.WTERMSIG(status) != signal.SIGPIPE:
            return False
        return bool(self.shell_state is not None
                    and self.shell_state.options.get('interactive'))

    def _print_completion_notice(self, job: 'Job') -> None:
        """Print bash's async completion notice for a finished bg job.

        The state label is bash-accurate — ``Done``/``Exit N`` for a normal
        exit and the signal description otherwise — via
        :func:`background_completion_label`. An interactive shell withholds
        the SIGPIPE notice (see :meth:`_sigpipe_suppressed`); the job is still
        reaped by the caller either way.
        """
        status = job.processes[-1].status if job.processes else None
        if self._sigpipe_suppressed(status):
            return
        label = background_completion_label(status)
        print(f"\n[{job.job_id}]+  {label:<24}{job.command}",
              file=self._notification_stream())

    def notify_completed_jobs(self):
        """Print notifications for completed background jobs."""
        completed = []
        for job_id, job in list(self.jobs.items()):
            if job.state == JobState.DONE and not job.notified and not job.foreground:
                self._print_completion_notice(job)
                job.notified = True
                completed.append(job_id)

        # Remove completed jobs after notification
        for job_id in completed:
            self.remove_job(job_id)

    def register_background_job(self, job: Job, shell_state=None, last_pid: Optional[int] = None):
        """Mark a job as running in the background and update bookkeeping."""
        job.foreground = False
        job.notified = False

        # Update shell job markers (%+, %-)
        if self.current_job is not job:
            self.previous_job = self.current_job
            self.current_job = job

        # Update $! with the requested PID (or pgid fallback)
        if shell_state is not None:
            shell_state.last_bg_pid = last_pid if last_pid is not None else job.pgid

        return job

    def launch_background(self, pgid: int, command_string: str,
                          processes: Sequence[Tuple[int, str]]) -> 'Job':
        """Record a freshly forked process group as a background job.

        Creates the job, adds its processes, registers it as the current
        background job (setting $! to the pid of the last process), and —
        in interactive shells only, matching bash — prints the "[N] PID"
        notice to stderr. Bash prints the pid of the LAST process in the
        job (the same value $! receives), not the process group id.

        Args:
            pgid: Process group id of the new job
            command_string: Command text for the job table
            processes: (pid, command) pairs, in pipeline order

        Returns:
            The newly created Job
        """
        job = self.create_job(pgid, command_string)
        for pid, proc_command in processes:
            job.add_process(pid, proc_command)
        last_pid = processes[-1][0] if processes else pgid
        self.register_background_job(job, shell_state=self.shell_state,
                                     last_pid=last_pid)
        if self.shell_state and self.shell_state.options.get('interactive'):
            print(f"[{job.job_id}] {last_pid}", file=self._notification_stream())
        return job

    def notify_stopped_jobs(self):
        """Print notifications for newly stopped jobs."""
        for _job_id, job in list(self.jobs.items()):
            if job.state == JobState.STOPPED and not job.notified:
                # Mark with + if it's the current job
                marker = '+' if job == self.current_job else '-' if job == self.previous_job else ' '
                print(f"[{job.job_id}]{marker}  Stopped                 {job.command}",
                      file=self._notification_stream())
                job.notified = True

    def list_jobs(self) -> List[str]:
        """Get formatted list of all jobs."""
        lines = []
        for job_id in sorted(self.jobs.keys()):
            job = self.jobs[job_id]
            is_current = (job == self.current_job)
            is_previous = (job == self.previous_job)
            lines.append(job.format_status(is_current, is_previous))
        return lines

    def resolve_job_spec(self, spec: str, *, bare: str = 'pid') -> JobSpecResult:
        """Resolve a jobspec into a typed result (bash get_job_spec semantics).

        Handles ``%%``/``%+`` and empty (current job), ``%-`` (previous),
        ``%N`` (job number), ``%str`` (command prefix) and ``%?str`` (command
        substring). A prefix/substring matching more than one job is
        :attr:`JobSpecOutcome.AMBIGUOUS`; no match is
        :attr:`JobSpecOutcome.NO_SUCH_JOB`; a missing current/previous job is
        also ``NO_SUCH_JOB`` (bash renders ``%+: no such job``).

        ``bare`` selects how an operand with no ``%`` is read: ``'pid'`` (a
        process id, as ``kill``/``wait``/``disown`` accept) or ``'jobnum'`` (a
        job number, as bash's ``jobs`` treats a bare integer — ``jobs 1`` is
        ``jobs %1``).
        """
        def resolved(job: "Optional[Job]") -> JobSpecResult:
            if job is not None:
                return JobSpecResult(JobSpecOutcome.FOUND, job)
            return JobSpecResult(JobSpecOutcome.NO_SUCH_JOB)

        if not spec:
            return resolved(self.current_job)

        if not spec.startswith('%'):
            if bare == 'jobnum' and spec.isdigit():
                return resolved(self.get_job(int(spec)))
            try:
                pid = int(spec)
            except ValueError:
                return JobSpecResult(JobSpecOutcome.NO_SUCH_JOB)
            return resolved(self.get_job_by_pid(pid))

        body = spec[1:]  # strip the leading %
        if body in ('', '+', '%'):
            return resolved(self.current_job)
        if body == '-':
            return resolved(self.previous_job)
        if body.isdigit():
            return resolved(self.get_job(int(body)))

        if body.startswith('?'):
            pattern = body[1:]
            matches = [j for j in self.jobs.values() if pattern in j.command]
        else:
            pattern = body
            matches = [j for j in self.jobs.values()
                       if j.command.startswith(pattern)]
        if len(matches) == 1:
            return JobSpecResult(JobSpecOutcome.FOUND, matches[0])
        if len(matches) > 1:
            return JobSpecResult(JobSpecOutcome.AMBIGUOUS, pattern=pattern)
        return JobSpecResult(JobSpecOutcome.NO_SUCH_JOB)

    def parse_job_spec(self, spec: str) -> Optional[Job]:
        """The resolved Job for a jobspec, or None (back-compat shim).

        Drops the typed diagnostics of :meth:`resolve_job_spec` (an ambiguous
        spec resolves to None here). Prefer ``resolve_job_spec`` in new code so
        no-such-job / ambiguous / current-unavailable can be reported the way
        bash does.
        """
        return self.resolve_job_spec(spec).job

    def terminal_pgid_if_owned(self) -> Optional[int]:
        """The terminal's foreground pgid, when this shell owns the terminal.

        Returns None when there is no usable tty, job control is
        unsupported, or another process group currently owns the terminal.
        In all of those cases the executors must NOT transfer terminal
        control around a foreground job. This is a real capability check —
        it replaces the old "pytest in sys.modules" test-awareness (under a
        test runner the shell doesn't own the terminal, so this returns
        None there naturally).
        """
        if not self.shell_state or not self.shell_state.supports_job_control:
            return None
        try:
            fg_pgid = os.tcgetpgrp(self.shell_state.terminal_fd)
        except OSError:
            return None
        if fg_pgid != os.getpgrp():
            return None
        return fg_pgid

    def transfer_terminal_control(self, pgid: int, context: str = "") -> bool:
        """Transfer terminal control to a process group.

        This is the single source of truth for all tcsetpgrp() calls:
        every executor that hands the terminal to a foreground job (or
        reclaims it for the shell) goes through here, so capability
        checks and debug logging live in one place.

        Args:
            pgid: Process group ID to transfer control to
            context: Optional context string for debug messages (e.g., "Pipeline", "Subshell")

        Returns:
            True if transfer was successful, False otherwise
        """
        if not self.shell_state or not self.shell_state.supports_job_control:
            if self.shell_state and self.shell_state.options.get('debug-exec'):
                print(f"DEBUG {context}: Skipping terminal transfer (no TTY support)", file=sys.stderr)
            return False

        try:
            os.tcsetpgrp(self.shell_state.terminal_fd, pgid)

            if self.shell_state.options.get('debug-exec'):
                ctx_str = f"{context}: " if context else ""
                print(f"DEBUG {ctx_str}Transferred terminal control to pgid {pgid}", file=sys.stderr)

            return True

        except OSError as e:
            # Log the failure
            if self.shell_state.options.get('debug-exec'):
                ctx_str = f"{context}: " if context else ""
                print(f"WARNING {ctx_str}Failed to transfer terminal control to pgid {pgid}: {e}",
                      file=sys.stderr)

            return False

    def restore_shell_foreground(self):
        """Restore shell to foreground and clean up state.

        This should be called after any foreground job completes
        to ensure terminal and bookkeeping are properly reset. It is the
        single source of truth for foreground-job cleanup: reclaim the
        terminal, restore the shell's terminal modes, and clear the
        foreground bookkeeping.
        """
        shell_pgid = os.getpgrp()

        # Reclaim the terminal FIRST. set_foreground_job(None) restores
        # the shell's terminal modes with tcsetattr(TCSADRAIN), which blocks
        # while another (possibly dead) process group still owns the
        # terminal — the shell hung here after SIGINT killed a foreground
        # job under a PTY.
        self.transfer_terminal_control(shell_pgid, "JobManager:restore")

        # Clear foreground job tracking and restore terminal modes
        self.set_foreground_job(None)
        if self.shell_state is not None and hasattr(self.shell_state, 'foreground_pgid'):
            self.shell_state.foreground_pgid = None

    def finish_foreground_job(self, terminal_transferred: bool,
                              job: Optional['Job'] = None):
        """Tear down foreground-job state after a foreground job completes OR stops.

        When terminal control was handed to the job, restore it to the shell
        (which also clears the foreground bookkeeping). Otherwise (e.g. under
        pytest, where control was never transferred) just clear the
        bookkeeping. Shared by the pipeline and external-command paths.

        A foreground job STOPPED by Ctrl-Z (SIGTSTP) stays in the job table and
        becomes the CURRENT job (``%+``) so a bare ``fg``/``bg`` resumes it
        (bash). The teardown clears foreground tracking — which demotes the
        stopped job to ``%-`` — so re-promote it to ``%+``, keeping the job that
        was current before it as ``%-``.
        """
        # During foreground execution current_job IS this job; previous_job is
        # whatever was current before it (set by set_foreground_job at launch).
        prior_previous = self.previous_job
        if terminal_transferred:
            self.restore_shell_foreground()
        else:
            self.set_foreground_job(None)
            if self.shell_state is not None and hasattr(self.shell_state, 'foreground_pgid'):
                self.shell_state.foreground_pgid = None

        if job is not None and job.state == JobState.STOPPED:
            self.current_job = job
            self.previous_job = prior_previous if prior_previous is not job else None

    @overload
    def wait_for_job(self, job: Job,
                     collect_all_statuses: Literal[False] = ...) -> int: ...
    @overload
    def wait_for_job(self, job: Job,
                     collect_all_statuses: Literal[True]) -> List[int]: ...

    def wait_for_job(self, job: Job,
                     collect_all_statuses: bool = False) -> Union[int, List[int]]:
        """Wait for a job to complete or stop.

        Args:
            job: The job to wait for
            collect_all_statuses: If True, collect exit codes from all processes

        Returns:
            Exit status; a list of per-process statuses when
            ``collect_all_statuses`` is True.
        """
        exit_status = 0
        all_exit_statuses: List[int] = []

        while job.any_process_running():
            try:
                # Wait for any child in the job's process group
                pid, status = os.waitpid(-job.pgid, os.WUNTRACED)
            except OSError as e:
                if e.errno == errno.EINTR:
                    # Interrupted by a signal — keep waiting. (Python
                    # normally retries EINTR itself, but a signal handler
                    # that raises can still surface it.)
                    continue
                if e.errno == errno.ECHILD:
                    # No waitable children remain in the job's process
                    # group, yet some processes are still marked running:
                    # they were reaped elsewhere (e.g. the SIGCHLD
                    # notification path) before we could wait on them.
                    # Mark them completed so the stored-status fallback
                    # below runs — otherwise a job whose processes all
                    # died could incorrectly report exit status 0.
                    for proc in job.processes:
                        if not proc.stopped and not proc.completed:
                            proc.completed = True
                break

            # Update process status
            job.update_process_status(pid, status)

            # Extract exit status
            proc_exit_status = exit_status_from_wait_status(status)

            # Find which process this is
            for i, proc in enumerate(job.processes):
                if proc.pid == pid:
                    if collect_all_statuses:
                        # Store exit status at the correct index
                        while len(all_exit_statuses) <= i:
                            all_exit_statuses.append(0)
                        all_exit_statuses[i] = proc_exit_status

                    # If this was the last process in the pipeline
                    if i == len(job.processes) - 1:
                        exit_status = proc_exit_status

        # If processes were already reaped by the SIGCHLD notification path,
        # derive the exit status from the statuses it recorded. If the LAST
        # process has no recorded status (reaped by something that didn't
        # record it), fall back to the last process that does have one —
        # never silently report 0 when a recorded status says otherwise.
        if not job.any_process_running() and job.processes:
            last_recorded_status = None
            for i, proc in enumerate(job.processes):
                if proc.completed and proc.status is not None:
                    proc_exit_status = exit_status_from_wait_status(proc.status)
                    last_recorded_status = proc_exit_status

                    if collect_all_statuses:
                        while len(all_exit_statuses) <= i:
                            all_exit_statuses.append(0)
                        all_exit_statuses[i] = proc_exit_status

                    # Last process determines default exit status
                    if i == len(job.processes) - 1:
                        exit_status = proc_exit_status

            last_proc = job.processes[-1]
            if last_proc.status is None and last_recorded_status is not None:
                exit_status = last_recorded_status

        # Update job state
        old_state = job.state
        job.update_state()

        # If notify option is enabled and job just completed, notify immediately
        if (self.shell_state and self.shell_state.options.get('notify', False) and
            old_state != JobState.DONE and job.state == JobState.DONE and
            not job.foreground and not job.notified):
            self._print_completion_notice(job)
            job.notified = True

        if collect_all_statuses:
            return all_exit_statuses
        return exit_status
