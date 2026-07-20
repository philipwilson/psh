"""Disown builtin command for job control."""

from typing import TYPE_CHECKING, List

from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


@builtin
class DisownBuiltin(Builtin):
    """Remove jobs from active job table."""

    @property
    def name(self) -> str:
        return "disown"

    @property
    def synopsis(self) -> str:
        return "disown [-h] [-ar] [jobspec ... | pid ...]"

    @property
    def description(self) -> str:
        return "Remove jobs from active job table"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Execute disown command."""
        # -h/-a/-r are boolean flags (clusterable, e.g. -ar); job specs and
        # PIDs are operands and never start with '-'.
        opts, job_specs = self.parse_flags(args, shell, flags='har')
        if opts is None:
            return 2
        mark_no_hup = opts['h']
        disown_all = opts['a']
        running_only = opts['r']

        # Get job manager
        job_manager = shell.job_manager

        # Both -a (all jobs) and -r (all RUNNING jobs) select the whole set —
        # -r does not need -a. The earlier code only branched here for -a, so a
        # lone `disown -r` fell through to the current-job path.
        if disown_all or running_only:
            return self._disown_all_jobs(job_manager, running_only, mark_no_hup, shell)

        if not job_specs:
            # No job specs - disown current job
            current_job = job_manager.current_job
            if current_job is None:
                self.error("no current job", shell)
                return 1
            return self._disown_job(current_job, mark_no_hup, job_manager, shell)

        # Disown specific jobs
        exit_status = 0
        for spec in job_specs:
            if self._disown_job_spec(spec, mark_no_hup, job_manager, shell) != 0:
                exit_status = 1

        return exit_status

    def _disown_all_jobs(self, job_manager, running_only: bool, mark_no_hup: bool, shell: 'Shell') -> int:
        """Disown all jobs (or all running jobs if running_only is True)."""
        jobs_to_disown = []

        for job in job_manager.jobs.values():
            if running_only:
                # Only disown running jobs
                if job.state.name == 'RUNNING':
                    jobs_to_disown.append(job)
            else:
                # Disown all jobs
                jobs_to_disown.append(job)

        # bash: `disown -a` / `disown -r` on an empty (or all-not-running)
        # table SUCCEEDS silently — the selection is empty, not an error.
        # Disown each selected job.
        for job in jobs_to_disown:
            self._disown_job(job, mark_no_hup, job_manager, shell)

        return 0

    def _disown_job_spec(self, spec: str, mark_no_hup: bool, job_manager, shell: 'Shell') -> int:
        """Disown a job by job specification or PID."""
        if spec.startswith('%'):
            # Job specification
            job = job_manager.parse_job_spec(spec)
            if job is None:
                self.error(f"{spec}: no such job", shell)
                return 1
            return self._disown_job(job, mark_no_hup, job_manager, shell)
        else:
            # Try as PID
            try:
                pid = int(spec)
                job = job_manager.get_job_by_pid(pid)
                if job is None:
                    self.error(f"{pid}: no such job", shell)
                    return 1
                return self._disown_job(job, mark_no_hup, job_manager, shell)
            except ValueError:
                self.error(f"{spec}: not a valid job specification or process id", shell)
                return 1

    def _disown_job(self, job, mark_no_hup: bool, job_manager, shell: 'Shell') -> int:
        """Disown a specific job.

        With ``-h`` (``mark_no_hup``) bash marks the job to not receive SIGHUP
        when the shell exits but keeps it in the job table — psh records the
        typed ``Job.no_hup`` flag the one ``Shell.shutdown`` HUP/CONT path
        honors (#20 H19). Without ``-h`` the job is detached from the
        user-visible table while KEEPING reap ownership of any still-running
        member (:meth:`JobManager.detach_running_job`), so a disowned child
        that later exits is reaped rather than orphaned as a zombie.
        """
        if mark_no_hup:
            job.no_hup = True
        else:
            job_manager.detach_running_job(job)
        return 0

    @property
    def help(self) -> str:
        return """disown: disown [-h] [-ar] [jobspec ... | pid ...]
    Remove jobs from active job table.

    Options:
        -a      Remove all jobs from job table
        -h      Keep the job in the table but exempt it from SIGHUP on exit
        -r      Remove only running jobs from job table

    Arguments:
        jobspec     Job specification (e.g., %1, %+, %-)
        pid         Process ID

    Without options or arguments, removes the current job from the
    active job table.

    With -h the job stays in the table but is marked to NOT receive SIGHUP
    when an interactive shell with `shopt -s huponexit` exits. Otherwise the
    job is removed from the table; psh keeps reap ownership of a still-running
    disowned child so it is not orphaned as a zombie.

    Exit Status:
    Returns 0 unless an invalid option or job specification is given."""
