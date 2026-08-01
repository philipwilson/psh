"""The state-aware analysis session (`--validate`/`--format`/... ).

Analysis used to parse the WHOLE input in one call under the option state the
shell was CONSTRUCTED with, while execution parses one unit at a time under
state that EVOLVES as earlier units run. So a script that enables a lexing
option on line 1 and uses it on line 2 executed fine and failed `--validate`
(remediation MEDIUM-9(a); reappraisal #22).

This session removes the difference at its source: it walks the SAME unit
boundaries execution walks — literally the same generator,
``source_processor.iter_command_units`` — parses each unit under the state
established by the units before it, and executes NOTHING. The per-unit
``Program``s are merged into one ``Program`` so each analysis visitor still
runs exactly once over the whole input, as it always did.

STATE CARRIER. The evolving state lives in a CHILD ``Shell`` (constructed with
``parent_shell=``, which copies options, aliases and functions). That is what
lets the rest of the pipeline stay untouched: ``lex_and_parse``,
``CommandAccumulator`` and ``parse_tokens`` already read exactly
``state.options``, ``alias_manager`` and ``active_parser`` off a shell, so
threading state costs no new parameter on any seam execution also traverses.
Shell construction is process-pure (campaign F2), so building one analyzes
nothing and changes no process state.

WHICH TRANSITIONS APPLY (integrator-ruled — remediation 2.6 R1-F, amended
R8-B). Analysis cannot evaluate control flow, so it cannot know whether a
directive is REACHED. STRUCTURE therefore decides where a directive counts,
and the OPTION decides how its value is combined.

Structure, the same for every option:

* directives inside a STATE-ISOLATED region (a subshell, a member of a
  multi-command pipeline, a backgrounded command, a command or process
  substitution) are ignored, because execution discards their effects too;
* directives inside a FUNCTION BODY do apply — a defined function is usually
  called, and execution's answer for the common case is "live";
* a directive is recognized through the prefixes that do not change which
  builtin runs (assignment prefixes, backslash quoting, ``builtin`` /
  ``command``) and through clustered flags — see :func:`_option_changes`.

Value, PER OPTION, because the options do not share semantics:

* ``extglob`` / ``posix`` are MONOTONE — only enables apply. Narrowing on an
  unreached disable would re-invent the false syntax errors this session
  exists to remove.
* ``expand_aliases`` is ORDERED — last write wins, enables and disables both,
  because that is what execution measurably does (a script that unsets it
  stops expanding aliases in later units, = bash). Modelling it as monotone
  would model a shell nobody runs.

Consequences, measured against execution and DECLARED rather than hidden. Over
the 29-row structural corpus that scored the rule (extglob as the detector):
exact on 19 rows, PERMISSIVE on 8 (an unreached directive is treated as live,
so analysis parses a superset — it can miss a syntax error, never invent one),
and blind on 2, a directive inside an ``eval`` STRING or a ``source``d FILE,
which no non-executing analysis can see. Those counts describe the MONOTONE
options; ``expand_aliases`` adds one more declared cost of its own — an
unreached conditional DISABLE narrows analysis, the only place the option axis
can still produce a false syntax error. A directive is also read WITHOUT
command resolution, so a ``shopt`` shadowed by a shell function of the same
name is absorbed anyway — analysis accepts more than the shell does there.
All are pinned as divergences (R1-C, R8-B, R11-B N12).

COST. Parsing per unit is slower than one whole-file parse, because each unit
pays its own lex and parse setup: **~3.3x** on a 4,000-line script (median
0.21s -> 0.69s over 5 runs after a discarded warm-up, on one development
host). It is a magnitude, not a benchmark — a second host measured 2.2x on
the same shape. Analysis modes are one-shot CLI tools, not an inner loop, so
this is recorded rather than optimized; a successor may revisit it.

RELATIONSHIP TO ``bash -n`` (R1-E). ``bash -n`` does not execute ``shopt``
either, so it reports the same false syntax error, and psh's own ``-n``
(``noexec``) is state-blind for the same reason. psh keeps ``-n`` pinned to
bash and makes ``--validate`` state-aware: they answer different questions —
"what does bash's syntax check say?" versus "would this script parse as it
runs?". The divergence from ``bash -n`` is deliberate and pinned.
"""
import re
from typing import TYPE_CHECKING, Any, List, Optional, Sequence, Tuple

from ..ast_nodes import Program
from ..ast_nodes.commands import SimpleCommand
from ..ast_nodes.words import LiteralPart
from ..core.option_registry import OPTION_REGISTRY
from ..invocation import resolve_parser_name
from ..lexer.token_types import TokenType
from ..visitor.traversal import walk_ast
from .input_preprocessing import process_line_continuations
from .lex_parse import lex_and_expand, parse_tokens
from .program_source import ProgramSource
from .source_processor import iter_command_units, offset_line_numbers

if TYPE_CHECKING:
    from ..shell import Shell

#: Option names the lex→parse pipeline consults, threaded from unit to unit.
#: The set is DERIVED, not curated: ``test_analysis_session.py`` traces the
#: option mapping through a real ``lex_and_parse`` and fails if this tuple and
#: the pipeline disagree in either direction. It has to be derived from the
#: PIPELINE rather than from a list of packages — an earlier version scanned
#: psh/lexer and psh/parser only, which structurally could not see
#: ``expand_aliases`` (read by ``Shell.expand_aliases``, a third consumer),
#: and so certified a set that was missing one of its own census's findings.
PARSE_RELEVANT_OPTIONS: Tuple[str, ...] = ('extglob', 'posix', 'expand_aliases')

#: MONOTONE options: only ENABLES are applied to later units. Analysis cannot
#: know whether a directive is reached, and narrowing on an unreached disable
#: would re-invent the false syntax errors this session exists to remove.
MONOTONE_OPTIONS: Tuple[str, ...] = ('extglob', 'posix')

#: ORDERED options: last write wins, enables AND disables. ``expand_aliases``
#: is here because its measured execution semantics are not monotone — a
#: script that unsets it genuinely stops expanding aliases in later units
#: (psh execution: `alias q=...` then `shopt -u expand_aliases` then `q` is
#: command-not-found, = bash), so analysis that kept expanding would be
#: modelling a shell nobody runs. The cost is declared: an unreached
#: conditional disable narrows analysis, the one place the option axis can
#: still produce a false syntax error. Pinned in the analysis-session tests.
ORDERED_OPTIONS: Tuple[str, ...] = ('expand_aliases',)

#: Words that PREFIX a command without changing which builtin runs.
_TRANSPARENT_HEADS = ('builtin', 'command')

#: A leading `NAME=value` word (a temporary-environment assignment prefix).
_ASSIGNMENT_WORD = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*=')

#: A backslash escape in an UNQUOTED literal part: the backslash is quoting and
#: the character after it is the text. Applied ONLY where the lexer says the
#: part was unquoted (see :func:`_effective_words`) — inside quotes a backslash
#: is ordinary text and this must not touch it.
_UNQUOTED_ESCAPE = re.compile(r'\\(.)', re.DOTALL)

#: Debug options, DERIVED from the registry so a new `debug-*` joins by itself.
#: The carrier is built with all of them OFF: analysis EXECUTES NOTHING, so an
#: execution trace emitted from an analysis run describes work that never
#: happened. Inheriting them also leaked a construction-time line — a child
#: state re-detects the terminal and reports it under `debug-exec` — onto the
#: stderr of `--debug-exec --validate`, which is not an execution at all.
DEBUG_OPTIONS: Tuple[str, ...] = tuple(
    sorted(name for name in OPTION_REGISTRY if name.startswith('debug')))

#: Flag letters `shopt` accepts (bash's internal_getopt over "psuoq", mirrored
#: by the builtin). A letter outside this set aborts the builtin with rc 2
#: BEFORE it applies anything, so such a command changes no state at all.
_SHOPT_FLAG_LETTERS = 'psuoq'

#: Which option TABLE a `shopt` command's operands name. Without `-o` it is the
#: shopt table; with `-o` it is the set-o table, and for the options this
#: session threads the two are DISJOINT: `shopt -s posix` is refused with
#: "invalid shell option name" while `shopt -so posix` sets it, and
#: `shopt -so extglob` is refused while `shopt -s extglob` sets it (measured in
#: psh and bash 5.2.26). A recognizer reading the flags but not the table would
#: invent both of those state changes. These cover the `shopt` spellings only:
#: psh's `set -o` accepts all three names as a documented superset over bash.
#: DERIVED, not curated — ``test_analysis_session.py`` checks both tuples
#: against the builtin's own _SHOPT_NAMES / _SET_O_NAMES in both directions.
SHOPT_TABLE_OPTIONS: Tuple[str, ...] = ('extglob', 'expand_aliases')
SET_O_TABLE_OPTIONS: Tuple[str, ...] = ('posix',)

#: Node types whose interior runs with its own copy of the shell state, so an
#: option change inside them dies with them. Totality (every ``CompoundCommand``
#: subclass classified either here or as state-preserving) is guarded by
#: ``test_analysis_session.py`` so a NEW compound shape cannot join the AST
#: unclassified.
ISOLATING_NODES = ('SubshellGroup', 'CommandSubstitution', 'ProcessSubstitution')


def _effective_words(command: Any) -> List[Optional[str]]:
    """Each word of *command* as the SHELL would see it — one entry per word.

    THE LEXER OWNS QUOTING, so this reads its answer instead of re-deriving
    one. Every ``LiteralPart`` carries ``quoted``/``quote_char`` (the v0.120
    Word/TokenPart invariant), and that single fact decides what a backslash
    means: in an UNQUOTED part ``\\x`` is quoting and yields ``x``; in a QUOTED
    part the backslash is ordinary text the shell keeps. So ``sh\\opt`` IS the
    ``shopt`` builtin while ``'sh\\opt'`` is a command of that literal name —
    measured identical in psh and bash 5.2.26 over eleven head spellings.

    An entry is ``None`` when the word contains an EXPANSION: its value is not
    statically knowable, so it can never match a directive name. Returning
    ``None`` rather than a best-effort rendering is the point — guessing here
    is how the previous version invented directives the shell never runs.
    """
    effective: List[Optional[str]] = []
    for word in getattr(command, 'words', ()) or ():
        pieces: List[str] = []
        known = True
        for part in word.parts:
            if not isinstance(part, LiteralPart):
                known = False
                break
            pieces.append(part.text if part.quoted
                          else _UNQUOTED_ESCAPE.sub(r'\1', part.text))
        effective.append(''.join(pieces) if known else None)
    return effective


def _normalize_head(words: Sequence[Optional[str]]) -> List[Optional[str]]:
    """Strip the prefixes that change WHO runs a command but not WHICH builtin.

    `x=1 command sh\\opt -s extglob` runs the same `shopt` the bare spelling
    does, and execution applies its option either way — so an analysis that
    only recognized the bare head silently missed six live spellings while
    claiming to find "every option ENABLE in a parsed unit". Handles leading
    `NAME=value` assignment words and any run of `builtin`/`command` prefixes.

    Backslash quoting is deliberately NOT handled here: it was already
    resolved by :func:`_effective_words` from the lexer's per-part quote
    context, which is the only place the distinction is known.
    """
    remaining = list(words)
    while (remaining and remaining[0] is not None
           and _ASSIGNMENT_WORD.match(remaining[0])):
        remaining.pop(0)
    while len(remaining) > 1 and remaining[0] in _TRANSPARENT_HEADS:
        transparent = remaining.pop(0)
        # `command -p` still runs the command (with a default PATH), so it is
        # transparent and repeatable. `command -v`/`-V` are NOT: they PRINT a
        # description and run nothing, so a head behind them is not a
        # directive and must fall through unrecognized. `builtin` has no `-p`
        # (measured: `builtin -p shopt …` fails in both shells).
        if transparent == 'command':
            while len(remaining) > 1 and remaining[0] == '-p':
                remaining.pop(0)
    return remaining


def _shopt_split(rest: Sequence[str]) -> Tuple[Optional[str], List[str]]:
    """A `shopt` command's flag LETTERS and its operands, split as it splits them.

    Mirrors the builtin's own argument loop
    (``psh/builtins/shell_options.py#ShoptBuiltin.execute``), because that loop
    is the decider: flags cluster in any order and combination, parsing STOPS
    at the first operand, ``--`` ends flags, and a flag letter outside
    ``psuoq`` aborts with rc 2 before anything is applied.

    The stopping rule is the one this function exists for, and the repo
    already pins it —
    ``tests/unit/builtins/test_shopt_set_o.py#test_flag_after_operand_is_an_operand``:
    in ``shopt extglob -s`` the ``-s`` is an option NAME, so extglob is
    QUERIED, not set. Reading flag letters PAST the first operand made
    analysis invent enables the shell declines to make (``shopt -q extglob
    -s``) and miss enables it really applies (``shopt -s extglob -u``).

    Returns ``(None, [])`` when a bad flag letter aborts the command.
    """
    flags = ''
    for index, word in enumerate(rest):
        if word == '--':
            return flags, list(rest[index + 1:])
        if word.startswith('-') and len(word) > 1:
            if any(letter not in _SHOPT_FLAG_LETTERS for letter in word[1:]):
                return None, []
            flags += word[1:]
        else:
            return flags, list(rest[index:])
    return flags, []


def _option_changes(words: Sequence[Optional[str]]) -> List[Tuple[str, bool]]:
    """Every (option, enable) this command would apply, in order.

    Recognizes the two spellings that reach the shell's option state:

    * ``shopt -s NAME...`` / ``shopt -u NAME...``, with the words split by
      :func:`_shopt_split` exactly as the builtin splits them — clustered
      flags (`-sq`, `-qs`) count by LETTER, flag reading STOPS at the first
      operand, ``--`` ends flags, and a bad flag letter aborts the command
      before it applies anything. A command whose flag letters carry BOTH
      ``s`` and ``u`` changes nothing, in EITHER spelling — ``shopt -su X``
      and ``shopt -s -u X`` are both refused with "cannot set and unset shell
      options simultaneously", rc 1, option untouched (measured in psh and
      bash 5.2.26; pinned for both forms by
      ``tests/unit/builtins/test_shopt_set_o.py#test_s_and_u_conflict``).
      ``-o`` switches which TABLE the operands name
      (:data:`SHOPT_TABLE_OPTIONS` / :data:`SET_O_TABLE_OPTIONS`), so
      ``shopt -so extglob`` and ``shopt -s posix`` are both refusals, not
      state changes.
    * ``set -o NAME`` / ``set +o NAME``, at ANY position in the argument list
      and in clustered form, so `set -e -o extglob` is seen. The sign carries
      bash's inversion: `+o` DISABLES. Scanning stops at ``--``, which ends
      options and makes the rest positional parameters — `set -- -o extglob`
      sets `$1`/`$2`, it does not touch extglob (measured).

    Returns only options this session threads; everything else is ignored, so
    an unrelated `shopt -s histappend` is not mistaken for parse-relevant
    state.
    """
    remaining = _normalize_head(words)
    if not remaining:
        return []
    head, rest = remaining[0], [w for w in remaining[1:] if w is not None]
    changes: List[Tuple[str, bool]] = []
    if head == 'shopt':
        # The builtin's own split decides which words are flags: aggregating
        # letters from the WHOLE argument list read flags that are really
        # operands, which both invented enables (`shopt -q extglob -s`) and
        # missed real ones (`shopt -s extglob -u`).
        flags, operands = _shopt_split(rest)
        if flags is None:
            return []          # a bad flag letter: rc 2, nothing applied
        if 's' in flags and 'u' in flags:
            return []          # refused, rc 1, option untouched
        if 's' in flags:
            enable = True
        elif 'u' in flags:
            enable = False
        else:
            return []          # a query or a listing, not a change
        table = SET_O_TABLE_OPTIONS if 'o' in flags else SHOPT_TABLE_OPTIONS
        for name in operands:
            if name in PARSE_RELEVANT_OPTIONS and name in table:
                changes.append((name, enable))
    elif head == 'set':
        index = 0
        while index < len(rest):
            word = rest[index]
            if word == '--':
                break          # ends options; the rest are positionals
            if (len(word) > 1 and word[0] in '-+' and 'o' in word[1:]
                    and index + 1 < len(rest)):
                name = rest[index + 1]
                if name in PARSE_RELEVANT_OPTIONS:
                    changes.append((name, word[0] == '-'))
                index += 2
                continue
            index += 1
    return changes


def _parser_selection(words: Sequence[Optional[str]]) -> Optional[str]:
    """The parser a ``parser-select`` command would activate, if any."""
    remaining = _normalize_head(words)
    if len(remaining) >= 2 and remaining[0] == 'parser-select' \
            and remaining[1] is not None:
        return resolve_parser_name(remaining[1])
    return None


class AnalysisSyntaxError(Exception):
    """A unit failed to parse. Carries WHERE, so the diagnostic can say so.

    Analysis reports errors the way execution does — ``psh: <source>:<line>:``
    — which it could not do while the whole input was one parse with no
    per-command start line (remediation 2.6 R1-B).
    """

    def __init__(self, error: BaseException, start_line: int) -> None:
        super().__init__(str(error))
        self.error = error
        self.start_line = start_line


def _directive_commands(node: Any, isolated: bool = False):
    """Yield the SimpleCommands whose effects would outlive their unit.

    Walks the ONE schema-declared traversal (``visitor.traversal.walk_ast``),
    marking everything below an isolating node as isolated rather than
    enumerating the state-preserving compounds — so a new control structure is
    state-preserving by default, which is the safe direction: it can only make
    the session more permissive, never make it invent a syntax error.
    """
    if type(node).__name__ in ISOLATING_NODES:
        isolated = True
    # Every member of a MULTI-command pipeline runs in its own process; a
    # one-command pipeline is just a command and keeps its effects.
    if type(node).__name__ == 'Pipeline' and len(getattr(node, 'commands', ())) > 1:
        isolated = True
    if getattr(node, 'background', False):
        isolated = True

    if not isolated and isinstance(node, SimpleCommand):
        yield node
    for child in walk_ast(node):
        yield from _directive_commands(child, isolated)


class AnalysisSession:
    """Parses an input unit by unit under evolving parse-relevant state."""

    def __init__(self, shell: 'Shell') -> None:
        self.shell = shell
        #: The evolving state. A child shell rather than a bag of fields, so
        #: the pipeline reads it through the same attributes it reads for
        #: execution. Built through the shell's OWN type: ``psh.shell`` sits
        #: above this package, so naming it here would invert the import
        #: layering — and an embedder's Shell subclass should carry its own
        #: behaviour into the analysis anyway. ``norc``: startup input must
        #: never run for an analysis.
        self.carrier = self._build_carrier(shell)
        #: ``--format`` is a SOURCE-TO-SOURCE tool: reprinting an alias's body
        #: in place of its name would rewrite the user's script rather than
        #: format it, so it alone parses with aliases off (integrator ruling,
        #: reappraisal #19 T6). It still threads OPTION state — a formatter
        #: that mis-lexes its input reprints something the shell would not run.
        self.expand_aliases = shell.analysis_mode != 'format'

    @staticmethod
    def _build_carrier(shell: 'Shell') -> 'Shell':
        """The carrier shell, built with every debug option OFF.

        EMBEDDER CONTRACT for the ``type(shell)`` construction: a Shell
        subclass an embedder passes in is constructed here with exactly two
        keywords, ``parent_shell=`` and ``norc=``, and nothing else. A
        subclass that requires additional constructor arguments, or that makes
        either of those mean something different, cannot be used as an
        analysis carrier — the analysis path has no other way to reach it.

        The clearing happens on the PARENT across the construction rather than
        on the carrier afterwards, because one of the lines is emitted DURING
        construction: a child state re-detects the terminal and reports the
        result under ``debug-exec``, so clearing the carrier's options after
        the fact would come one line too late. The parent's own values are
        restored in ``finally``, including when construction raises, so the
        window is invisible to everything but the carrier it creates
        (pinned in ``test_analysis_session.py``).
        """
        options = shell.state.options
        saved = {name: options[name] for name in DEBUG_OPTIONS
                 if name in options}
        scopes_were_traced = bool(saved.get('debug-scopes', False))
        try:
            for name in saved:
                options[name] = False
            # The scope manager keeps its OWN debug flag rather than reading
            # the option, and a child clones the manager — so clearing the
            # option alone left the carrier tracing every variable it
            # inherited. Both switches belong in the same window.
            if scopes_were_traced:
                shell.state.scope_manager.enable_debug(False)
            return type(shell)(parent_shell=shell, norc=True)
        finally:
            options.update(saved)
            if scopes_were_traced:
                shell.state.scope_manager.enable_debug(True)

    def analyze(self, content: str, drop_dangling_at_eof: bool = False) -> Program:
        """Parse *content* into ONE merged ``Program``, executing nothing.

        ``drop_dangling_at_eof`` is the input channel's stream-vs-string rule
        for a trailing backslash at true end of input, applied per unit exactly
        as ``SourceProcessor._preprocess_command`` applies it.

        The unit is lexed ONCE. ``lex_and_expand`` yields the heredoc-aware
        token stream (bodies collected into the LexedUnit, NOT tokenized as
        command text) and that SAME stream feeds both the parse and the
        state-absorption pass. An earlier version re-tokenized the unit's raw
        text for absorption, which lexed heredoc BODIES as commands: an
        apostrophe in a body became a false syntax error, and `alias` text in a
        body was absorbed as if it were a command. One lex, one grammar.
        """
        merged = Program()
        input_source = ProgramSource.command_string(content).make_input_source()
        for start_line, unit in iter_command_units(self.carrier, input_source,
                                                   trace=False):
            text = process_line_continuations(
                unit.text, drop_dangling_at_eof=drop_dangling_at_eof)
            if unit.error is not None:
                raise AnalysisSyntaxError(unit.error, start_line)
            if not text.strip() or (text.strip().startswith('#')
                                    and '\n' not in text.strip()):
                continue
            base_line = start_line if start_line > 0 else 1
            try:
                # base_line anchors the unit on its ABSOLUTE source line, as
                # SourceProcessor._parse_command does, so a ParseError reports
                # the line the error is really on rather than line 1 of the
                # unit. EVERY lex or parse failure is raised inside this try,
                # so it reaches the caller through the envelope and carries the
                # unit's line — the lex half used to escape it entirely.
                lexed = lex_and_expand(
                    text, self.carrier, base_line=base_line,
                    expand_aliases=self.expands_aliases_now(),
                    lexer_options=self.carrier.state.options)
                ast = parse_tokens(
                    lexed.tokens, lexed.heredocs, self.carrier,
                    source_text=text, line_offset=max(0, base_line - 1),
                    lexer_options=self.carrier.state.options)
                if start_line > 1:
                    offset_line_numbers(ast, start_line - 1)
                # Absorption runs INSIDE the envelope as well. It walks THIS
                # unit's AST and tokens, so a failure there is a failure to
                # analyze this unit and must reach the caller carrying the
                # unit's line — the last path by which an inner exception
                # could still escape the envelope unlabelled.
                self._absorb_transitions(ast, lexed.tokens)
            except Exception as exc:
                raise AnalysisSyntaxError(exc, start_line) from exc
            merged.statements.extend(ast.statements)
        return merged

    def expands_aliases_now(self) -> bool:
        """Whether THIS unit is parsed with alias expansion live.

        Two independent gates: ``--format`` never expands (the source-to-source
        ruling), and the session's own ``expand_aliases`` option tracks what
        the script has done to it — which is why the option is threaded rather
        than assumed (a script may turn expansion off mid-file).
        """
        return (self.expand_aliases
                and bool(self.carrier.state.options.get('expand_aliases', True)))

    def _absorb_transitions(self, ast: Program, tokens: Sequence[Any]) -> None:
        """Apply this unit's parse-relevant state changes to later units."""
        self._absorb_aliases(tokens)
        for command in _directive_commands(ast):
            words = _effective_words(command)
            for name, enable in _option_changes(words):
                if name in MONOTONE_OPTIONS:
                    # Enables only: narrowing could re-invent the false syntax
                    # errors this session exists to remove.
                    if enable:
                        self.carrier.state.options[name] = True
                elif name in ORDERED_OPTIONS:
                    # Last write wins, matching execution's measured behavior.
                    self.carrier.state.options[name] = enable
            selected = _parser_selection(words)
            if selected is not None:
                self.carrier.active_parser = selected

    def _absorb_aliases(self, tokens: Sequence[Any]) -> None:
        """Promote this unit's ``alias``/``unalias`` definitions into the table.

        ``AliasManager.expand_aliases`` already honours a definition made
        EARLIER IN THE SAME token stream (a documented psh divergence: bash
        defers it to the next line). Whole-file analysis got that for free
        because the whole file WAS one stream; a per-unit session has to carry
        the definitions forward itself, or a script that defines an alias on
        line 1 and uses it on line 2 would stop analyzing — the one place where
        going incremental could have LOST behavior (remediation 2.6 R1-G).

        *tokens* is the unit's own heredoc-aware stream, so a heredoc BODY
        cannot contribute definitions: its lines are data, exactly as they are
        to the shell. Definitions are absorbed even while expansion is OFF,
        because the ``alias`` builtin still DEFINES when ``expand_aliases`` is
        unset — only expansion is gated.

        THE WALK IS THE REAL ONE. This runs ``AliasManager.expand_aliases``
        over the unit with the session's table as its in-pass overlay, and
        keeps the overlay rather than the expansion. Absorbing by hand instead
        — scanning the stream for the words ``alias``/``unalias`` — silently
        dropped the decider's COMMAND-POSITION guard, so `echo unalias -a`
        wiped the analysis table and `echo alias x=...` created an entry, in
        argument position where the shell does neither. A decider's guards are
        part of the decider; reusing the walk is the only way to inherit them.
        """
        table = self.carrier.alias_manager.aliases
        stream = [t for t in tokens if t.type != TokenType.EOF]
        if not any(t.type == TokenType.WORD and t.value in ('alias', 'unalias')
                   for t in stream):
            return
        effective = dict(table)
        self.carrier.alias_manager.expand_aliases(
            list(stream), effective, self.carrier.state.options)
        table.clear()
        table.update(effective)


def parse_for_analysis(shell: 'Shell', content: str,
                       drop_dangling_at_eof: bool = False) -> Program:
    """Parse *content* into an AST for analysis, unit by unit.

    THE one door into analysis parsing: every analysis mode reaches the
    session through here. It walks the same
    unit boundaries execution walks and threads parse-relevant state (extglob,
    posix, the alias table, the active parser) from each unit to the next
    WITHOUT executing anything — so a script that enables extglob on line 1 and
    uses ``+(...)`` on line 2 analyzes exactly as it runs (remediation
    MEDIUM-9(a)). Each unit goes through ``lex_parse.lex_and_expand`` then
    ``lex_parse.parse_tokens`` — the same heredoc-aware lex→alias→parse
    pipeline execution uses, split so the session can feed ONE token stream to
    both the parse and its state absorption — so analysis honours ``--parser``
    and threads lexer options into nested-substitution re-lexing (reappraisal
    #19 H11). A heredoc BODY stays attached to its redirect.

    Line continuations are joined per unit (as
    ``SourceProcessor._preprocess_command`` does): the lexer does NOT collapse a
    continuation in every context (``then\\``, inside ``[[ ]]``), so without this
    analysis reported false syntax errors on valid scripts that execute fine.
    ``drop_dangling_at_eof`` mirrors the execution path's stream-vs-string rule
    for a trailing backslash at true EOF.

    ``--format``'s ``expand_aliases=False`` exception lives on the session; see
    ``AnalysisSession`` for that and for the which-transitions-apply rule.
    """
    return AnalysisSession(shell).analyze(
        content, drop_dangling_at_eof=drop_dangling_at_eof)
