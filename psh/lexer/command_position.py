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

from .token_types import TokenType

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
