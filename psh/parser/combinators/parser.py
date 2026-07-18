"""Main parser integration for the modular parser combinator implementation.

This module integrates all the parser combinator modules into a cohesive
parser for shell commands using functional combinators.
"""

from typing import TYPE_CHECKING, List, Mapping, Optional, Tuple, cast

from ...ast_nodes import ASTNode, Program, Statement, StatementList
from ...lexer.keyword_normalizer import KeywordNormalizer
from ...lexer.token_types import Token, TokenType
from ..config import ParserConfig
from ..parse_inputs import ParseInputs
from ..parse_outcome import ParseOutcome, outcome_from_parse
from ..recursive_descent.helpers import ParseError, describe_token
from .commands import create_command_parsers
from .control_structures import create_control_structure_parsers
from .diagnostics import error_context_for_token
from .expansions import create_expansion_parsers
from .special_commands import create_special_command_parsers

# Import all parser modules
from .tokens import create_token_parsers

if TYPE_CHECKING:
    from ...lexer.heredoc_lexer import LexedHeredoc


class ParserCombinatorShellParser:
    """Experimental parser combinator implementation.

    **Status: Experimental / Educational -- not the production parser.**

    This parser demonstrates functional parsing through composable combinators.
    It breaks down complex shell syntax into small, reusable parsing functions
    that can be combined to handle the full shell grammar.

    The production parser is the recursive descent parser in
    ``recursive_descent/``.  This combinator parser exists as an educational
    counterpoint and proof of concept.  It may lag behind on edge-case fixes
    and new features.  There is no plan to converge the two implementations.

    Project decision (2026-06-12): this parser is **outside the production
    quality bar**.  Parity regression tests pin known-good behavior against
    drift, but remaining gaps (e.g. composite words in some list contexts)
    are documented rather than tracked as defects, and conformance work does
    not target this parser.  Revisit if/when dedicated time is available.

    Use ``parser-select combinator`` inside psh to activate it interactively.
    """

    def __init__(self, config: Optional[ParserConfig] = None,
                 heredocs: "Optional[Mapping[int, 'LexedHeredoc']]" = None):
        """Initialize the parser combinator.

        Args:
            config: Parser configuration
            heredocs: Optional id-keyed map of collected heredocs (the
                LexedUnit's LexedHeredoc entries: spec + body)
        """
        self.config = config or ParserConfig()
        self.heredocs = heredocs
        # Per-call immutable inputs (campaign S4 handoff 3): the ParseInputs
        # budget (lexer_options/line_offset) threaded into template building.
        # Set transiently by parse_with_heredocs; a bare parse() uses None
        # (defaults), and parse() clears the per-module working copies in its
        # finally so the instance retains NO per-call state after return
        # (handoff 1). None by default.
        self._parse_inputs: "Optional[ParseInputs]" = None

        # Initialize all parser modules
        self._initialize_modules()

    def _initialize_modules(self):
        """Initialize all parser modules and wire them together."""
        # Create token parsers
        self.tokens = create_token_parsers()

        # Create expansion parsers
        self.expansions = create_expansion_parsers(self.config)

        # Create command parsers with dependencies
        self.commands = create_command_parsers(
            config=self.config,
            token_parsers=self.tokens,
            expansion_parsers=self.expansions
        )

        # Create control structure parsers
        self.control = create_control_structure_parsers(
            config=self.config,
            token_parsers=self.tokens,
            command_parsers=self.commands
        )

        # Create special command parsers
        self.special = create_special_command_parsers(
            config=self.config,
            token_parsers=self.tokens,
            command_parsers=self.commands
        )

        # Wire circular dependencies
        self._wire_dependencies()

        # Build the complete parser after dependencies are wired
        self._build_complete_parser()

    def _wire_dependencies(self):
        """Wire circular dependencies between modules.

        Some parser modules have circular dependencies (e.g., commands
        can contain control structures which contain commands). This
        method resolves these dependencies after all modules are created.
        """
        # Wire command parsers in dependent modules - this triggers
        # initialization of parsers that depend on commands
        self.control.set_command_parsers(self.commands)
        self.special.set_command_parsers(self.commands)

    def _build_complete_parser(self):
        """Wire the recursive references now that every module exists.

        ``CommandParsers`` built its grammar graph once (pipeline, and-or,
        statement, statement-list) reading two recursion *slots* at parse time.
        Here we fill those slots — no parser is rebuilt or reassigned:

        * the pipeline element widens from a bare simple command to "function
          definition / control structure / special command / simple command" so
          a compound command — or a function definition (``f() { :; } | cat``,
          ``! f() { :; }``, ``time f() { :; }``, ``x && f() { :; }``; #20 H9,
          campaign S5) — can appear inside a pipeline;
        * the statement head gains function definitions (tried first).
        """
        pipeline_element = (
            self.control.function_def
            .or_else(self.control.control_structure)
            .or_else(self.special.special_command)
            .or_else(self.commands.simple_command)
        )
        self.commands.set_command_parser(pipeline_element)
        self.commands.set_function_def(self.control.function_def)
        # A non-brace function body may be any compound command, including
        # the special-command module's `(( ))`.
        self.control.set_special_command_parser(self.special.special_command)

        # Convenience handles onto the (already-built) command + top-level parsers.
        self.command = self.commands.and_or_list
        self.top_level = self.commands.statement_list

    def _prepare_tokens(self, tokens: List[Token]) -> Tuple[List[Token], int]:
        """Normalize keywords and skip leading newlines.

        Returns:
            (normalized_tokens, start_pos).  start_pos == len(tokens)
            when input is empty/newline-only.
        """
        normalizer = KeywordNormalizer()
        tokens = normalizer.normalize(list(tokens))
        start_pos = 0
        while start_pos < len(tokens) and tokens[start_pos].type.name == 'NEWLINE':
            start_pos += 1
        return tokens, start_pos

    def parse(self, tokens: List[Token]) -> Program:
        """Parse a list of tokens into an AST.

        Args:
            tokens: List of tokens from the lexer

        Returns:
            The canonical Program root (same as the recursive descent parser).

        Raises:
            ParseError: If parsing fails
        """
        # Install the per-call working state on the shared long-lived modules —
        # the collected-heredoc map (the redirection mixin builds each heredoc
        # Redirect with its spec truth and body AT CONSTRUCTION) and the
        # ParseInputs budget (template building) — and CLEAR both in the finally
        # so this build-once grammar instance retains NO per-call state after
        # return (campaign S4 handoff 1/3, guarded by the retains-nothing
        # snapshot pin in test_parser_contract_guards_s4).
        self.commands.heredocs = self.heredocs
        self.expansions.parse_ctx = self._parse_inputs
        try:
            return self._parse_body(tokens)
        finally:
            self.commands.heredocs = None
            self.expansions.parse_ctx = None

    def _parse_body(self, tokens: List[Token]) -> Program:
        """The parse proper, run with per-call working state installed."""
        tokens, start_pos = self._prepare_tokens(tokens)

        # Empty input
        if start_pos >= len(tokens):
            return Program(statements=[])

        # Parse the tokens
        result = self.top_level.parse(tokens, start_pos)

        if not result.success:
            # Try to provide a helpful error message. Token identity renders
            # through the shared describe_token so no raw enum name
            # ("EXCLAMATION") leaks into a user-facing diagnostic.
            error_msg = result.error or "Failed to parse input"
            error_token = None
            if result.position < len(tokens):
                error_token = tokens[result.position]
                error_msg = (f"{error_msg} at position {result.position}: "
                             f"{describe_token(error_token)}")
            if error_token is None:
                error_token = tokens[-1] if tokens else Token(type=TokenType.WORD, value='', position=0)
            raise ParseError(error_context_for_token(error_token, error_msg))

        # Get the parsed AST (success was checked above, so value is set)
        ast = result.value
        assert ast is not None

        # Ensure we consumed all tokens (allowing trailing newlines and EOF)
        pos = result.position
        while pos < len(tokens) and tokens[pos].type.name in ['NEWLINE', 'EOF']:
            pos += 1

        if pos < len(tokens):
            # We didn't consume all tokens
            remaining_token = tokens[pos]
            raise ParseError(error_context_for_token(
                remaining_token,
                f"Unexpected token after valid input: {describe_token(remaining_token)}",
            ))

        # Normalize to the canonical Program root: flatten a StatementList into
        # Program.statements; wrap a lone Statement as a one-element program.
        if isinstance(ast, StatementList):
            return Program(statements=list(ast.statements))
        if isinstance(ast, Program):
            return ast
        return Program(statements=[cast(Statement, ast)])

    def parse_with_heredocs(
        self, tokens: List[Token],
        heredocs: "Mapping[int, 'LexedHeredoc']",
        lexer_options: "Optional[Mapping[str, object]]" = None,
        line_offset: int = 0,
    ) -> Program:
        """Parse tokens with collected-heredoc support.

        Args:
            tokens: List of tokens from the lexer (bodies lifted out;
                operator tokens carry ``heredoc_id``)
            heredocs: The LexedUnit's id-keyed map of LexedHeredoc entries
            lexer_options: Shell option dict in effect (campaign S4 handoff 3),
                threaded via ParseInputs so nested-substitution/syntax templates
                build with the same option-sensitive budget as the RD parser
                (notably extglob-aware re-lexing of a nested substitution body).
            line_offset: Enclosing line offset for nested-body diagnostics.

        Returns:
            Parsed AST with each heredoc Redirect built from its spec entry

        The per-call heredoc map and ParseInputs are set for the duration of the
        parse and RESTORED to their prior values afterwards, so the instance
        retains no per-call state after return.
        """
        saved_heredocs = self.heredocs
        saved_inputs = self._parse_inputs
        self.heredocs = heredocs
        self._parse_inputs = ParseInputs(
            lexer_options=lexer_options, line_offset=line_offset)
        try:
            return self.parse(tokens)
        finally:
            self.heredocs = saved_heredocs
            self._parse_inputs = saved_inputs

    def parse_outcome(self, tokens: List[Token]) -> ParseOutcome:
        """Parse into the typed ``Complete | Incomplete | Invalid`` outcome sum.

        The combinator's parity surface for the S4 outcome contract. The
        combinator does not compute an open-construct trail, so ``Incomplete``
        carries an empty trail; an end-of-input failure on an EOF token still
        classifies as ``Incomplete`` via ``ParseError.at_eof`` (the default when
        the offending token is EOF). Continuation-prompt detection remains
        recursive-descent-only (the accumulator builds an RD parser), so this
        exists for parity and I3-readiness, not to drive PS2.
        """
        return outcome_from_parse(lambda: self.parse(tokens), lambda: ())

    def parse_partial(self, tokens: List[Token]) -> Tuple[Optional[ASTNode], int]:
        """Parse as much as possible from the token stream.

        Test-facing: no production caller uses this (the shell entry points call
        only ``parse`` / ``parse_with_heredocs``). Kept as an educational probe
        for how the combinator makes partial progress.

        Args:
            tokens: List of tokens from the lexer

        Returns:
            Tuple of (AST node or None, position where parsing stopped)
        """
        self.commands.heredocs = self.heredocs
        self.expansions.parse_ctx = self._parse_inputs
        try:
            tokens, start_pos = self._prepare_tokens(tokens)

            # Empty input
            if start_pos >= len(tokens):
                return None, start_pos

            # Try parsers from broadest to narrowest (heterogeneous Parser
            # types, so the list is loosely typed).
            candidates: list = [self.top_level, self.commands.statement, self.command]
            for parser in candidates:
                result = parser.parse(tokens, start_pos)
                if result.success:
                    return result.value, result.position

            # Nothing could be parsed
            return None, start_pos
        finally:
            self.commands.heredocs = None
            self.expansions.parse_ctx = None

    def can_parse(self, tokens: List[Token]) -> bool:
        """Check if the tokens can be parsed without actually parsing.

        Test-facing: no production caller uses this (the shell entry points call
        only ``parse`` / ``parse_with_heredocs``). Kept as an educational
        can-this-parse probe.

        Args:
            tokens: List of tokens to check

        Returns:
            True if the tokens appear to be parseable
        """
        try:
            tokens, start_pos = self._prepare_tokens(tokens)

            # Empty input is valid
            if start_pos >= len(tokens):
                return True

            # Try to parse
            result = self.top_level.parse(tokens, start_pos)

            if not result.success:
                return False

            # Check if we consumed all tokens (allowing trailing newlines)
            pos = result.position
            while pos < len(tokens) and tokens[pos].type.name in ['NEWLINE', 'EOF']:
                pos += 1

            return pos == len(tokens)
        except (AttributeError, IndexError, TypeError, ParseError):
            return False

    # The composition modules wired in _initialize_modules: (instance attribute,
    # display label, one-line summary of what it parses). explain_parse() renders
    # only the stages actually present on the instance, so the description cannot
    # drift from the real composition.
    _MODULE_STAGES = (
        ("tokens", "TOKEN PARSERS", "keywords, operators, separators"),
        ("expansions", "EXPANSION PARSERS", "$var, ${...}, $(...), `...`, $((...))"),
        ("commands", "COMMAND PARSERS",
         "simple commands, pipelines, and-or lists, statement lists"),
        ("control", "CONTROL STRUCTURE PARSERS",
         "if/case conditionals, while/until/for/select loops, functions"),
        ("special", "SPECIAL COMMAND PARSERS",
         "(( )) arithmetic, [[ ]] tests, process substitution"),
    )

    def explain_parse(self, tokens: List[Token]) -> str:
        """A short summary of the combinator parsing pipeline.

        The stage list is DERIVED from the modules actually wired on this
        instance (``_MODULE_STAGES`` checked against the live attributes), so
        it stays truthful to the real composition rather than a hand-kept
        narrative. ``tokens`` is accepted for interface symmetry with
        ``parse``/``can_parse`` but is not inspected.
        """
        lines = ["=== Parser Combinator Pipeline ===", ""]
        for i, (attr, label, detail) in enumerate(self._MODULE_STAGES, 1):
            suffix = "" if getattr(self, attr, None) is not None else "  (not wired)"
            lines.append(f"{i}. {label}: {detail}{suffix}")
        return "\n".join(lines) + "\n"


# Convenience functions

def create_parser_combinator_shell_parser(
    config: Optional[ParserConfig] = None,
    heredocs: "Optional[Mapping[int, 'LexedHeredoc']]" = None
) -> ParserCombinatorShellParser:
    """Create and return a ParserCombinatorShellParser instance.

    Args:
        config: Optional parser configuration
        heredocs: Optional id-keyed collected-heredoc map

    Returns:
        Initialized ParserCombinatorShellParser object
    """
    return ParserCombinatorShellParser(config, heredocs)
