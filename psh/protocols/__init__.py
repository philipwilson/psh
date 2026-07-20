"""The five narrow shell-service protocols (boundary campaign Q1, §13).

Dependency DIRECTION, made explicit and typed. Historically every component
that needed *anything* from the shell took the whole ``Shell`` — a
service-locator parameter that let a consumer reach any subsystem, so the real
dependency (this expander needs to read a variable; this reader needs stdin)
was invisible to both the reader and the type checker. Q1 names the FIVE
service surfaces a migrated boundary can depend on instead of the complete
``Shell``:

===================  =========================================================
Protocol             Canonical producer (``file.py#symbol``)
===================  =========================================================
``VariableAccess``   ``core/scope.py#ScopeManager.lookup`` (the tri-state read
                     authority, ``core/variable_lookup.py#VariableLookup``) +
                     ``core/variable_store.py#VariableStore`` (the write
                     authority), surfaced as ``ShellState.get_variable`` /
                     ``set_variable`` / ``get_special_variable``.
``ExpansionContext`` ``expansion/manager.py#ExpansionManager`` — the expansion
                     orchestrator (word/string expansion + its sub-expanders).
``IOContext``        the shell's three process I/O text streams
                     (``Shell.stdin`` / ``stdout`` / ``stderr``, backed by
                     ``core/stream_bindings.py#StreamBindings``) — the surface
                     the ``io_redirect`` reader layer
                     (``io_redirect/input_cursor.py`` /
                     ``builtins/input_reader.py#make_reader``) needs.
``JobRuntime``       ``executor/job_control.py#JobManager`` — the job-table /
                     terminal-transfer / wait surface the foreground-job
                     transaction (``executor/foreground_session.py``) drives.
``LocaleContext``    ``core/locale_service.py#LocaleService`` (on
                     ``ShellState.locale``) — collation, locale-gated case
                     mapping, POSIX character-class membership.
===================  =========================================================

**Import direction is one-way and enforced.** This module imports NOTHING from
``psh`` at runtime — every producer/value type it names in an annotation is
imported only under ``TYPE_CHECKING`` (annotations are PEP 563 strings here), so
``psh.protocols`` is a true leaf. Implementations may import a protocol; a
protocol may never import an implementation. Guarded by
``tests/unit/tooling/test_protocol_layering_q1.py`` (a sibling of the r19
import-layering guard). The producers satisfy these protocols STRUCTURALLY — no
producer declares one as a base — proven at runtime by
``tests/unit/protocols/test_protocol_conformance_q1.py`` (``isinstance`` against
a live ``Shell``), which is also the behavioral-inertness pin: the migrations
change only annotations, because ``Shell`` already IS each of these.

The protocols are ``@runtime_checkable`` so that conformance test can
``isinstance``; runtime checking verifies member PRESENCE only (never
signatures), which is exactly the "does the producer expose this surface"
question the pin asks. Consumers narrow via string (``TYPE_CHECKING``)
annotations, so a migration adds NO runtime import edge to this package.

Scope note (Q1 census, ``tmp/boundary-ledgers/Q1.md``): this slot MIGRATES two
boundaries. ``IOContext`` — the reader boundary (``make_reader`` /
``InputCursorRegistry.cursor_for_fd`` took ``Shell``, used only ``.stdin``).
``JobRuntime`` — ``ForegroundJobSession`` took the concrete ``JobManager`` and
now takes this protocol (mypy-checked: ``JobManager`` satisfies it structurally).
``VariableAccess`` / ``ExpansionContext`` / ``LocaleContext`` are DEFINED against
their producers, member-frozen and conformance-pinned, but consumer adoption is
POST-CAMPAIGN: their touched-set consumers genuinely retain ``Shell`` for a need
no protocol covers (``subscript`` forwards ``shell`` to ``evaluate_arithmetic``;
the ``child_policy`` runners reach the trap/signal/executor machinery;
``resolve_command`` forwards ``shell`` to ``ExecutionStrategy.can_execute``;
``execute_sourced_file`` owns the source-depth / positionals / RETURN-trap
transaction) — each recorded, with its justification, in the shrink-only ratchet
``tests/unit/tooling/test_shell_consumer_ratchet_q1.py``. Their exact member
sets are frozen by ``tests/unit/protocols/test_protocol_conformance_q1.py``.
"""
from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    List,
    Optional,
    Protocol,
    TextIO,
    overload,
    runtime_checkable,
)

if TYPE_CHECKING:
    from typing import Literal

    from ..ast_nodes.words import Word
    from ..core.state import ShellState
    from ..executor.job_control import Job


@runtime_checkable
class VariableAccess(Protocol):
    """Read/write access to shell variables — the value surface, not the store.

    The canonical READ authority is ``ScopeManager.lookup`` (returns the
    tri-state ``VariableLookup`` — ``core/variable_lookup.py``); the canonical
    WRITE authority is ``VariableStore`` (``core/variable_store.py``, the single
    mutation transaction boundary). ``ShellState`` projects both as the ergonomic
    accessors below and structurally satisfies this protocol. A consumer that
    needs only to read/write named values depends on THIS, not on ``ShellState``
    (which also carries options, execution state, streams, ...).
    """

    def get_variable(self, name: str, default: str = "") -> str:
        """The string projection of ``lookup(name)`` (VALUE → its value, else
        ``default``); no environment fallback (appraisal #20 H13)."""
        ...

    def set_variable(self, name: str, value: Any) -> None:
        """Bind ``name`` through the write authority (readonly/nameref/observer
        guards apply)."""
        ...

    def get_special_variable(self, name: str) -> str:
        """Read a special parameter (``?`` ``$`` ``!`` ``#`` ``@`` ``*`` ...)."""
        ...


@runtime_checkable
class ExpansionContext(Protocol):
    """The expansion-orchestrator surface (``ExpansionManager``).

    A consumer that must run shell expansions — string ``$``-expansion, an
    assignment-value word expansion, or reach a sub-expander — depends on this
    rather than the whole ``Shell``. ``ExpansionManager`` (``expansion/
    manager.py``) is the producer and structurally satisfies it. This is the
    surface ``expansion/subscript.py#SubscriptEvaluator`` consumes through
    ``shell.expansion_manager`` (it additionally forwards ``shell`` to
    ``evaluate_arithmetic``, which is why that boundary still takes ``Shell`` —
    see the Q1 ratchet).
    """

    def expand_string_variables(self, text: str,
                                quote_ctx: Optional[str] = None) -> str:
        """Expand ``$``-constructs in a raw string (one verbatim pass)."""
        ...

    def expand_assignment_value_word(self, word: "Word") -> str:
        """Expand a parsed ``Word`` under assignment-value semantics (composite
        quoting, ``$'...'`` decode, no split/glob) — the associative-key /
        array-initializer engine."""
        ...

    # Sub-expanders reachable for the lower-level string/escape helpers.
    variable_expander: Any
    word_expander: Any


@runtime_checkable
class IOContext(Protocol):
    """The shell's three process I/O text streams.

    ``Shell.stdin`` / ``stdout`` / ``stderr`` (read-write properties over
    ``core/stream_bindings.py#StreamBindings``) — injectable, so a test can swap
    a ``StringIO`` in. A reader/writer boundary that needs only the streams
    (not variables, options, or job control) depends on THIS. ``Shell``
    structurally satisfies it.

    MIGRATED consumers (Q1): ``builtins/input_reader.py#make_reader`` (reads
    ``.stdin`` to build an ``InputCursor``) and
    ``io_redirect/input_cursor.py#InputCursorRegistry.cursor_for_fd`` (forwards
    to ``make_reader``). Both took ``Shell`` and used only ``.stdin``.
    """

    @property
    def stdin(self) -> TextIO: ...

    @property
    def stdout(self) -> TextIO: ...

    @property
    def stderr(self) -> TextIO: ...


@runtime_checkable
class JobRuntime(Protocol):
    """The job-table / terminal-transfer / wait surface (``JobManager``).

    MIGRATED consumer (Q1): the foreground-job transaction
    (``executor/foreground_session.py#ForegroundJobSession``) takes THIS (was the
    concrete ``JobManager``) and drives exactly this subset — create/register a
    job, hand it (and reclaim) the terminal, wait, report a signal death, rotate
    the current job. ``JobManager`` (``executor/job_control.py``) structurally
    satisfies it (mypy-checked at the call site).
    """

    #: The shell state, wired via ``JobManager.set_shell_state`` (read to publish
    #: ``foreground_pgid`` on terminal handoff).
    shell_state: "Optional[ShellState]"

    def terminal_pgid_if_owned(self) -> Optional[int]:
        """The terminal's foreground pgid if this shell owns it, else None."""
        ...

    def create_job(self, pgid: int, command: str) -> "Job": ...

    def set_foreground_job(self, job: "Optional[Job]") -> None: ...

    def transfer_terminal_control(self, pgid: int, context: str = "") -> bool: ...

    @overload
    def wait_for_job(self, job: "Job",
                     collect_all_statuses: "Literal[False]" = ...) -> int: ...
    @overload
    def wait_for_job(self, job: "Job",
                     collect_all_statuses: "Literal[True]") -> List[int]: ...

    def report_signal_death_at(self, job: "Job", index: int) -> None: ...

    def finish_foreground_job(self, terminal_transferred: bool,
                              job: "Optional[Job]" = None) -> None: ...

    def remove_job(self, job_id: int) -> None: ...


@runtime_checkable
class LocaleContext(Protocol):
    """The effective-locale service surface (``LocaleService`` on
    ``ShellState.locale``).

    The one home for collation, locale-gated case mapping, and POSIX
    character-class membership (``core/locale_service.py``). A consumer that
    needs locale-correct comparison or case folding depends on this rather than
    the whole ``ShellState``. ``LocaleService`` structurally satisfies it;
    current callers (``expansion/glob.py``, ``expansion/parameter_expansion.py``,
    ``executor/enhanced_test_evaluator.py``) read it as ``state.locale`` and are
    outside this slot's touched set.
    """

    def collate_key(self, s: str) -> Any:
        """A sort key under the effective ``LC_COLLATE`` (glob/case ranges)."""
        ...

    def compare(self, a: str, b: str) -> int:
        """Three-way collation comparison under the effective ``LC_COLLATE``."""
        ...

    def upper(self, s: str) -> str: ...

    def lower(self, s: str) -> str: ...

    def toggle(self, s: str) -> str: ...

    def in_class(self, ch: str, name: str) -> bool:
        """POSIX character-class membership (``[[:alpha:]]`` &c.)."""
        ...


__all__ = [
    "VariableAccess",
    "ExpansionContext",
    "IOContext",
    "JobRuntime",
    "LocaleContext",
]
