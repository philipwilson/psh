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
from typing import TYPE_CHECKING, List, Union

from ..ast_nodes.words import ExpansionPart, LiteralPart, ProcessSubstitution, Word, WordPart
from ..core import arith_assignment_discard
from ..core.exceptions import ExpansionError, PshError
from ..lexer import tokenize
from ..lexer.token_types import TokenType
from .arithmetic import ArithmeticError, evaluate_arithmetic

if TYPE_CHECKING:
    from ..core.state import ShellState
    from ..shell import Shell
    from .manager import ExpansionManager


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


class SubscriptEvaluator:
    """One interpreter for array subscripts (indexed arithmetic / associative key).

    Lives on :class:`ExpansionManager` as ``shell.expansion_manager.subscript``.
    """

    def __init__(self, shell: 'Shell'):
        self.shell = shell

    @property
    def state(self) -> "ShellState":
        return self.shell.state

    @property
    def _manager(self) -> "ExpansionManager":
        return self.shell.expansion_manager

    # -- The re-lex bridge: raw subscript text -> one Word --------------------
    def word_from_text(self, raw: str) -> Word:
        """Re-lex raw subscript source into ONE Word for quote-aware expansion.

        The subscript is captured as raw source text by the parser (or arrives
        already argument-expanded from a builtin), so this rebuilds the per-part
        quote context the associative-key engine needs. Two fidelity points make
        it faithful to the parser's own word building:

        - **Unquoted whitespace is preserved.** Re-tokenizing ``a b`` yields two
          WORD tokens; an associative key keeps the literal space (bash does not
          word-split a subscript). The gap between consecutive tokens' source
          spans is re-inserted as an unquoted literal run, which the no-split
          associative policy never breaks.
        - **A lone double-quoted STRING expands.** ``"$k"`` tokenizes to one
          STRING token whose expansion parts need ``token.quote_type`` to
          decompose — passed exactly as :meth:`parse_argument_as_word` does.

        A process-substitution SPELLING never becomes an executable
        expansion — its frame turns literal while its body keeps expanding
        (:meth:`_literalize_procsub_frames`): ``a[<(printf x)]=v`` keys
        ``<(printf x)`` and never launches anything, while ``a[<(cat $y)]``
        keys ``<(cat Q)`` when ``y=Q`` (HIGH-4, bash). Command substitutions
        and backticks DO stay executable (bash runs them in an associative
        key).

        Un-lexable raw raises :class:`SubscriptSyntaxError` — the typed
        variant of the former broad-``except`` literal degradation (only the
        lexer/word-builder's own PshError failures translate; anything else
        is an internal defect and propagates).
        """
        # cycle-break: expansion -> parser.word_builder would form a package
        # cycle (word_builder imports expansion.param_parser). Deferred import;
        # ratchet cap 1 in tests/unit/tooling/test_import_layering.py.
        from ..parser.recursive_descent.support.word_builder import WordBuilder
        try:
            tokens = [t for t in tokenize(raw) if t.type != TokenType.EOF]
        except PshError as e:
            raise SubscriptSyntaxError(raw) from e
        if not tokens:
            return Word(parts=[LiteralPart(raw, quoted=False, quote_char=None)])
        parts: 'list[WordPart]' = []
        pos = 0
        for token in tokens:
            start = getattr(token, 'position', pos) or 0
            if start > pos:
                parts.append(LiteralPart(raw[pos:start], quoted=False,
                                         quote_char=None))
            quote_type = (token.quote_type
                          if token.type == TokenType.STRING else None)
            try:
                word = WordBuilder.build_word_from_token(token, quote_type)
            except PshError as e:
                # An unclosed substitution spelling (``$(``, ``<(``) fails the
                # builder's own nested validation — same typed user error.
                raise SubscriptSyntaxError(raw) from e
            parts.extend(self._literalize_procsub_frames(word.parts))
            pos = getattr(token, 'end_position', start) or start
        if pos < len(raw):
            parts.append(LiteralPart(raw[pos:], quoted=False, quote_char=None))
        return Word(parts=parts)

    def _literalize_procsub_frames(
            self, parts: 'List[WordPart]') -> 'List[WordPart]':
        """Keep procsub FRAMES literal while their bodies expand normally.

        The subscript-keying identity rule (HIGH-4, bash 5.2 probe-verified):
        an unquoted ``<(...)`` / ``>(...)`` in a subscript never RUNS (no
        /dev/fd path, no side effects) — the spelling is key text — but the
        BODY still undergoes the one keying expansion like any other word
        text: ``a[<(cat $y)]`` with ``y=Q`` keys ``<(cat Q)``, ``$()`` inside
        the body executes, quotes remove, and a NESTED frame stays literal
        (``<(a <(b))`` keys itself). So the direction char and parens become
        unquoted literal parts and the body re-enters the re-lex bridge
        (recursion literalizes nested frames the same way). Quoted spellings
        never re-lex to procsub parts, so this touches exactly the unquoted
        case."""
        out: 'List[WordPart]' = []
        for p in parts:
            if (isinstance(p, ExpansionPart)
                    and isinstance(p.expansion, ProcessSubstitution)):
                ps = p.expansion
                frame = '<' if ps.direction == 'in' else '>'
                out.append(LiteralPart(frame + '(', quoted=False,
                                       quote_char=None))
                out.extend(self.word_from_text(ps.source).parts)
                out.append(LiteralPart(')', quoted=False, quote_char=None))
            else:
                out.append(p)
        return out

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
            return evaluate_arithmetic(expanded, self.shell)
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
