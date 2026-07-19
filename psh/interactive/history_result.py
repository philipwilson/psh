"""The typed outcome of a history expansion (campaign I4).

A history reference can resolve four distinct ways, and the old
``Optional[str]`` contract of :meth:`HistoryExpander.expand_history` conflated
them: ``None`` meant "failed", ``''`` meant "print-only", and any other string
meant "expanded OR unchanged" — with a private ``expanded`` bool (never
returned) as the only signal that a reference actually fired. Recording and
diagnostics then re-derived the outcome from a regex
(``contains_history_reference``) and from string identity. Reappraisal #20's
history finding: a syntactically live reference that FAILS, that only PRINTS,
or that expands to text IDENTICAL to the input are three different events that
``expanded_text != original_text`` cannot tell apart.

:class:`HistoryExpansionResult` is the single typed answer. Its ``kind`` is the
authority; consumers branch on it rather than inspecting the text. The producer
(:meth:`HistoryExpander.expand_history`) is PURE — it never prints and never
records; the reporting consumer echoes/prints/records from the result and the
silent completeness trial reads only ``kind``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Tuple


class HistoryExpansionKind(Enum):
    """Which of the four distinct history-expansion outcomes occurred."""

    #: No live reference (or ``histexpand`` off): ``text`` is the input verbatim.
    NONE = auto()
    #: A reference resolved: ``text`` is the expansion (which MAY equal the
    #: input — ``!!`` repeating an identical command still counts as EXPANDED,
    #: because bash echoes and records it as one).
    EXPANDED = auto()
    #: A ``:p`` modifier fired: ``text`` is the expansion to PRINT; it is
    #: recorded but NOT executed.
    PRINT_ONLY = auto()
    #: The reference failed (event not found / bad word specifier / substitution
    #: failed). ``error`` is the diagnostic body; the line is NOT recorded.
    ERROR = auto()


@dataclass(frozen=True)
class HistoryExpansionSpan:
    """A resolved (or failing) reference's ``[start, end)`` span in the input."""

    start: int
    end: int


@dataclass(frozen=True)
class HistoryExpansionResult:
    """The typed outcome of one :meth:`HistoryExpander.expand_history` call."""

    kind: HistoryExpansionKind
    text: str
    error: Optional[str] = None
    spans: Tuple[HistoryExpansionSpan, ...] = field(default_factory=tuple)

    @property
    def is_error(self) -> bool:
        return self.kind is HistoryExpansionKind.ERROR

    @property
    def is_print_only(self) -> bool:
        return self.kind is HistoryExpansionKind.PRINT_ONLY

    @property
    def is_expanded(self) -> bool:
        return self.kind is HistoryExpansionKind.EXPANDED

    @property
    def changed(self) -> bool:
        """A reference actually fired (EXPANDED or PRINT_ONLY).

        The point of the type: this is TRUE even when ``text == original`` (an
        identical ``!!`` re-run), which a string comparison would miss, and
        FALSE for a ``histexpand``-off line that still contains a literal ``!``.
        """
        return self.kind in (HistoryExpansionKind.EXPANDED,
                              HistoryExpansionKind.PRINT_ONLY)

    @property
    def recordable_text(self) -> Optional[str]:
        """The text to record in history for this outcome, or ``None``.

        bash records the EXPANDED line (``NONE`` verbatim, ``EXPANDED`` /
        ``PRINT_ONLY`` the expansion) and records NOTHING for an ``ERROR``.
        """
        if self.kind is HistoryExpansionKind.ERROR:
            return None
        return self.text
