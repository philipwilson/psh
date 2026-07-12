"""Shared job-control vocabulary (state enum + jobspec result types).

This module holds the small, dependency-free value types that both the
executor's :class:`~psh.executor.job_control.JobManager` and the job builtins
(`jobs`/`fg`/`bg`/`kill`/`disown`/`wait`) speak. It lives in ``psh.core`` so
the builtins can name a job's state and a jobspec resolution outcome WITHOUT
importing ``psh.executor`` — breaking the former ``builtins <-> executor``
runtime import cycle (P4, reappraisal #19). The executor's ``job_control``
module imports these names back and re-exports them, so callers that reach for
``psh.executor.job_control.JobState`` continue to work unchanged.

Only leaf value types belong here. The behavior-bearing classes ``Job``,
``Process``, and ``JobManager`` — with their waitpid/signal machinery — stay in
``psh.executor.job_control``.
"""

import os
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    # Type-only back-reference for JobSpecResult.job; not a runtime import, so
    # core stays runtime-independent of the executor.
    from ..executor.job_control import Job


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
