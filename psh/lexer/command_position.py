"""Shared command-position vocabulary.

"Command position" is the start of a simple command, where a reserved word is
recognized as a keyword (and where the lexer enables operators like ``[[``).
THREE machines track it, at different stages and over different alphabets,
and all of them consult the classifications defined here:

1. **The lexer pass** (``ModularLexer._update_command_position_context``) —
   runs during tokenization, when reserved words are still plain ``WORD``
   tokens, so it matches operator token TYPES (`STATEMENT_SEPARATORS`,
   `COMMAND_GROUP_OPENERS`) plus keyword VALUES
   (`LEXER_COMMAND_POSITION_WORDS`).

2. **The keyword normalizer** (``KeywordNormalizer``) — runs after
   tokenization, when keywords carry their own token types, so it matches
   typed keywords (`RESET_TO_COMMAND_POSITION`) plus the same separators.

3. **The command-substitution extent scanner**
   (``cmdsub_scanner.find_command_substitution_end``) — runs on RAW TEXT
   (no tokens exist yet) to find where ``$(...)`` ends, so it matches plain
   word strings (`CMDPOS_KEEPING_WORDS`). Its job is narrower: it only
   needs command position to recognize ``case`` (whose patterns contain
   unmatched ``)``), so its set also includes words the other passes
   handle structurally (``{``, ``!``, ``time``).

The sets deliberately differ — each machine sees a different alphabet at a
different stage — but the notion of "what returns us to command position"
is defined in this one file so the three stay in sight of each other.

A unified state machine is intentionally NOT extracted: the per-stage
differences are irreducible. Instead, the documented relationships between
these sets (and that their keyword-valued entries are real keywords) are
locked by ``tests/unit/lexer/test_command_position_consistency.py`` so the
vocabulary cannot silently drift apart.

For the transition tables of all three machines side by side, the
deliberate asymmetries between the sets, and worked examples, see
``docs/architecture/command_position.md``.
"""

from typing import TYPE_CHECKING

from .token_types import TokenType

if TYPE_CHECKING:
    from .state_context import LexicalState

# Operator token types after which the next token is at command position.
# Shared verbatim by the lexer pass and the normalizer. `&` and `|&` belong
# here just like `;` and `|`: bash accepts `true & if …` and `a |& while …`
# (the cmdsub scanner already treats both characters this way).
STATEMENT_SEPARATORS = frozenset({
    TokenType.SEMICOLON,
    TokenType.AMPERSAND,
    TokenType.NEWLINE,
    TokenType.AND_AND,
    TokenType.OR_OR,
    TokenType.PIPE,
    TokenType.PIPE_AND,
})

# Case-item terminators (``;;``, ``;&``, ``&;``) also return to command
# position. The normalizer treats these as separators; the lexer instead tracks
# case state directly (case_depth / in_case_pattern), so it does not fold these
# into its command-position reset.
CASE_TERMINATORS = frozenset({
    TokenType.DOUBLE_SEMICOLON,
    TokenType.SEMICOLON_AMP,
    TokenType.AMP_SEMICOLON,
})

# Token types after which the next token is at command position, consulted by
# the keyword normalizer. Most are reserved-word types that only exist after
# keyword normalization (so only the normalizer uses them). The two compound
# closers — `))` and `]]` — are operator types present during tokenization;
# they are here because an arithmetic command or `[[ ]]` test used as a
# condition header may be followed DIRECTLY (no separator) by `then`/`do`
# (bash: `if ((1)) then …`, `while ((x)) do …`, `for ((;;)) do …`,
# `if [[ a = a ]] then …`), and those `then`/`do` must still normalize to
# keywords.
RESET_TO_COMMAND_POSITION = frozenset({
    TokenType.THEN,
    TokenType.DO,
    TokenType.ELSE,
    TokenType.ELIF,
    TokenType.FI,
    TokenType.DONE,
    TokenType.ESAC,
    TokenType.DOUBLE_RPAREN,
    TokenType.DOUBLE_RBRACKET,
})

# Structural openers after which the lexer is at command position.
COMMAND_GROUP_OPENERS = frozenset({
    TokenType.LPAREN,
    TokenType.LBRACE,
})

# Reserved-word / operator tokens that PREFIX a pipeline and keep the FOLLOWING
# token at command position, so a compound keyword (`while`/`if`/`case`/...) or
# the `[[` test operator right after them is still recognized: `! while ...; do
# ...; done`, `! if ...; fi`, `! [[ -z x ]]`, `time while ...`, `time [[ ... ]]`.
# Without this the lexer/normalizer reset command position after `!`/`time`, so
# the next reserved word lexed as a plain WORD and the parser hit "Expected
# command".
PIPELINE_PREFIX_TOKENS = frozenset({
    TokenType.EXCLAMATION,
    TokenType.TIME,
})

# WORD values the lexer pass treats as command-position setters during
# tokenization (before keywords have types). Two deliberate asymmetries
# against RESET_TO_COMMAND_POSITION:
#
# * the OPENERS (if/while/until/for/case) are included: the lexer needs
#   `while [[ -f x ]]` to enable `[[` right after the keyword, while the
#   normalizer handles openers through its own keyword logic;
# * the CLOSERS (fi/done/esac) are omitted: in valid syntax a closer is
#   followed by a separator (which resets command position anyway) or by
#   another closer, never directly by a command — so the lexer has no need
#   for them, and the omission only shows in already-invalid inputs
#   (`fi [[` lexes `[[` as a word, not an operator).
LEXER_COMMAND_POSITION_WORDS = frozenset({
    'if', 'while', 'until', 'for', 'case',
    'then', 'do', 'else', 'elif',
    # `time` prefixes a pipeline: keep command position so `time while`/
    # `time [[ ... ]]` recognize the following keyword/operator.
    'time',
})

# Plain word strings that keep the cmdsub extent scanner "at command
# position", so a `case` directly after them is recognized
# (`if case ...`, `do case ...`, `{ case ...`). Includes closers and the
# structural words it sees as text rather than as tokens.
CMDPOS_KEEPING_WORDS = frozenset({
    'if', 'then', 'else', 'elif', 'fi', 'while', 'until', 'do', 'done',
    '{', '}', '!', 'time', 'coproc',
})


# Token types after which the lexer pass is at command position: the shared
# separators, the structural group openers, and the pipeline-prefix operators.
_COMMAND_STARTING_TOKENS = (
    STATEMENT_SEPARATORS | COMMAND_GROUP_OPENERS | PIPELINE_PREFIX_TOKENS)

# Redirection operators are "neutral": they do NOT change command position, so
# a redirection placed before a command (`>out echo hi`, `>out if ...`) leaves
# the following word/keyword at command position.
_NEUTRAL_TOKENS = frozenset({
    TokenType.REDIRECT_IN, TokenType.REDIRECT_OUT, TokenType.REDIRECT_APPEND,
    TokenType.HEREDOC, TokenType.HEREDOC_STRIP, TokenType.HERE_STRING,
})


def advance_lexical_state(
    state: "LexicalState", token_type: TokenType, token_value: str = ''
) -> None:
    """Advance the lexer's :class:`~psh.lexer.state_context.LexicalState` by one
    emitted token — the ONE lexer-stage command-position / case transition.

    This is the single source of truth for the LEXER PASS only. It deliberately
    does NOT serve the keyword normalizer or the command-substitution extent
    scanner: as documented in this module's docstring (and locked by
    ``tests/unit/lexer/test_command_position_consistency.py``), those three
    machines run at different pipeline stages over different alphabets — the
    lexer over keyword-VALUED ``WORD`` tokens (keywords have no type yet), the
    normalizer over typed keywords, the scanner over raw text with its own
    ``case`` phase FSM — and their transition SHAPES are irreducibly different.
    Only the classification VOCABULARY (the frozensets above) is shared; a
    unified transition function was intentionally not extracted. Do not extend
    this to the other two stages without new evidence.

    Mutates *state* in place. The order of updates is significant and mirrors
    the historical inline implementation: depths first, then the case FSM (the
    ``case`` opener gated on the token's OWN command position), then the
    command-position transition (whose ``)`` branch reads the just-updated
    bracket depth).
    """
    # Whether the token we are about to classify was ITSELF read at command
    # position. ``state.command_position`` still holds the state set by the
    # PREVIOUS token — the same value the recognizers just consulted to
    # tokenize this one — so it is exactly "was this word eligible as a
    # reserved word at its own position". Reserved-word/case transitions below
    # are gated on this: a keyword-SPELLED WORD that appears as an ordinary
    # argument (`echo if [[ x`) is NOT at command position, so it must not
    # restore command position or open case state and thereby flip the
    # classification of the following token. This mirrors the KeywordNormalizer,
    # which only promotes a WORD to a keyword when command position holds.
    was_command_position = state.command_position

    # -- bracket / arithmetic nesting depth --------------------------------
    # Track arithmetic-paren nesting by counting *individual* parens, so a
    # nested group balances regardless of how the lexer fuses adjacent parens.
    # `((` opens two levels, `))` closes two, and single `(`/`)` met inside
    # arithmetic adjust one level each (e.g. `for ((i=0; i<((5)-1); i++))`).
    if token_type == TokenType.DOUBLE_LBRACKET:
        state.bracket_depth += 1
    elif token_type == TokenType.DOUBLE_RBRACKET:
        state.bracket_depth -= 1
    elif token_type == TokenType.DOUBLE_LPAREN:
        state.arithmetic_depth += 2
    elif token_type == TokenType.DOUBLE_RPAREN:
        state.arithmetic_depth = max(0, state.arithmetic_depth - 2)
    elif token_type == TokenType.LPAREN and state.arithmetic_depth > 0:
        state.arithmetic_depth += 1
    elif token_type == TokenType.RPAREN and state.arithmetic_depth > 0:
        state.arithmetic_depth -= 1

    # -- case-statement phase ---------------------------------------------
    # Only a `case` at command position opens case state — an argument that
    # merely spells `case` (`echo case ...`) must not (gated like the keyword
    # branch below). The `in`/`esac`/terminator transitions stay guarded by
    # case_expecting_in / case_depth, which are only ever set here, so they are
    # transitively gated on this same eligibility check.
    if (token_type == TokenType.WORD and token_value == 'case'
            and was_command_position):
        state.case_depth += 1
        state.case_expecting_in = True
    elif (token_type == TokenType.WORD and token_value == 'in'
          and state.case_expecting_in):
        state.case_expecting_in = False
        state.in_case_pattern = True
    elif (token_type == TokenType.WORD and token_value == 'esac'
          and state.case_depth > 0):
        state.case_depth -= 1
        state.in_case_pattern = False
    elif (token_type == TokenType.RPAREN
          and state.case_depth > 0
          and state.in_case_pattern):
        state.in_case_pattern = False
    elif token_type in CASE_TERMINATORS and state.case_depth > 0:
        state.in_case_pattern = True

    # -- command position --------------------------------------------------
    if token_type in _COMMAND_STARTING_TOKENS:
        state.set_command_position()
    elif token_type == TokenType.RPAREN and state.bracket_depth == 0:
        # `)` returns to command position (function header / case pattern /
        # subshell close) — but only OUTSIDE a `[[ ]]` conditional, where a `)`
        # is part of the regex/conditional operand (e.g. the group close in
        # `=~ ([[:alpha:]]+)`) and must NOT flip command position, or the
        # following `[[` is mis-lexed as the DOUBLE_LBRACKET operator.
        state.set_command_position()
    elif (token_type == TokenType.WORD
          and token_value in LEXER_COMMAND_POSITION_WORDS
          and was_command_position):
        # Keywords are emitted as WORD during tokenization (before the
        # normalizer runs). Treat keyword-valued words as command-position
        # setters so operators like `[[` are recognized correctly — but ONLY
        # when the word was itself at command position (a genuine keyword). An
        # identically-spelled ARGUMENT (`echo if [[ x`) falls through to the
        # reset below, so the following `[[` stays a plain word, matching bash.
        state.set_command_position()
    elif token_type not in _NEUTRAL_TOKENS:
        state.reset_command_position()
