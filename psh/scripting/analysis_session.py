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

WHICH TRANSITIONS APPLY (the rule, integrator-ruled — remediation 2.6 R1-F).
Analysis cannot evaluate control flow, so it cannot know whether a directive is
REACHED. The rule is therefore deliberately MONOTONE:

* every option ENABLE found in a parsed unit applies to later units;
* a DISABLE never applies — narrowing the state could only re-invent the
  false syntax errors this session exists to remove;
* directives inside a STATE-ISOLATED region (a subshell, a member of a
  multi-command pipeline, a backgrounded command, a command or process
  substitution) are ignored, because execution discards their effects too;
* directives inside a FUNCTION BODY do apply — a defined function is usually
  called, and execution's answer for the common case is "live".

Consequences, measured against execution over a 30-script corpus and DECLARED
rather than hidden: the rule is exact for 19 rows, PERMISSIVE for 8 (it treats
an unreached directive as live, so analysis parses a superset — it can miss a
syntax error, never invent one), and blind for 2 — a directive inside an
``eval`` STRING or a ``source``d FILE, which no non-executing analysis can see.
Those two are the declared residual (R1-C); they are pinned as divergences.

RELATIONSHIP TO ``bash -n`` (R1-E). ``bash -n`` does not execute ``shopt``
either, so it reports the same false syntax error, and psh's own ``-n``
(``noexec``) is state-blind for the same reason. psh keeps ``-n`` pinned to
bash and makes ``--validate`` state-aware: they answer different questions —
"what does bash's syntax check say?" versus "would this script parse as it
runs?". The divergence from ``bash -n`` is deliberate and pinned.
"""
from typing import TYPE_CHECKING, Any, List, Optional, Tuple

from ..ast_nodes import Program
from .lex_parse import lex_and_parse
from .source_processor import _offset_line_numbers, iter_command_units

if TYPE_CHECKING:
    from ..shell import Shell

#: Option names the lex→parse pipeline actually consults. DERIVED in the 2.6
#: census from three independent instruments (a runtime option-key trace, a
#: runtime shell-attribute trace, and a static scan of psh/lexer + psh/parser
#: for literal keys read from an options mapping), which agreed on exactly
#: these two. ``tests/unit/scripting/test_analysis_session.py`` re-derives the
#: static half and fails if the lexer grows a third, so this tuple cannot
#: silently fall behind the code it summarizes.
PARSE_RELEVANT_OPTIONS: Tuple[str, ...] = ('extglob', 'posix')

#: Node types whose interior runs with its own copy of the shell state, so an
#: option change inside them dies with them. Totality (every ``CompoundCommand``
#: subclass classified either here or as state-preserving) is guarded by
#: ``test_analysis_session.py`` so a NEW compound shape cannot join the AST
#: unclassified.
ISOLATING_NODES = ('SubshellGroup', 'CommandSubstitution', 'ProcessSubstitution')


class AnalysisSyntaxError(Exception):
    """A unit failed to parse. Carries WHERE, so the diagnostic can say so.

    Analysis reports errors the way execution does — ``psh: <source>:<line>:``
    — which it could not do while the whole input was one parse with no
    per-command start line (remediation 2.6 R1-B).
    """

    def __init__(self, error: BaseException, start_line: int,
                 source_text: str) -> None:
        super().__init__(str(error))
        self.error = error
        self.start_line = start_line
        self.source_text = source_text


def _directive_commands(node: Any, isolated: bool = False):
    """Yield the SimpleCommands whose effects would outlive their unit.

    Walks the ONE schema-declared traversal (``visitor.traversal.walk_ast``),
    marking everything below an isolating node as isolated rather than
    enumerating the state-preserving compounds — so a new control structure is
    state-preserving by default, which is the safe direction: it can only make
    the session more permissive, never make it invent a syntax error.
    """
    from ..ast_nodes.commands import SimpleCommand
    from ..visitor.traversal import walk_ast

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
        from ..shell import Shell as _Shell
        self.shell = shell
        #: The evolving state. A child shell rather than a bag of fields so the
        #: pipeline reads it through the same attributes it reads for
        #: execution. norc: startup input must never run for an analysis.
        self.carrier = _Shell(parent_shell=shell, norc=True)
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
        """
        from .input_preprocessing import process_line_continuations
        from .program_source import ProgramSource

        merged = Program()
        input_source = ProgramSource.command_string(content).make_input_source()
        for start_line, unit in iter_command_units(self.carrier, input_source):
            text = process_line_continuations(
                unit.text, drop_dangling_at_eof=drop_dangling_at_eof)
            if unit.error is not None:
                raise AnalysisSyntaxError(unit.error, start_line,
                                          unit.source or unit.text)
            if not text.strip() or (text.strip().startswith('#')
                                    and '\n' not in text.strip()):
                continue
            try:
                # base_line anchors the unit on its ABSOLUTE source line, as
                # SourceProcessor._parse_command does, so a ParseError reports
                # the line the error is really on rather than line 1 of the
                # unit. The AST's own .line stamps are offset separately below
                # (line_offset serves error reporting and nested fragments).
                ast = lex_and_parse(text, self.carrier,
                                    base_line=start_line if start_line > 0 else 1,
                                    expand_aliases=self.expand_aliases,
                                    lexer_options=self.carrier.state.options)
            except Exception as exc:
                raise AnalysisSyntaxError(exc, start_line, text) from exc
            if start_line > 1:
                _offset_line_numbers(ast, start_line - 1)
            merged.statements.extend(ast.statements)
            self._absorb_transitions(ast, text)
        return merged

    def _absorb_transitions(self, ast: Program, text: str) -> None:
        """Apply this unit's parse-relevant state changes to later units."""
        if self.expand_aliases:
            self._absorb_aliases(text)
        for command in _directive_commands(ast):
            args = command.args
            if not args:
                continue
            head, rest = args[0], args[1:]
            if head == 'shopt' and '-s' in rest:
                for name in rest:
                    if name in PARSE_RELEVANT_OPTIONS:
                        self.carrier.state.options[name] = True
            elif head == 'set' and len(rest) >= 2 and rest[0] == '-o':
                if rest[1] in PARSE_RELEVANT_OPTIONS:
                    self.carrier.state.options[rest[1]] = True
            elif head == 'parser-select' and rest:
                from ..invocation import resolve_parser_name
                selected = resolve_parser_name(rest[0])
                if selected is not None:
                    self.carrier.active_parser = selected

    def _absorb_aliases(self, text: str) -> None:
        """Promote this unit's ``alias``/``unalias`` definitions into the table.

        ``AliasManager.expand_aliases`` already honours a definition made
        EARLIER IN THE SAME token stream (a documented psh divergence: bash
        defers it to the next line). Whole-file analysis got that for free
        because the whole file WAS one stream; a per-unit session has to carry
        the definitions forward itself, or a script that defines an alias on
        line 1 and uses it on line 2 would stop analyzing — the one place where
        going incremental could have LOST behavior (remediation 2.6 R1-G).
        """
        from ..lexer import tokenize
        from ..lexer.token_types import TokenType

        table = self.carrier.alias_manager.aliases
        tokens = [t for t in tokenize(text, shell_options=self.carrier.state.options)
                  if t.type != TokenType.EOF]
        if not any(t.type == TokenType.WORD and t.value in ('alias', 'unalias')
                   for t in tokens):
            return
        effective = dict(table)
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if (token.type == TokenType.WORD
                    and token.value in ('alias', 'unalias')):
                index = self.carrier.alias_manager._absorb_alias_command(
                    tokens, index, effective)
                continue
            index += 1
        table.clear()
        table.update(effective)


def parse_for_analysis(shell: 'Shell', content: str,
                       drop_dangling_at_eof: bool = False) -> Program:
    """Parse *content* for analysis under evolving parse-relevant state."""
    return AnalysisSession(shell).analyze(
        content, drop_dangling_at_eof=drop_dangling_at_eof)


def unit_texts(shell: 'Shell', content: str) -> List[Optional[str]]:
    """The unit boundaries analysis would use — for tests and debugging."""
    from .program_source import ProgramSource
    session = AnalysisSession(shell)
    return [unit.text for _, unit in iter_command_units(
        session.carrier,
        ProgramSource.command_string(content).make_input_source())]
