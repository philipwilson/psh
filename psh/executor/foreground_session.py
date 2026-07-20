"""The one foreground-job transaction (campaign J1).

A command, a pipeline, and a foreground subshell each hand a freshly launched
process group to the terminal, wait for it, report a signal death, rotate the
current job, and reclaim the terminal — the SAME transaction. Before J1 the
three paths each open-coded it, and the subshell path (``subshell.py``) had
drifted: it never registered the job as the foreground job, never announced a
signal death (``( kill -s TERM $BASHPID )`` was SILENT where bash prints
``Terminated: 15``), used ``restore_shell_foreground()`` directly instead of
``finish_foreground_job()`` (so a Ctrl-Z-stopped subshell was not promoted to
``%+``), and had no exception cleanup.

``ForegroundJobSession`` owns that transaction once, for all three:

    session = ForegroundJobSession.open(shell.job_manager)  # BEFORE the fork
    pid, pgid = launcher.launch(...)                        # launch
    try:
        session.register(pgid, command, [(pid, label), ...])
        status = session.wait()          # or wait_all() for a pipeline
        session.report_signal_death()    # or report_signal_death(idx)
    finally:
        session.finish()                 # reclaim terminal + drop DONE job

``open`` captures the terminal owner BEFORE the launch (the shell still owns
it then); ``register`` creates the job, records it as the foreground job, and
transfers the terminal; ``finish`` reclaims the terminal, clears the
foreground bookkeeping (promoting a re-stopped job to ``%+``), and drops the
job if it completed. ``finish`` is idempotent, so the ``try/finally`` gives
exception cleanup — a wait that raises still reclaims the terminal.

It composes WITH the process/redirect lease machinery (campaign F2/R1): it
never calls ``tcsetpgrp`` or saves/restores fds itself — the terminal transfer
goes through ``JobManager.transfer_terminal_control`` and the fd discipline
stays in the IO/redirect layer.
"""
from typing import TYPE_CHECKING, List, Optional, Sequence, Tuple

from .job_control import JobState

if TYPE_CHECKING:
    from .job_control import Job, JobManager


class ForegroundJobSession:
    """One foreground-job transaction: registration, terminal transfer/capture/
    restore, waiting, signal-death reporting, current-job rotation, and
    exception cleanup. Shared by external commands, pipelines, and foreground
    subshells (campaign J1)."""

    def __init__(self, job_manager: "JobManager"):
        self._jm = job_manager
        #: The terminal's foreground pgid before the launch (None ⇒ this shell
        #: does not own the terminal, e.g. under pytest / non-interactive).
        self.original_pgid: Optional[int] = None
        self.job: Optional["Job"] = None
        #: Whether tcsetpgrp actually handed the terminal to the job.
        self.terminal_transferred: bool = False
        self._status_index: int = -1
        self._finished: bool = False

    @classmethod
    def open(cls, job_manager: "JobManager") -> "ForegroundJobSession":
        """Open a session, capturing the terminal owner BEFORE the launch.

        Must be called while the shell still owns the terminal — i.e. before
        the job's process group is forked and handed the terminal.
        """
        session = cls(job_manager)
        session.original_pgid = job_manager.terminal_pgid_if_owned()
        return session

    def register(self, pgid: int, command: str,
                 processes: Sequence[Tuple[int, str]]) -> "Job":
        """Create the job, record it as the foreground job, and hand it the
        terminal (when this shell owns it)."""
        jm = self._jm
        job = jm.create_job(pgid, command)
        for pid, label in processes:
            job.add_process(pid, label)
        job.foreground = True
        self.job = job
        # Terminal-mode handoff + foreground-job tracking (a running foreground
        # job does NOT enter the %+/%- rotation — set_foreground_job is
        # careful not to).
        jm.set_foreground_job(job)
        if self.original_pgid is not None:
            if jm.transfer_terminal_control(pgid, "ForegroundJobSession"):
                self.terminal_transferred = True
                if jm.shell_state is not None:
                    jm.shell_state.foreground_pgid = pgid
        return job

    def wait(self) -> int:
        """Wait for a single-process job (command / subshell); the announced
        member is its last (only) process."""
        assert self.job is not None
        status = self._jm.wait_for_job(self.job)
        self._status_index = len(self.job.processes) - 1
        return status

    def wait_all(self) -> List[int]:
        """Wait for every member (pipeline); returns per-member statuses for
        PIPESTATUS. The announced member defaults to the last; the caller may
        override via :meth:`report_signal_death` after selecting the pipefail
        member."""
        assert self.job is not None
        statuses = self._jm.wait_for_job(self.job, collect_all_statuses=True)
        if not isinstance(statuses, list):
            statuses = [statuses]
        self._status_index = len(statuses) - 1
        return statuses

    def report_signal_death(self, status_index: Optional[int] = None) -> None:
        """Announce the status-determining member's signal death (bash).

        Defaults to the member whose status this session waited on; a pipeline
        passes the pipefail-selected index.
        """
        assert self.job is not None
        idx = self._status_index if status_index is None else status_index
        self._jm.report_signal_death_at(self.job, idx)

    def finish(self) -> None:
        """Reclaim the terminal, clear foreground bookkeeping (promoting a
        re-stopped job to ``%+``), and drop the job if it completed.

        Idempotent — safe to call from a ``finally`` after a normal path that
        also called it, and safe when ``register`` never ran (a launch that
        failed before registration)."""
        if self._finished:
            return
        self._finished = True
        # finish_foreground_job takes "was the terminal transfer intended?"
        # (original_pgid is not None) — matching the pre-J1 external/pipeline
        # calls — so a transfer that we attempted but that failed still
        # reclaims via restore_shell_foreground rather than stranding it.
        self._jm.finish_foreground_job(self.original_pgid is not None, self.job)
        if self.job is not None and self.job.state == JobState.DONE:
            self._jm.remove_job(self.job.job_id)
