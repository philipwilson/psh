"""The ONE array-subscript keying authority (campaign W2).

Reappraisal #21's signature finding was that a single feature — interpreting an
array subscript — was implemented six-plus inconsistent ways across six modules:
the write path stored a literal key, the read/unset paths resolved a bare name
through a same-named variable, the ``+``/``-``/``?`` is-set operator used a third
expansion, the arithmetic path required parse-as-arithmetic and mis-keyed
whitespace, ``$'...'`` keys went undecoded, and an unsubscripted ``$assoc``
returned empty. This module replaces all of them with one service.

The architectural core is **target-kind BEFORE interpretation**: bash decides
whether the target is indexed or associative from the DECLARED variable, and
only THEN interprets the subscript. An undeclared name defaults to indexed
(arithmetic) — quoting does NOT infer an associative array. The two
interpretations are:

- **Indexed** (``a[i]``): the subscript is an arithmetic expression. Variables
  expand, then it is arithmetic-evaluated (lazily parsed) to an ``int``. A bare
  name is a variable reference (``a[i]`` with ``i=3`` addresses ``a[3]``); a
  subscript that fails to evaluate is a fatal shell error (bash), not a silent 0.

- **Associative** (``h[k]``): the subscript is a literal STRING key produced by
  ONE word/quote expansion under assignment-value semantics — every expansion is
  performed, quotes are removed, composite quoting concatenates
  (``h['a''b']`` -> key ``ab``), ``$'...'`` decodes, a leading ``~`` tilde-expands,
  but there is NO word splitting and NO pathname generation, and a BARE NAME is
  a literal (``h[k]`` keys ``k``, never ``$k``'s value). This is exactly the
  engine the array-initializer ``[key]=value`` path already uses
  (``expand_assignment_value_word``), reused here so every site keys identically.

Callers resolve the target's kind and pass it in; the service never re-decides.
"""
import enum
from typing import TYPE_CHECKING, Iterator, List, Union

from ..ast_nodes.words import CommandSubstitution, ExpansionPart, LiteralPart, Word, WordPart
from ..core import arith_assignment_discard
from ..core.exceptions import ExpansionError, PshError
from ..lexer import tokenize
from ..lexer.cmdsub_scanner import find_command_substitution_end
from ..lexer.token_types import TokenType
from .arithmetic import ArithmeticError, evaluate_arithmetic
from .param_parser import skip_quoted_run

if TYPE_CHECKING:
    from ..core.state import ShellState
    from ..protocols import ExpansionHost, ExpansionRuntime


class SubscriptSyntaxError(ExpansionError):
    """Raw subscript TEXT that cannot be re-lexed into a word (campaign 2.3).

    Raised by :meth:`SubscriptEvaluator.word_from_text` when re-lexing raw
    subscript source fails — an unclosed quote (``a["]``) or an unclosed
    substitution spelling (``a[$(]``). Replaces the former broad
    ``except Exception`` fallbacks that silently degraded the un-lexable text
    to a LITERAL key (MEDIUM-12a: that swallow masked extent bugs as
    wrong-key writes, and a genuine internal defect as a key). Only the
    lexer's own typed failures (``PshError``: ``UnclosedQuoteError``,
    ``SubstitutionSyntaxError`` — the census in the slot ledger found no
    other live raiser) are translated; any other exception is an internal
    defect and now propagates loudly (strict-errors).

    An ``ExpansionError``, so an expansion-path caller gets bash's
    discard-line model; the BUILTIN keying surfaces translate it instead
    (bash 5.2, probe-verified): ``unset`` reports "not a valid identifier"
    (rc 1, loud) and ``test -v`` / ``[[ -v`` report quietly unset (rc 1).
    Carries ``raw`` (the offending subscript text)."""

    def __init__(self, raw: str):
        self.raw = raw
        super().__init__(f"[{raw}]: bad array subscript", exit_code=1)


class TargetKind(enum.Enum):
    """Whether a subscript addresses an indexed (arithmetic) or associative
    (string-key) target. Decided by the caller from the DECLARED variable."""
    INDEXED = enum.auto()
    ASSOCIATIVE = enum.auto()


class SubscriptUse(enum.Enum):
    """Which surface is keying — drives the EMPTY-subscript policy for
    indexed targets in :meth:`SubscriptEvaluator.evaluate`.

    bash 5.2 treats an (expanded-)empty indexed subscript differently per
    surface (probe-verified 2026-07-19): read/write address index 0 (empty
    arithmetic evaluates to 0), while ``test -v``/``[[ -v`` report silently
    unset and ``unset`` is a silent no-op. So ``TEST_V`` and ``UNSET`` make
    :meth:`~SubscriptEvaluator.evaluate` return ``None`` ("no target") for an
    empty indexed subscript; every other use falls through to arithmetic.
    The remaining empty policies live at their consumer sites: the WRITE path
    rejects an empty ASSOCIATIVE key
    (executor/array.py#execute_array_element_assignment) and the ARITHMETIC
    path rejects an empty verbatim subscript
    (arithmetic/evaluator.py#_array_key) — both "bad array subscript".
    """
    READ = enum.auto()
    WRITE = enum.auto()
    IS_SET = enum.auto()
    UNSET = enum.auto()
    TEST_V = enum.auto()
    ARITH = enum.auto()
    DECLARE = enum.auto()


#: Uses whose EMPTY indexed subscript means "no target" (None), not index 0.
_EMPTY_IS_NO_TARGET = frozenset({SubscriptUse.TEST_V, SubscriptUse.UNSET})

#: Builtin-surface uses whose SubscriptSyntaxError is reported by the CALLER
#: (bash: `test -v` is quietly unset, `unset` says "not a valid identifier"),
#: so the keying funnel must not print for them. The same two uses as the
#: empty-is-no-target policy today, but a distinct policy — kept separate.
_QUIET_SYNTAX_USES = frozenset({SubscriptUse.TEST_V, SubscriptUse.UNSET})


def _procsub_segments(raw: str) -> 'Iterator[tuple[str, int, int]]':
    """Yield ``(kind, start, end)`` runs of ``raw``: ``'procsub'`` for each
    UNQUOTED ``<(``/``>(`` spelling (extent via the lexer's grammar-aware
    scanner; an unclosed frame runs to end-of-text), ``'text'`` between.
    Quoted spellings and ones inside ``$(...)``/``${...}``/backticks belong
    to their enclosing construct and stay in text runs."""
    i, n = 0, len(raw)
    seg_start = 0
    while i < n:
        nxt = skip_quoted_run(raw, i)
        if nxt is not None:
            i = nxt
            continue
        if raw[i] in '<>' and i + 1 < n and raw[i + 1] == '(':
            if seg_start < i:
                yield ('text', seg_start, i)
            end, found = find_command_substitution_end(raw, i + 2)
            yield ('procsub', i, end if found else n)
            i = end if found else n
            seg_start = i
            continue
        i += 1
    if seg_start < n:
        yield ('text', seg_start, n)


def _is_substitution_syntax_error(e: PshError) -> bool:
    """Whether ``e`` is the read-time substitution-body parse error class
    (checked by NAME through the deferred parser import — the class lives in
    the parser package, which this module must not import at module level)."""
    return any(c.__name__ == 'SubstitutionSyntaxError'
               for c in type(e).__mro__)


class SubscriptEvaluator:
    """One interpreter for array subscripts (indexed arithmetic / associative key).

    Lives on :class:`ExpansionManager` as ``shell.expansion_manager.subscript``.
    """

    def __init__(self, host: 'ExpansionHost') -> None:
        #: The expansion host. This took the whole ``Shell`` until remediation
        #: 5C.1: it forwards to ``evaluate_arithmetic``, and while THAT took a
        #: ``Shell`` this had to as well (the consumer ratchet's allowlist said
        #: exactly that). Typing the arithmetic signature retired the reason.
        self.host = host

    @property
    def state(self) -> "ShellState":
        return self.host.state

    @property
    def _manager(self) -> "ExpansionRuntime":
        """The expansion orchestrator, as the narrow ``ExpansionRuntime``.

        This boundary consumes exactly three of that protocol's members —
        ``expand_assignment_value_word`` (the associative-key engine) and
        ``variable_expander`` twice — so the narrow surface is the honest type
        here. Until remediation 5C.1 ``__init__`` still took the whole
        ``Shell`` for its ``evaluate_arithmetic`` forward, and the Q1 ratchet
        carried an allowlist entry saying so; typing that signature retired
        both the forward and the entry.
        """
        return self.host.expansion_manager

    # -- The re-lex bridge: raw subscript text -> one Word --------------------
    def word_from_text(self, raw: str) -> Word:
        """Re-lex raw subscript source into ONE Word for quote-aware expansion.

        The subscript is captured as raw source text by the parser (or arrives
        already argument-expanded from a builtin), so this rebuilds the per-part
        quote context the associative-key engine needs.

        **Procsub spellings are never parsed here** (round-3 B1; bash never
        parses a procsub body at keying time, and body VALIDITY is irrelevant
        to it): an unquoted ``<(...)``/``>(...)`` is split off structurally —
        frame chars become literal parts, the body text re-enters this bridge
        (so ``$``-forms inside expand, quotes remove, nested frames recurse;
        an unclosed frame keeps its raw tail). NO re-render happens here:
        bash renders spellings only on the SOURCE parse paths, which psh now
        mirrors at parse time (parser support ``rewrite_rendered_subscript``);
        runtime strings and arith-held subscripts stay raw (probe matrix
        B1R2-route-matrix.txt, three render tiers).

        The remaining text segments re-lex through the ordinary token
        pipeline. Two fidelity points: unquoted whitespace is preserved via
        source-span gap fill, and a lone double-quoted STRING expands with its
        ``token.quote_type``. An INVALID modern ``$(...)`` body becomes a
        DEFERRED executable part (the backtick model — execution re-parses at
        expansion time, so every keying route ATTEMPTS the substitution like
        bash). Un-lexable raw (an unclosed QUOTE — the class bash's builtins
        report as "not a valid identifier") raises the typed
        :class:`SubscriptSyntaxError`; anything else is an internal defect
        and propagates (strict-errors).
        """
        try:
            parts = self._raw_parts(raw)
        except SubscriptSyntaxError as e:
            # Rewrap so the carried text is the caller's FULL raw (a segment
            # or recursion may have raised with its local slice).
            if e.raw != raw:
                raise SubscriptSyntaxError(raw) from e
            raise
        return Word(parts=parts)

    def _raw_parts(self, raw: str) -> 'List[WordPart]':
        """Parts for ``raw``: procsub spellings split structurally, the rest
        through the token pipeline."""
        parts: 'List[WordPart]' = []
        for kind, start, end in _procsub_segments(raw):
            if kind == 'procsub':
                parts.append(LiteralPart(raw[start:start + 2], quoted=False,
                                         quote_char=None))
                closed = raw[end - 1] == ')' and end - 1 >= start + 2
                body_end = end - 1 if closed else end
                body = raw[start + 2:body_end]
                if body:
                    parts.extend(self._raw_parts(body))
                if closed:
                    parts.append(LiteralPart(')', quoted=False,
                                             quote_char=None))
            else:
                parts.extend(self._segment_parts(raw[start:end]))
        if not parts:
            parts.append(LiteralPart(raw, quoted=False, quote_char=None))
        return parts

    def _segment_parts(self, raw: str) -> 'List[WordPart]':
        """The token pipeline for a procsub-free segment of subscript text."""
        # cycle-break: expansion -> parser.word_builder would form a package
        # cycle (word_builder imports expansion.param_parser). Deferred import;
        # ratchet cap 1 in tests/unit/tooling/test_import_layering.py.
        from ..parser.recursive_descent.support.word_builder import WordBuilder
        try:
            tokens = [t for t in tokenize(raw) if t.type != TokenType.EOF]
        except PshError as e:
            raise SubscriptSyntaxError(raw) from e
        parts: 'List[WordPart]' = []
        pos = 0
        for token in tokens:
            start = getattr(token, 'position', pos) or 0
            if start > pos:
                parts.append(LiteralPart(raw[pos:start], quoted=False,
                                         quote_char=None))
            end = getattr(token, 'end_position', start) or start
            if token.type.name.startswith('REDIRECT'):
                # Redirect-family tokens don't round-trip through .value
                # (REDIRECT_OUT for `2>` carries value `>`, the fd only in
                # the span) — and in subscript TEXT a redirect operator is
                # literal key characters, so reproduce the exact source
                # slice (2.3 B2: `a[<(echo x 2> e)]` must keep the `2`).
                parts.append(LiteralPart(raw[start:end], quoted=False,
                                         quote_char=None))
                pos = end
                continue
            quote_type = (token.quote_type
                          if token.type == TokenType.STRING else None)
            try:
                word = WordBuilder.build_word_from_token(token, quote_type)
            except PshError as e:
                if _is_substitution_syntax_error(e):
                    # An INVALID modern $(...) body: bash ATTEMPTS the
                    # substitution at keying time (probe matrix, cmdsub
                    # rows) — defer it like a backtick; execution re-parses
                    # the source at expansion and errors THERE.
                    parts.extend(self._deferred_cmdsub_parts(raw[start:end]))
                    pos = end
                    continue
                # The unclosed-QUOTE class: bash's builtins treat the whole
                # argument as invalid (m12) — the typed user error.
                raise SubscriptSyntaxError(raw) from e
            parts.extend(word.parts)
            pos = end
        if pos < len(raw):
            parts.append(LiteralPart(raw[pos:], quoted=False, quote_char=None))
        return parts

    def _deferred_cmdsub_parts(self, text: str) -> 'List[WordPart]':
        """Parts for a token slice whose modern ``$(...)`` body failed its
        eager parse: each unquoted ``$(``-extent becomes a DEFERRED executable
        :class:`CommandSubstitution` (program=None — the execution path
        re-parses ``source``, exactly the backtick model); the gap segments
        re-enter the bridge for full fidelity."""
        parts: 'List[WordPart]' = []
        i, n = 0, len(text)
        seg_start = 0
        while i < n:
            # The $( check must run BEFORE the quoted-run skip: the skip
            # helper consumes $(...) extents wholesale, which would starve
            # this extraction and recurse the pipeline (round-3 trace).
            if text[i] == '$' and i + 1 < n and text[i + 1] == '(':
                if seg_start < i:
                    parts.extend(self._raw_parts(text[seg_start:i]))
                end, found = find_command_substitution_end(text, i + 2)
                body = text[i + 2:end - 1] if found else text[i + 2:]
                parts.append(ExpansionPart(
                    CommandSubstitution(program=None, source=body,
                                        backtick_style=False),
                    quoted=False, quote_char=None))
                i = end
                seg_start = end
                continue
            nxt = skip_quoted_run(text, i)
            if nxt is not None:
                i = nxt
                continue
            i += 1
        if seg_start < n:
            parts.extend(self._raw_parts(text[seg_start:n]))
        return parts

    # -- The two interpretations ---------------------------------------------
    def associative_key(self, raw: str, *, quiet: bool = False) -> str:
        """The literal string key of an associative-array subscript.

        One word/quote expansion under assignment-value semantics: composite
        quoting, ``$'...'`` decode, ``"$k"`` expansion, leading-tilde, unquoted
        spaces preserved, NO split/glob, and NO bare-name dereference.

        This is the SAME engine for every keying surface — the non-arithmetic
        ``h[$k]=v`` write path AND the arithmetic ``(( h[$k]=v ))`` path. The
        arithmetic pre-pass (``arithmetic/evaluator.py#_arith_preexpand``) holds
        the subscript RAW, so ``$k`` arrives here as an ExpansionPart: its value
        is inserted LITERALLY (never quote-removed, never rescanned for a nested
        ``$``), while source-spelled quotes/backslashes are removed — exactly
        bash's provenance rule (W2/CV1).

        Un-lexable raw raises :class:`SubscriptSyntaxError`. The message is
        printed here (location-prefixed, like the indexed twin
        ``_evaluate_expanded_index``) unless ``quiet`` — the BUILTIN surfaces
        (``unset``, ``test -v``: :class:`SubscriptUse` UNSET/TEST_V via
        :meth:`evaluate`) report in their own bash wording instead.
        """
        try:
            word = self.word_from_text(raw)
        except SubscriptSyntaxError as e:
            if not quiet:
                print(f"{self.state.error_location_prefix()}{e}",
                      file=self.state.stderr)
            raise
        return self._manager.expand_assignment_value_word(word)

    def raw_has_source_quote(self, raw: str) -> bool:
        """True if ``raw`` contains a source-spelled quoted part.

        The arithmetic empty-subscript policy uses this: an EMPTY associative
        key is bash's fatal ``NAME[]: bad array subscript`` when the emptiness
        came from substitution or literal-empty text (``h[$e]``, ``h[]``), but a
        source empty-quoted key (``h[""]``/``h['']``) is a valid empty key. Only
        re-lexes (no expansion runs), so the caller's one keying expansion is
        never doubled."""
        return any(isinstance(p, LiteralPart) and p.quoted
                   for p in self.word_from_text(raw).parts)

    def indexed_index(self, raw: str) -> int:
        """The integer index of an indexed-array (or scalar) subscript.

        Variables expand (``$i``/``${i}``); the result is arithmetic-evaluated,
        so a BARE name is a variable reference and recursion works
        (``i=j; j=2; a[i]`` -> 2) — the arithmetic evaluator dereferences bare
        names, so no separate bare-name fallback is needed. A subscript that
        fails to evaluate (``a[1//]``, ``a[08]``) is a fatal arithmetic error
        that discards the input (bash), not a silent index 0.
        """
        return self._evaluate_expanded_index(
            self._manager.variable_expander.expand_string_variables(raw))

    def _evaluate_expanded_index(self, expanded: str) -> int:
        """Arithmetic-evaluate an already-``$``-expanded indexed subscript."""
        try:
            return evaluate_arithmetic(expanded, self.host)
        except ArithmeticError as e:
            # Location-prefixed like every non-interactive runtime diagnostic
            # (v0.690 convention; bash: `bash: line 1: 08: value too great…`).
            print(f"{self.state.error_location_prefix()}{e}",
                  file=self.state.stderr)
            self.state.last_exit_code = 1
            arith_assignment_discard(self.state)

    def evaluate(self, raw: str, kind: TargetKind,
                 use: SubscriptUse = SubscriptUse.READ
                 ) -> Union[int, str, None]:
        """Interpret ``raw`` for a target of ``kind`` — the one dispatch point.

        Returns the string key (associative), the int index (indexed), or
        ``None`` when *use* is ``TEST_V``/``UNSET`` and the indexed subscript
        expands to EMPTY — bash's "no target" surfaces (silently-unset ``-v``,
        no-op ``unset``; see :class:`SubscriptUse`). The one shared expansion
        pass means a command substitution in the subscript runs exactly once.

        An un-lexable ASSOCIATIVE subscript raises
        :class:`SubscriptSyntaxError` — printed here for the shell's own
        keying surfaces, quiet for the builtin uses (``TEST_V``/``UNSET``),
        whose callers translate it (bash: ``test -v`` quietly unset,
        ``unset`` a loud "not a valid identifier").
        """
        if kind is TargetKind.ASSOCIATIVE:
            return self.associative_key(
                raw, quiet=use in _QUIET_SYNTAX_USES)
        expanded = self._manager.variable_expander.expand_string_variables(raw)
        if expanded == '' and use in _EMPTY_IS_NO_TARGET:
            return None
        return self._evaluate_expanded_index(expanded)
