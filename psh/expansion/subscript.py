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
from typing import TYPE_CHECKING, Union

from ..ast_nodes.words import LiteralPart, Word
from ..core import arith_assignment_discard
from ..lexer import tokenize
from ..lexer.token_types import TokenType

if TYPE_CHECKING:
    from ..shell import Shell


class TargetKind(enum.Enum):
    """Whether a subscript addresses an indexed (arithmetic) or associative
    (string-key) target. Decided by the caller from the DECLARED variable."""
    INDEXED = enum.auto()
    ASSOCIATIVE = enum.auto()


class SubscriptUse(enum.Enum):
    """Which surface is keying — used only for diagnostics and the empty-key
    policy (write/read/is-set reject an empty subscript; test/unset tolerate)."""
    READ = enum.auto()
    WRITE = enum.auto()
    IS_SET = enum.auto()
    UNSET = enum.auto()
    TEST_V = enum.auto()
    ARITH = enum.auto()
    DECLARE = enum.auto()


class SubscriptEvaluator:
    """One interpreter for array subscripts (indexed arithmetic / associative key).

    Lives on :class:`ExpansionManager` as ``shell.expansion_manager.subscript``.
    """

    def __init__(self, shell: 'Shell'):
        self.shell = shell

    @property
    def state(self):
        return self.shell.state

    @property
    def _manager(self):
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

        On any tokenization failure the raw text is returned as one unquoted
        literal part (robust degradation; strict-errors never sees a stray
        Python exception from re-lexing an already-parsed subscript).
        """
        # cycle-break: expansion -> parser.word_builder would form a package
        # cycle (word_builder imports expansion.param_parser). Deferred import;
        # ratchet cap 1 in tests/unit/tooling/test_import_layering.py.
        from ..parser.recursive_descent.support.word_builder import WordBuilder
        try:
            tokens = [t for t in tokenize(raw) if t.type != TokenType.EOF]
        except Exception:
            return Word(parts=[LiteralPart(raw, quoted=False, quote_char=None)])
        if not tokens:
            return Word(parts=[LiteralPart(raw, quoted=False, quote_char=None)])
        parts = []
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
            except Exception:
                word = Word(parts=[LiteralPart(getattr(token, 'value', ''),
                                               quoted=False, quote_char=None)])
            parts.extend(word.parts)
            pos = getattr(token, 'end_position', start) or start
        if pos < len(raw):
            parts.append(LiteralPart(raw[pos:], quoted=False, quote_char=None))
        return Word(parts=parts)

    # -- The two interpretations ---------------------------------------------
    def associative_key(self, raw: str) -> str:
        """The literal string key of an associative-array subscript.

        One word/quote expansion under assignment-value semantics: composite
        quoting, ``$'...'`` decode, ``"$k"`` expansion, leading-tilde, unquoted
        spaces preserved, NO split/glob, and NO bare-name dereference.
        """
        return self._manager.expand_assignment_value_word(self.word_from_text(raw))

    def indexed_index(self, raw: str) -> int:
        """The integer index of an indexed-array (or scalar) subscript.

        Variables expand (``$i``/``${i}``); the result is arithmetic-evaluated,
        so a BARE name is a variable reference and recursion works
        (``i=j; j=2; a[i]`` -> 2) — the arithmetic evaluator dereferences bare
        names, so no separate bare-name fallback is needed. A subscript that
        fails to evaluate (``a[1//]``, ``a[08]``) is a fatal arithmetic error
        that discards the input (bash), not a silent index 0.
        """
        from .arithmetic import ArithmeticError, evaluate_arithmetic
        expanded = self._manager.variable_expander.expand_string_variables(raw)
        try:
            return evaluate_arithmetic(expanded, self.shell)
        except ArithmeticError as e:
            print(f"psh: {e}", file=self.state.stderr)
            self.state.last_exit_code = 1
            arith_assignment_discard(self.state)

    def evaluate(self, raw: str, kind: TargetKind,
                 use: SubscriptUse = SubscriptUse.READ) -> Union[int, str]:
        """Interpret ``raw`` for a target of ``kind`` — the one dispatch point."""
        if kind is TargetKind.ASSOCIATIVE:
            return self.associative_key(raw)
        return self.indexed_index(raw)
