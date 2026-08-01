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
  builtin runs (assignment prefixes, a backslash-escaped head, ``builtin``/``command``)
  and through clustered flags — see :func:`_option_changes`.

Value, PER OPTION, because the options do not share semantics:

* ``extglob`` / ``posix`` are MONOTONE — only enables apply. Narrowing on an
  unreached disable would re-invent the false syntax errors this session
  exists to remove.
* ``expand_aliases`` is ORDERED — last write wins, enables and disables both,
  because that is what execution measurably does (a script that unsets it
  stops expanding aliases in later units, = bash). Modelling it as monotone
  would model a shell nobody runs.

Consequences, measured against execution and DECLARED rather than hidden: for
the monotone options the rule is exact for 19 of 29 corpus rows and PERMISSIVE
for 8 (an unreached directive is treated as live, so analysis parses a
superset — it can miss a syntax error, never invent one); for
``expand_aliases`` an unreached conditional DISABLE narrows analysis, which is
the one place the option axis can still produce a false syntax error, and it is
pinned as such. Blind for 2 rows in every case — a directive inside an ``eval``
STRING or a ``source``d FILE, which no non-executing analysis can see. Those
are the declared residual (R1-C); all are pinned as divergences.

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
from ..invocation import resolve_parser_name
from ..lexer.token_types import TokenType
from ..visitor.traversal import walk_ast
from .input_preprocessing import process_line_continuations
from .lex_parse import lex_and_expand, parse_tokens
from .program_source import ProgramSource
from .source_processor import _offset_line_numbers, iter_command_units

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

#: Node types whose interior runs with its own copy of the shell state, so an
#: option change inside them dies with them. Totality (every ``CompoundCommand``
#: subclass classified either here or as state-preserving) is guarded by
#: ``test_analysis_session.py`` so a NEW compound shape cannot join the AST
#: unclassified.
ISOLATING_NODES = ('SubshellGroup', 'CommandSubstitution', 'ProcessSubstitution')


def _normalize_head(args: Sequence[str]) -> List[str]:
    """Strip the prefixes that change WHO runs a command but not WHICH builtin.

    `x=1 command \\shopt -s extglob` runs the same `shopt` the bare spelling
    does, and execution applies its option either way — so an analysis that
    only recognized the bare head silently missed six live spellings while
    claiming to find "every option ENABLE in a parsed unit". Handles, in
    order: leading `NAME=value` assignment words, a backslash-escaped head
    (`\\shopt` — bash's suppress-alias-expansion spelling), and any run of
    `builtin` / `command` prefixes.
    """
    words = list(args)
    while words and _ASSIGNMENT_WORD.match(words[0]):
        words.pop(0)
    while words:
        if words[0].startswith('\\'):
            words[0] = words[0][1:]
            continue
        if words[0] in _TRANSPARENT_HEADS and len(words) > 1:
            words.pop(0)
            continue
        break
    return words


def _option_changes(args: Sequence[str]) -> List[Tuple[str, bool]]:
    """Every (option, enable) this command would apply, in order.

    Recognizes the two spellings that reach the shell's option state:

    * ``shopt -s NAME...`` / ``shopt -u NAME...``, including CLUSTERED short
      flags (`-sq`, `-qs`) — the letter decides, not the exact flag word;
    * ``set -o NAME`` / ``set +o NAME``, at ANY position in the argument list
      and in clustered form, so `set -e -o extglob` is seen. The sign carries
      bash's inversion: `+o` DISABLES.

    Returns only options this session threads; everything else is ignored, so
    an unrelated `shopt -s histappend` is not mistaken for parse-relevant
    state.
    """
    words = _normalize_head(args)
    if not words:
        return []
    head, rest = words[0], words[1:]
    changes: List[Tuple[str, bool]] = []
    if head == 'shopt':
        enable = None
        for word in rest:
            if word.startswith('-') and len(word) > 1:
                if 's' in word[1:]:
                    enable = True
                elif 'u' in word[1:]:
                    enable = False
        if enable is None:
            return []
        for word in rest:
            if not word.startswith('-') and word in PARSE_RELEVANT_OPTIONS:
                changes.append((word, enable))
    elif head == 'set':
        index = 0
        while index < len(rest):
            word = rest[index]
            if (len(word) > 1 and word[0] in '-+' and 'o' in word[1:]
                    and index + 1 < len(rest)):
                name = rest[index + 1]
                if name in PARSE_RELEVANT_OPTIONS:
                    changes.append((name, word[0] == '-'))
                index += 2
                continue
            index += 1
    return changes


def _parser_selection(args: Sequence[str]) -> Optional[str]:
    """The parser a ``parser-select`` command would activate, if any."""
    words = _normalize_head(args)
    if len(words) >= 2 and words[0] == 'parser-select':
        return resolve_parser_name(words[1])
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
        self.carrier = type(shell)(parent_shell=shell, norc=True)
        #: ``--format`` is a SOURCE-TO-SOURCE tool: reprinting an alias's body
        #: in place of its name would rewrite the user's script rather than
        #: format it, so it alone parses with aliases off (integrator ruling,
        #: reappraisal #19 T6). It still threads OPTION state — a formatter
        #: that mis-lexes its input reprints something the shell would not run.
        self.expand_aliases = shell.analysis_mode != 'format'

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
        for start_line, unit in iter_command_units(self.carrier, input_source):
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
            except Exception as exc:
                raise AnalysisSyntaxError(exc, start_line) from exc
            if start_line > 1:
                _offset_line_numbers(ast, start_line - 1)
            merged.statements.extend(ast.statements)
            self._absorb_transitions(ast, lexed.tokens)
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
            for name, enable in _option_changes(command.args):
                if name in MONOTONE_OPTIONS:
                    # Enables only: narrowing could re-invent the false syntax
                    # errors this session exists to remove.
                    if enable:
                        self.carrier.state.options[name] = True
                elif name in ORDERED_OPTIONS:
                    # Last write wins, matching execution's measured behavior.
                    self.carrier.state.options[name] = enable
            selected = _parser_selection(command.args)
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
        """
        table = self.carrier.alias_manager.aliases
        stream = [t for t in tokens if t.type != TokenType.EOF]
        if not any(t.type == TokenType.WORD and t.value in ('alias', 'unalias')
                   for t in stream):
            return
        effective = dict(table)
        index = 0
        while index < len(stream):
            token = stream[index]
            if (token.type == TokenType.WORD
                    and token.value in ('alias', 'unalias')):
                index = self.carrier.alias_manager._absorb_alias_command(
                    stream, index, effective)
                continue
            index += 1
        table.clear()
        table.update(effective)


def parse_for_analysis(shell: 'Shell', content: str,
                       drop_dangling_at_eof: bool = False) -> Program:
    """Parse *content* for analysis under evolving parse-relevant state."""
    return AnalysisSession(shell).analyze(
        content, drop_dangling_at_eof=drop_dangling_at_eof)
