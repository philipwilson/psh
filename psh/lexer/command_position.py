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
"""

from .token_types import TokenType

# Operator token types after which the next token is at command position.
# Shared verbatim by the lexer pass and the normalizer.
STATEMENT_SEPARATORS = frozenset({
    TokenType.SEMICOLON,
    TokenType.NEWLINE,
    TokenType.AND_AND,
    TokenType.OR_OR,
    TokenType.PIPE,
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

# Reserved-word token types after which the next token is at command position.
# These types only exist after keyword normalization, so only the normalizer
# uses them — during tokenization these words are still plain WORD tokens.
RESET_TO_COMMAND_POSITION = frozenset({
    TokenType.THEN,
    TokenType.DO,
    TokenType.ELSE,
    TokenType.ELIF,
    TokenType.FI,
    TokenType.DONE,
    TokenType.ESAC,
})

# Structural openers after which the lexer is at command position.
COMMAND_GROUP_OPENERS = frozenset({
    TokenType.LPAREN,
    TokenType.LBRACE,
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
})

# Plain word strings that keep the cmdsub extent scanner "at command
# position", so a `case` directly after them is recognized
# (`if case ...`, `do case ...`, `{ case ...`). Includes closers and the
# structural words it sees as text rather than as tokens.
CMDPOS_KEEPING_WORDS = frozenset({
    'if', 'then', 'else', 'elif', 'fi', 'while', 'until', 'do', 'done',
    '{', '}', '!', 'time', 'coproc',
})
