"""
Heredoc collection support for the PSH lexer.

The :class:`HeredocCollector` is the FIFO collector of the campaign-S2
heredoc transaction: registration constructs a :class:`HeredocSpec` for each
``<<``/``<<-`` operator (ordinal identity — duplicate textual delimiters are
distinct), gathering routes every input line through the ONE head-of-queue
close policy (:class:`PendingHeredocQueue`), and each completed body becomes
a typed :class:`CollectedHeredoc` (terminated by its delimiter line or by
end of input).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..utils.heredoc_detection import (
    CollectedHeredoc,
    HeredocSpec,
    HeredocTermination,
    PendingHeredocQueue,
    make_heredoc_spec,
)


@dataclass
class _Gathering:
    """Per-pending gathering state: body lines and the 1-based source line
    where this heredoc's body begins. ``start_line`` is re-stamped when a
    pending heredoc is promoted to queue head (matching the line bash
    reports in its "delimited by end-of-file" warning)."""

    start_line: int
    lines: List[str] = field(default_factory=list)
    last_line: int = 0


class HeredocCollector:
    """The FIFO collector: registers specs, gathers bodies in source order.

    ``specs`` maps ordinal id -> :class:`HeredocSpec` (every heredoc ever
    registered, in id order); ``collected`` maps id -> :class:`CollectedHeredoc`
    for every COMPLETED body. The pending set is the :class:`PendingHeredocQueue`
    — the sole close-decision authority.
    """

    def __init__(self) -> None:
        self.specs: Dict[int, HeredocSpec] = {}
        self.collected: Dict[int, CollectedHeredoc] = {}
        self.queue = PendingHeredocQueue()
        self._gathering: Dict[int, _Gathering] = {}

    def register_heredoc(self, raw: str, strip_tabs: bool, line: int,
                         span: Tuple[int, int] = (0, 0)) -> HeredocSpec:
        """Register a newly scanned ``<<``/``<<-`` operator's delimiter word.

        ``raw`` is the exact source spelling of the delimiter word (from the
        token span); the spec's cooked/quoted facts are derived by the sole
        constructor :func:`make_heredoc_spec`. ``line`` is the 1-based source
        line where this heredoc's body gathering would begin.
        """
        spec = make_heredoc_spec(ordinal=len(self.specs), raw=raw,
                                 strip_tabs=strip_tabs, span=span)
        self.specs[spec.id] = spec
        self.queue.push(spec)
        self._gathering[spec.id] = _Gathering(start_line=line)
        return spec

    def has_pending_heredocs(self) -> bool:
        """True while at least one registered heredoc still needs its body."""
        return bool(self.queue)

    def restamp_head_start(self, line: int) -> None:
        """The (new) head's body gathering begins at source line *line*."""
        head = self.queue.head
        if head is not None:
            self._gathering[head.id].start_line = line

    def collect_line(self, line: str, lineno: int = 0) -> Optional[int]:
        """Feed one physical *line* to the head pending heredoc.

        Delegates the terminator decision to the head-of-queue policy: if the
        line terminates the HEAD, its :class:`CollectedHeredoc` is recorded
        and the completed spec id returned; otherwise the line is body text
        of the head (``<<-`` tab-stripping applied) and None is returned.
        """
        head = self.queue.head
        if head is None:
            return None
        closed = self.queue.feed_line(line)
        if closed is not None:
            self._finish(closed, HeredocTermination.DELIMITER)
            return closed.id
        gathering = self._gathering[head.id]
        gathering.lines.append(line.lstrip('\t') if head.strip_tabs else line)
        gathering.last_line = lineno
        return None

    def finalize_at_eof(self, last_line: int) -> List[Tuple[HeredocSpec, int]]:
        """End of input with heredocs still pending: delimit them by EOF.

        Bash does not drop an unterminated heredoc — it uses everything
        gathered so far as the body, warns ("here-document at line N
        delimited by end-of-file"), and runs the command. Content routing
        matches bash: the first pending heredoc keeps the gathered lines;
        any later pending heredocs get empty bodies. The typed
        ``HeredocTermination.EOF`` outcome is recorded either way — a TRIAL
        parse suppresses the warning, never the fact.

        Returns ``(spec, warn_line)`` pairs for the caller's warnings, in
        order: the first pending heredoc reports the line its body gathering
        began at (possibly re-stamped); later ones report ``last_line``,
        where their gathering would have begun (bash reports the same).
        """
        warnings: List[Tuple[HeredocSpec, int]] = []
        for index, spec in enumerate(self.queue.drain()):
            gathering = self._gathering[spec.id]
            warn_line = gathering.start_line if index == 0 else last_line
            warnings.append((spec, warn_line))
            self._finish(spec, HeredocTermination.EOF)
        return warnings

    def _finish(self, spec: HeredocSpec, termination: HeredocTermination) -> None:
        gathering = self._gathering.pop(spec.id)
        lines = gathering.lines
        body = '\n'.join(lines) + ('\n' if lines else '')
        if lines:
            span = (gathering.start_line,
                    gathering.last_line or gathering.start_line)
        else:
            span = (gathering.start_line, gathering.start_line - 1)
        self.collected[spec.id] = CollectedHeredoc(
            spec_id=spec.id, body=body, termination=termination, span=span)
