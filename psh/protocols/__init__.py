"""The narrow shell-service protocols (boundary campaign Q1, §13).

Dependency DIRECTION, made explicit and typed. Historically every component
that needed *anything* from the shell took the whole ``Shell`` — a
service-locator parameter that let a consumer reach any subsystem, so the real
dependency (this expander needs to read a variable; this reader needs stdin)
was invisible to both the reader and the type checker. Q1 named the service
surfaces a migrated boundary can depend on instead of the complete ``Shell``:

===================  =========================================================
Protocol             Canonical producer (``file.py#symbol``)
===================  =========================================================
``ExpansionRuntime`` ``expansion/manager.py#ExpansionManager`` — the expansion
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
``LocaleAccess``     ``core/locale_service.py#LocaleService`` (on
                     ``ShellState.locale``) — collation, locale-gated case
                     mapping, POSIX character-class membership.
``ExpansionHost``    ``shell.py#Shell`` — shell state plus the expansion
                     machinery, and nothing else. The narrow replacement for
                     handing round the whole ``Shell``: consumed by
                     ``expansion/arithmetic/evaluator.py#evaluate_arithmetic``,
                     ``interactive/prompt.py#PromptExpander`` and
                     ``expansion/_protocols.py#VariableExpanderProtocol.host``
                     (remediation 5C.1).
===================  =========================================================

**Names are unique tree-wide.** ``ExpansionRuntime`` and ``LocaleAccess`` were
``ExpansionContext`` / ``LocaleContext`` until remediation 5B.1: each collided
with a live CONCRETE class of the same name
(``lexer/expansion_parser.py#ExpansionContext`` and
``core/locale_service.py#LocaleContext``), so a reader could not tell which one
a module meant. The protocol sides were renamed — they had zero consumers,
the concrete classes did not. ``tests/unit/tooling/test_protocol_name_collision
_q5.py`` keeps the class from recurring.

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

**Every EXPORTED protocol here has at least one production consumer**, and
that is a deliberate property rather than an accident of history: a protocol
nothing depends on documents an intention, not a dependency. The emphasis on
*exported* is load-bearing, not a hedge: remediation 5C.1 added two protocols —
``ExpansionSubExpanders`` and ``ExpansionSurface`` — that are consumed ONLY
from inside this module, as ``ExpansionHost``'s member type and as
``ExpansionSurface``'s own bases. They are deliberately absent from ``__all__``
for exactly the reason this paragraph gives: exporting a surface nothing
outside depends on would manufacture the defect the rule exists to prevent.
They are the declared STRUCTURE of ``ExpansionHost``'s manager member, and the
mutation arms in ``tests/unit/protocols/test_expansion_host_witness_5c1.py``
bite THROUGH them, so they are observed rather than decorative. The census
guard (``tests/unit/protocols/test_protocol_adoption_census_5b2.py``) checks
``__all__``, which is the same line this paragraph draws. Q1 migrated ``IOContext``
(the reader boundary — ``make_reader`` / ``InputCursorRegistry.cursor_for_fd``
took ``Shell`` and used only ``.stdin``) and ``JobRuntime``
(``ForegroundJobSession``, which took the concrete ``JobManager``). Remediation
5B.2 adopted the rest: ``ExpansionRuntime`` by
``expansion/subscript.py#SubscriptEvaluator``, and ``LocaleAccess`` by all SIX
``state.locale`` readers. ``tests/unit/protocols/
test_protocol_adoption_census_5b2.py`` keeps it true by census; the exact
member sets are frozen by ``test_protocol_conformance_q1.py``.

A SIXTH protocol — a three-member variable value-surface
(``get_variable`` / ``set_variable`` / ``get_special_variable``) — was defined
here by the campaign and DELETED by remediation 5B.2 without ever gaining a
consumer. The boundary it was designed for,
``expansion/_protocols.py#VariableExpanderProtocol.state``, reaches ELEVEN
distinct ``ShellState`` members across 47 sites, 44 of them outside that
surface; a tree-wide search (all 19 ``ShellState``-typed parameters, plus every
class holding a ``ShellState`` attribute) found nothing else that could adopt
it either. It was deleted rather than kept on speculation. **A future
value-surface protocol should be designed against that measured 11-member
usage, not against the three-member guess** — the census is recorded in
``VariableExpanderProtocol.state``'s docstring and in successor row D-5B.2-s1.
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
    from ..expansion._protocols import VariableExpanderProtocol
    from ..expansion.word_expander import WordExpander


#: The opaque sort key :meth:`LocaleAccess.collate_key` returns.
#:
#: A libc-derived value that callers only ever hand to ``sorted(key=...)`` or
#: compare against another key from the same locale — never inspect, index, or
#: do arithmetic on. The alias NAMES that opacity rather than dressing it up: a
#: more precise annotation would claim a structure the value does not promise,
#: while a bare ``Any`` says nothing about why it is opaque. Remediation 5B.2.
CollationKey = Any


@runtime_checkable
class ExpansionRuntime(Protocol):
    """The expansion-orchestrator surface (``ExpansionManager``).

    A consumer that must run shell expansions — string ``$``-expansion, an
    assignment-value word expansion, or reach a sub-expander — depends on this
    rather than the whole ``Shell``. ``ExpansionManager`` (``expansion/
    manager.py``) is the producer and structurally satisfies it. This is the
    surface ``expansion/subscript.py#SubscriptEvaluator`` consumes through
    ``shell.expansion_manager`` (it additionally forwards ``shell`` to
    ``evaluate_arithmetic``, which is why that boundary still takes ``Shell`` —
    see the Q1 ratchet).

    NAME (remediation 5B.1): this was ``ExpansionContext`` until the collision
    with the CONCRETE lexer class ``lexer/expansion_parser.py#ExpansionContext``
    was resolved. The protocol side was renamed because it had zero consumers
    while the lexer class is live; ``Runtime`` follows ``JobRuntime`` — this is
    the machinery that RUNS expansions, not a bag of context data.
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

    # Sub-expanders reachable for the lower-level string/escape helpers. Both
    # were ``Any`` until remediation 5B.2 typed them at their producers
    # (``ExpansionManager.__init__`` builds a ``VariableExpander`` and a
    # ``WordExpander``); the variable side is declared against the mixin
    # PROTOCOL rather than the concrete class, because that protocol is already
    # the shared surface its four mixins type-check against.
    #
    # READ-ONLY properties, not plain attributes, and that distinction is
    # load-bearing: a mutable attribute in a Protocol is INVARIANT, so
    # declaring ``variable_expander: VariableExpanderProtocol`` would demand
    # that a producer's attribute be exactly that type — and
    # ``ExpansionManager`` holds a concrete ``VariableExpander``, which is a
    # subtype, not the same type. Nothing consumes these by assignment, so the
    # covariant read surface is both correct and what the producers satisfy.
    @property
    def variable_expander(self) -> "VariableExpanderProtocol": ...

    @property
    def word_expander(self) -> "WordExpander": ...


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

    def publish_foreground_pgid(self, pgid: int) -> None:
        """Record *pgid* as the foreground process group after a handoff.

        Until remediation 5B.2 this protocol instead exposed the whole
        ``shell_state``, and its one consumer reached through it to assign
        ``shell_state.foreground_pgid`` itself — a whole-state member on a
        narrow protocol, for a single ``int`` write. The write moved into the
        producer rather than into ``transfer_terminal_control``: a caller
        census found FIVE paths through that method and only ONE that may
        publish, so folding the write in would have given the other four
        (``fg`` builtin, two SignalManager paths, JobManager's own restore) a
        write they must not perform.
        """
        ...

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
class LocaleAccess(Protocol):
    """The effective-locale service surface (``LocaleService`` on
    ``ShellState.locale``).

    The one home for collation, locale-gated case mapping, and POSIX
    character-class membership (``core/locale_service.py``). A consumer that
    needs locale-correct comparison or case folding depends on this rather than
    the whole ``ShellState``. ``LocaleService`` structurally satisfies it.

    Current callers reach it as ``state.locale``: SIX production files, 13
    access sites (AST census, remediation 5B.1) — ``core/scope.py``,
    ``executor/array.py``, ``executor/enhanced_test_evaluator.py``,
    ``expansion/glob.py``, ``expansion/operators.py`` and
    ``expansion/parameter_expansion.py`` (6 sites, the heaviest reader). An
    earlier version of this docstring named only three; the omitted three are
    part of 5B.2's migration set, so the count matters beyond prose.

    NAME (remediation 5B.1): this was ``LocaleContext`` until the collision with
    the CONCRETE frozen dataclass ``core/locale_service.py#LocaleContext`` was
    resolved. The protocol side was renamed because it had zero consumers, while
    the dataclass is row 4 of the boundary campaign's canonical representation
    set; ``Access`` marks a read surface over a service,
    not the value type. The dataclass keeps the ``Context`` name it is recorded
    under.
    """

    def collate_key(self, s: str) -> "CollationKey":
        """A sort key under the effective ``LC_COLLATE`` (glob/case ranges).

        The key is opaque — see :data:`CollationKey`. Compare keys, sort by
        them; never read inside one.
        """
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


class ExpansionSubExpanders(Protocol):
    """The sub-expanders reachable from the expansion manager.

    ``ExpansionRuntime`` models the manager as an ORCHESTRATOR — run a string
    expansion, run an assignment-value expansion. This models it as a
    DIRECTORY: the four sub-expander members that the variable-expander mixins
    reach through it. The two sets are disjoint, which is why this is a second
    protocol rather than four more members on the first (widening a protocol to
    cover an unrelated use is how a service surface becomes a service locator
    again).

    The membership is exactly the measured hop usage, nothing added "while we
    are here": ``.subscript`` (5 sites), ``.command_sub`` (2),
    ``.execute_arithmetic_expansion`` (1), ``.tilde_expander`` (1).

    Read-only PROPERTIES, not plain attributes: a mutable attribute in a
    Protocol is INVARIANT, so declaring ``subscript: SubscriptEvaluator`` would
    demand a producer hold exactly that type. ``ExpansionManager`` holds
    concrete subtypes and nothing assigns THROUGH these, so the covariant read
    surface is both correct and what the producer satisfies (the 5B.2 lesson).

    Deliberately NOT exported. See :class:`ExpansionSurface`.
    """

    @property
    def subscript(self) -> Any:
        """The array-subscript authority (indexed arithmetic / assoc key)."""
        ...

    @property
    def command_sub(self) -> Any:
        """The command-substitution executor."""
        ...

    @property
    def tilde_expander(self) -> Any:
        """The tilde expander."""
        ...

    def execute_arithmetic_expansion(self, expr: str) -> int:
        """Evaluate an arithmetic expansion body."""
        ...


class ExpansionSurface(ExpansionRuntime, ExpansionSubExpanders, Protocol):
    """The whole expansion-manager surface: orchestration AND sub-expanders.

    Declares NOTHING of its own, and that is the point. Both halves were
    measured independently; composing them is not a widening of either, so
    neither protocol grows to serve a use it was not designed for.

    Not exported, together with :class:`ExpansionSubExpanders`, and the reason
    is a real invariant rather than tidiness: ``psh.protocols`` forbids a
    defined-but-unused EXPORT (``tests/unit/protocols/
    test_protocol_adoption_census_5b2.py``), and these two are consumed only
    from inside this module — as ``ExpansionHost``'s member type and as this
    class's own bases. Exporting them would manufacture the very
    zero-consumer surface that guard exists to prevent. They are the declared
    STRUCTURE of ``ExpansionHost``'s manager member, not independently
    consumable services; a future slot that genuinely wants to consume one
    should export it THEN, together with its consumer.
    """


@runtime_checkable
class ExpansionHost(Protocol):
    """What a consumer needs from the object that owns the expansion machinery.

    The narrow replacement for handing round the whole ``Shell``. Three
    consumers depend on it, and its membership is the measured union of exactly
    what they use:

    * ``expansion/arithmetic/evaluator.py#evaluate_arithmetic`` — ``.state``
      (variables, scope manager, error-location prefix, the arithmetic
      recursion depth) and ``.expansion_manager`` (``expand_string_variables``,
      ``subscript``);
    * ``interactive/prompt.py#PromptExpander`` — ``.state``
      (``command_number``, ``history``) and
      ``.expansion_manager.expand_string_variables``;
    * ``expansion/_protocols.py#VariableExpanderProtocol.host`` — the four
      mixins' sub-expander hops, plus forwarding to the two above.

    Before remediation 5C.1 all three took the whole ``Shell``, which is why
    ``VariableExpanderProtocol`` had to keep a full-``Shell`` member (the
    campaign's "broad owner escape hatch"): the mixins could not be narrower
    than what they forwarded to. Typing these two signatures is what let that
    member retire — the successor step D-5B.2-s2 named.

    ``Shell`` satisfies this structurally (it has both attributes); no producer
    declares it as a base.
    """

    @property
    def state(self) -> ShellState:
        """The shell's variable/option state."""
        ...

    @property
    def expansion_manager(self) -> ExpansionSurface:
        """The expansion machinery, orchestration and sub-expanders."""
        ...


__all__ = [
    "ExpansionHost",
    "ExpansionRuntime",
    "IOContext",
    "JobRuntime",
    "LocaleAccess",
]
