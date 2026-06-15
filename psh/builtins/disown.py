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

        if disown_all:
            # Disown all jobs
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

        if not jobs_to_disown:
            if running_only:
                self.error("no running jobs", shell)
            else:
                self.error("no jobs", shell)
            return 1

        # Disown each job
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
        """Disown a specific job."""
        if mark_no_hup:
            # Mark job to not receive SIGHUP, but keep in job table
            job.no_hup = True
            # In a real implementation, this would set a flag that prevents
            # SIGHUP from being sent to the job when the shell exits
        else:
            # Remove job from job table completely
            job_manager.remove_job(job.job_id)

        return 0

    @property
    def help(self) -> str:
        return """disown: disown [-h] [-ar] [jobspec ... | pid ...]
    Remove jobs from active job table.

    Options:
        -a      Remove all jobs from job table
        -h      Mark jobs to not receive SIGHUP when shell exits
        -r      Remove only running jobs from job table

    Arguments:
        jobspec     Job specification (e.g., %1, %+, %-)
        pid         Process ID

    Without options or arguments, removes the current job from the
    active job table.

    When -h is used, jobs are marked to not receive SIGHUP but remain
    in the job table. Otherwise, jobs are completely removed.

    Exit Status:
    Returns 0 unless an invalid option or job specification is given."""
