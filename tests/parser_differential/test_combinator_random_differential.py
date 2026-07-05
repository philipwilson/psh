"""Randomized recursive-descent vs combinator differential (drift detector).

The two parsers are contracted to produce the same canonical AST for the same
input (and to agree on whether an input is a syntax error). The curated
:mod:`test_combinator_ast_parity` corpus pins that invariant for hand-picked
constructs; this module *fuzzes* it — generating many small shell snippets from
a grammar and asserting the two parsers stay locked together across all of them.

Both parser auditors (reappraisal #18) asked for this so that a future edit to
one parser that silently diverges from the other is caught by the nightly.

Design:

* **Bounded + fast by default** so it also rides the local gate: ``ITERS``
  snippets (default 150, ~0.3s). A shared per-snippet compound budget
  (:data:`MAX_COMPOUNDS`) caps nesting so every snippet stays small. The nightly
  cranks the iteration count up via ``PSH_DIFFERENTIAL_ITERS`` (see
  ``nightly.yml``).
* **Reproducible.** The RNG seed comes from ``PSH_DIFFERENTIAL_SEED`` (default
  0). Every failure message embeds the seed, the iteration index, and the
  offending snippet, and a standalone ``PSH_DIFFERENTIAL_SEED=<n>`` re-run with
  the same ITERS regenerates the exact sequence.
* **Equivalence.** For each snippet: parse with both parsers.
  - both succeed  -> ASTs must be equal after :func:`_normalize_wrappers`
    (which peels the one inert representational difference between the parsers:
    whether a lone compound is wrapped in a trivial ``AndOrList -> Pipeline``);
  - both raise    -> agree it is a syntax error (message drift is out of scope
    here — :mod:`test_combinator_error_parity` owns that);
  - one succeeds, the other raises -> a real divergence, fail loudly.

The grammar is deliberately restricted to the productions the two parsers are
known to agree on (see GRAMMAR NOTES below), so a failure means a genuine, NEW
drift rather than a re-discovery of a catalogued pre-existing gap.
"""

import os
import random

import pytest

# Sibling module in the same (non-package) test directory — pytest's default
# import mode prepends this directory to sys.path, so it imports by basename.
from test_combinator_ast_parity import (  # noqa: E402
    _canonical_ast,
    _parse_combinator,
    _parse_rd,
)

# ---------------------------------------------------------------------------
# Knobs (env-controlled so the nightly can widen coverage; see nightly.yml).
# ---------------------------------------------------------------------------
SEED = int(os.environ.get("PSH_DIFFERENTIAL_SEED", "0"))
ITERS = int(os.environ.get("PSH_DIFFERENTIAL_ITERS", "150"))
# Max compound (nesting) nodes per snippet. Compounds are the size multiplier,
# so a small shared budget keeps every snippet cheap to parse (a few hundred
# chars) — essential for riding the fast local gate. The nightly widens ITERS,
# not this: bigger snippets add parse cost without adding grammar coverage.
MAX_COMPOUNDS = int(os.environ.get("PSH_DIFFERENTIAL_MAX_COMPOUNDS", "4"))


# ---------------------------------------------------------------------------
# GRAMMAR NOTES — productions deliberately EXCLUDED, so the detector stays GREEN
# and any failure means a NEW drift. Two flavours: GENUINE divergences (a
# pre-existing RD-vs-combinator gap, each a candidate for a future parity
# cluster) and CONSERVATIVE simplifications (the parsers actually agree; the
# exclusion only costs some fuzzer coverage and masks nothing).
#   * CONSERVATIVE — a compound command as a non-leading PIPELINE stage
#     (`case ... esac | cmd`, `if ...; fi | cmd`, `foo | { ...; }`). The two
#     parsers AGREE on these (verified across if/while/until/case/brace/
#     subshell/[[/(( , leading and non-leading, `|` and `|&`). Excluded only to
#     keep pipeline stages uniformly simple-command-based; compounds still
#     appear as and-or operands / whole statements.
#   * GENUINE — a `time -p` prefix on a NON-BRACE compound (`time -p for ...`,
#     `time -p if ...`, `time -p while ...`, `time -p case ...`): RD wrongly
#     rejects it while the combinator and bash accept. Narrowly the `time -p`
#     case — plain `time` (no `-p`) on a compound, `time -p { ...; }`, and `!`
#     on any compound all AGREE. Prefixes are applied only to simple pipelines.
#   * GENUINE — a composite (adjacent-token) word as a `case` SUBJECT
#     (`case a"b"c in`): the combinator errors "Expected 'in'". And an EXPANSION
#     in a `for`-item list or `case` subject (`${y}`): RD strips `${...}`->`$...`
#     in the legacy `items`/`expr` string fields while the combinator keeps the
#     braces. See _ITEM_WORDS / _CASE_SUBJECTS.
#   * GENUINE — bare `]` / `}` / `[` as a *command name*: the combinator's
#     word_like omits RBRACKET/RBRACE (a separate pre-existing WORD_LIKE gap).
#   * GENUINE — repeated / interleaved `!` and `time` prefixes: the combinator
#     rejects `! time cmd` and `time time cmd` (RD accepts both) — a documented
#     combinator gap (pipelines.py comment). (`time ! cmd` and `! ! cmd` AGREE.)
# Mid-pipeline `time` (`cmd | time cmd2`), C-for empty sections, and
# bash-permissive function names — the three things T2-H fixed — ARE generated.
# ---------------------------------------------------------------------------

_COMMAND_NAMES = ['echo', 'true', 'false', ':', 'printf', 'cat', 'ls',
                  'cmd', 'foo', 'grep', 'wc']
_PLAIN_WORDS = ['a', 'b', 'c', 'x', 'y', 'arg', 'foo', 'bar', 'baz',
                '1', '42', 'file.txt', '-l', '-n', '--flag']
_QUOTED_WORDS = ['"a b"', "'lit $x'", '"$var"', 'a"b"c', "pre'mid'post"]
_EXPANSIONS = ['$x', '${y}', '${z:-d}', '${#w}', '$(echo z)', '`pwd`',
               '$((1 + 2))', 'a${x}b']
_REDIRECTS = ['> out', '>> out', '< in', '2> err', '2>&1', '&> both',
              '>&2', '<> rw', '2>&-']
_ASSIGNS = ['V=val', 'A=1', 'B=$x', 'C="a b"']
_FUNC_NAMES = ['f', 'my_fn', 'my-func', 'a.b', '9', 'func1', 'a+b']
_CASE_PATTERNS = ['a', 'b|c', '*', 'x*', '"a b"', '[0-9]']
# `for`-list items and `case` subjects: expansions are EXCLUDED here because
# RD normalizes `${y}` -> `$y` in the legacy `items`/`expr` string fields while
# the combinator preserves the braces — a pre-existing representational
# divergence (out of scope for T2-H). A composite (adjacent-token) word also
# breaks the combinator's `case` subject parser, so subjects stay single-token.
_ITEM_WORDS = ['a', 'b', 'c', 'x', 'y', 'arg', 'foo', 'bar', '1', '42',
               'file.txt', '-l', '"a b"', "'lit'", 'a"b"c']
_CASE_SUBJECTS = ['a', 'b', 'x', 'y', 'arg', 'foo', 'file.txt', '42', '-l',
                  '"a b"', "'lit'"]
_AND_OR_OPS = ['&&', '||']
_PIPE_OPS = ['|', '|&']


class SnippetGenerator:
    """Generate random shell snippets over a parity-safe grammar.

    Size is bounded by a per-snippet *compound budget* (``self._compounds``):
    compounds are the only production that multiplies size, so capping their
    total count keeps every snippet small and cheap to parse regardless of how
    the coin flips land. Once the budget is spent, every pipeline element is a
    simple command, which terminates the recursion.
    """

    def __init__(self, rng: random.Random):
        self.rng = rng
        self._compounds = 0  # remaining compound budget for the current snippet

    def _choice(self, seq):
        return self.rng.choice(seq)

    def _maybe(self, p: float) -> bool:
        return self.rng.random() < p

    def word(self) -> str:
        bucket = self._choice(
            [_PLAIN_WORDS, _PLAIN_WORDS, _QUOTED_WORDS, _EXPANSIONS])
        return self._choice(bucket)

    def simple_command(self) -> str:
        parts = []
        # Optional prefix assignments.
        if self._maybe(0.15):
            for _ in range(self.rng.randint(1, 2)):
                parts.append(self._choice(_ASSIGNS))
        parts.append(self._choice(_COMMAND_NAMES))
        for _ in range(self.rng.randint(0, 3)):
            parts.append(self.word())
        # Optional trailing redirection(s).
        for _ in range(self.rng.randint(0, 2)):
            if self._maybe(0.4):
                parts.append(self._choice(_REDIRECTS))
        return ' '.join(parts)

    def pipeline(self) -> str:
        """A pipeline of SIMPLE commands, with an optional leading prefix.

        Compounds are deliberately NOT generated as pipeline stages: a compound
        as a non-leading stage (``case ... esac | cmd``) and a ``time``/``!``
        prefix on a compound (``time -p for ...``) are pre-existing RD-vs-
        combinator divergences (out of scope for T2-H). Keeping them out of the
        grammar keeps the detector honest — a failure means a NEW drift.
        """
        stages = [self.simple_command()]
        for _ in range(self.rng.randint(0, 1)):
            stages.append(self._choice(_PIPE_OPS))
            stage = self.simple_command()
            # Mid-pipeline `time`/`time -p`: NOT the reserved word there (bash
            # runs the external time), so it is an ordinary command word. This
            # exercises the T2-H fix that demotes a non-leading TIME token.
            r = self.rng.random()
            if r < 0.06:
                stage = 'time ' + stage
            elif r < 0.09:
                stage = 'time -p ' + stage
            stages.append(stage)
        pipe = ' '.join(stages)
        # Leading `time [-p]` / single `!` prefix (never combined, never
        # repeated — those are documented parity gaps).
        r = self.rng.random()
        if r < 0.08:
            pipe = 'time ' + pipe
        elif r < 0.12:
            pipe = 'time -p ' + pipe
        elif r < 0.18:
            pipe = '! ' + pipe
        return pipe

    def operand(self) -> str:
        """An and-or operand: usually a pipeline, sometimes a compound.

        A compound is only emitted while the shared budget allows it (and then
        spends one unit), so total nesting per snippet is capped. Compounds
        appear here (as whole and-or operands / statements), not as pipeline
        stages — see :meth:`pipeline`.
        """
        if self._compounds > 0 and self._maybe(0.5):
            self._compounds -= 1
            return self.compound()
        return self.pipeline()

    def and_or(self) -> str:
        parts = [self.operand()]
        for _ in range(self.rng.randint(0, 1)):
            parts.append(self._choice(_AND_OR_OPS))
            parts.append(self.operand())
        return ' '.join(parts)

    def seq(self) -> str:
        """A `;`-joined run of 1-2 and-or lists, with NO trailing separator.

        Inline backgrounding (`&`) is deliberately not generated inside a
        sequence: `&` is itself a list separator, so `cmd & ; next` is a bash
        syntax error, and the two parsers need not be probed on ill-separated
        input. Backgrounding parity is covered by the curated corpus and by the
        top-level `&` in :meth:`program`.
        """
        n = self.rng.randint(1, 2)
        return '; '.join(self.and_or() for _ in range(n))

    def _kw_list(self) -> str:
        """A sequence guaranteed to end in a `;` — for the position right
        before a reserved word (`do`/`then`/`done`/`fi`/`elif`/`else`).

        bash requires a separator there: `while cond do ...` reads `do` as an
        argument of the last command, not the keyword (a syntax error). Always
        emitting the `;` keeps generated snippets well-formed so a divergence
        means a genuine parser drift, not a grammar bug.
        """
        return self.seq() + '; '

    def compound(self) -> str:
        kind = self._choice([
            'if', 'while', 'until', 'for_in', 'for_c', 'case',
            'subshell', 'brace', 'function',
        ])
        return getattr(self, f'_c_{kind}')()

    def _c_if(self) -> str:
        out = f'if {self._kw_list()}then {self._kw_list()}'
        for _ in range(self.rng.randint(0, 1)):
            out += f'elif {self._kw_list()}then {self._kw_list()}'
        if self._maybe(0.5):
            out += f'else {self._kw_list()}'
        return out + 'fi'

    def _c_while(self) -> str:
        return f'while {self._kw_list()}do {self._kw_list()}done'

    def _c_until(self) -> str:
        return f'until {self._kw_list()}do {self._kw_list()}done'

    def _c_for_in(self) -> str:
        var = self._choice(['i', 'x', 'item', 'f'])
        items = ' '.join(self._choice(_ITEM_WORDS)
                         for _ in range(self.rng.randint(0, 3)))
        head = f'for {var}'
        if items or self._maybe(0.5):
            head += f' in {items}'
        return f'{head}; do {self._kw_list()}done'

    def _c_for_c(self) -> str:
        # Each of the three sections is independently present or empty, to
        # exercise the DOUBLE_SEMICOLON / mandatory-second-`;` handling.
        init = self._choice(['i=0', 'i=1', 'i=(0)', ''])
        cond = self._choice(['i<3', 'i<=n', '(i<3)', ''])
        upd = self._choice(['i++', 'i+=1', '(i++)', ''])
        header = f'(({init}; {cond}; {upd}))'
        return f'for {header}; do {self._kw_list()}done'

    def _c_case(self) -> str:
        # A `;;` terminates each arm, so the arm body needs no trailing `;`
        # (and must not have one — `cmd; ;;` is a syntax error).
        subject = self._choice(_CASE_SUBJECTS)
        arms = []
        for _ in range(self.rng.randint(1, 3)):
            pat = self._choice(_CASE_PATTERNS)
            arms.append(f'{pat}) {self.seq()} ;;')
        return f'case {subject} in {" ".join(arms)} esac'

    def _c_subshell(self) -> str:
        return f'( {self.seq()} )'

    def _c_brace(self) -> str:
        # A brace group requires a separator before `}` (bash), so terminate.
        return f'{{ {self.seq()}; }}'

    def _c_function(self) -> str:
        name = self._choice(_FUNC_NAMES)
        body = f'{{ {self.seq()}; }}'
        if self._maybe(0.5):
            return f'{name}() {body}'
        # `function` keyword form (name-only, no parens).
        kw_name = self._choice(['f', 'my_fn', 'g'])
        return f'function {kw_name} {body}'

    def program(self) -> str:
        self._compounds = self.rng.randint(0, MAX_COMPOUNDS)
        prog = self.seq()
        # Optional top-level backgrounding (safe: nothing follows it) or a
        # trailing separator.
        tail = self.rng.random()
        if tail < 0.08:
            prog += ' &'
        elif tail < 0.4:
            prog += ';'
        return prog


def _normalize_wrappers(node):
    """Strip semantically-inert single-element Pipeline/AndOrList wrappers.

    The two parsers disagree on ONE thing that this fuzzer would otherwise trip
    on constantly: whether a lone compound command is wrapped in a trivial
    ``AndOrList -> Pipeline`` when it sits in a list or as an and-or operand.
    RD inserts the wrapper; the combinator returns the bare compound. Both mean
    exactly the same thing (a one-command pipeline / one-pipeline and-or list is
    executionally identical to its single element), so we canonicalize both
    sides by peeling those inert wrappers. Wrappers that carry meaning —
    negation, ``time``, ``|&`` stderr, ``&&``/``||`` operators, or backgrounding
    — are left intact, so a genuine structural difference is still caught.
    """
    if isinstance(node, list):
        return [_normalize_wrappers(x) for x in node]
    if isinstance(node, tuple):
        # e.g. IfConditional.elif_parts is a list of (condition, then) tuples;
        # recurse so wrappers inside an elif condition are peeled too.
        return tuple(_normalize_wrappers(x) for x in node)
    if not isinstance(node, dict):
        return node
    node = {k: _normalize_wrappers(v) for k, v in node.items()}
    t = node.get('type')
    if t == 'Pipeline':
        if (len(node.get('commands') or []) == 1
                and not node.get('negated')
                and not node.get('timed')
                and not node.get('time_posix')
                and not node.get('pipe_stderr')):
            return node['commands'][0]
    elif t == 'AndOrList':
        if (len(node.get('pipelines') or []) == 1
                and not node.get('operators')
                and not node.get('background')):
            return node['pipelines'][0]
    return node


def _outcome(parse_fn, source):
    """Return ('ok', normalized_ast) or ('err', exc) for one parser."""
    try:
        return 'ok', _normalize_wrappers(_canonical_ast(parse_fn(source)))
    except Exception as exc:  # noqa: BLE001 — classify, don't crash the fuzzer
        return 'err', exc


def _generate_snippets(seed: int, count: int):
    rng = random.Random(seed)
    gen = SnippetGenerator(rng)
    return [gen.program() for _ in range(count)]


@pytest.mark.parser_differential
def test_random_rd_vs_combinator_parity():
    """Fuzz RD-vs-combinator AST/parse-outcome parity over ITERS snippets."""
    snippets = _generate_snippets(SEED, ITERS)
    for i, source in enumerate(snippets):
        rd_kind, rd_val = _outcome(_parse_rd, source)
        cb_kind, cb_val = _outcome(_parse_combinator, source)

        base = (f"\nDIVERGENCE (seed={SEED}, iters={ITERS}, index={i})\n"
                f"  reproduce: PSH_DIFFERENTIAL_SEED={SEED} "
                f"PSH_DIFFERENTIAL_ITERS={ITERS} pytest "
                f"tests/parser_differential/"
                f"test_combinator_random_differential.py\n"
                f"  snippet: {source!r}\n")

        # Outcome category must match (both accept or both reject).
        assert rd_kind == cb_kind, (
            base
            + f"  rd  : {rd_kind}"
            + (f" ({type(rd_val).__name__}: {rd_val})" if rd_kind == 'err' else "")
            + f"\n  comb: {cb_kind}"
            + (f" ({type(cb_val).__name__}: {cb_val})" if cb_kind == 'err' else "")
        )

        # On mutual success the canonical ASTs must be identical.
        if rd_kind == 'ok':
            assert rd_val == cb_val, base + "  ASTs differ (see canonical dump)"


def test_generator_is_deterministic():
    """Same seed -> same snippet sequence (so failures reproduce)."""
    assert _generate_snippets(0, 20) == _generate_snippets(0, 20)
    assert _generate_snippets(1, 20) != _generate_snippets(0, 20)
