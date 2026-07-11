"""Token-level parsers for the shell parser combinator.

This module provides parsers for individual tokens and token combinations
used throughout the shell grammar.
"""

from ...lexer.token_types import Token
from .core import keyword, token


class TokenParsers:
    """Factory for commonly used token parsers.

    This class provides a centralized location for all token-level parsers,
    organized by category for easy access and maintenance.
    """

    def __init__(self):
        """Initialize all token parsers."""
        self._initialize_basic_tokens()
        self._initialize_operators()
        self._initialize_delimiters()
        self._initialize_keywords()
        self._initialize_expansions()
        self._initialize_special_tokens()
        self._initialize_combined_parsers()

    def _initialize_basic_tokens(self):
        """Initialize basic token parsers."""
        # Basic word and string tokens
        self.word = token('WORD')
        self.string = token('STRING')
        self.eof = token('EOF')

        # Line separators
        self.semicolon = token('SEMICOLON')
        self.newline = token('NEWLINE')

        # Pipeline and logical operators
        self.pipe = token('PIPE')
        self.and_if = token('AND_AND')  # && (the lexer emits AND_AND, not POSIX AND_IF)
        self.or_if = token('OR_OR')     # || (the lexer emits OR_OR, not POSIX OR_IF)

        # Background job
        self.ampersand = token('AMPERSAND')

    def _initialize_operators(self):
        """Initialize operator token parsers."""
        # Redirection operators
        self.redirect_out = token('REDIRECT_OUT')
        self.redirect_in = token('REDIRECT_IN')
        self.redirect_append = token('REDIRECT_APPEND')
        self.redirect_dup = token('REDIRECT_DUP')  # >&, 2>&1
        self.redirect_readwrite = token('REDIRECT_READWRITE')  # <>
        self.redirect_clobber = token('REDIRECT_CLOBBER')  # >|

        # Here document operators
        self.heredoc = token('HEREDOC')  # <<
        self.heredoc_strip = token('HEREDOC_STRIP')  # <<-
        self.here_string = token('HERE_STRING')  # <<<

        # Pipe stderr operator
        self.pipe_and = token('PIPE_AND')  # |&

        # Combined redirect operator parser
        self.redirect_operator = (
            self.redirect_out
            .or_else(self.redirect_in)
            .or_else(self.redirect_append)
            .or_else(self.redirect_dup)
            .or_else(self.redirect_readwrite)
            .or_else(self.redirect_clobber)
            .or_else(self.heredoc)
            .or_else(self.heredoc_strip)
            .or_else(self.here_string)
        )

    def _initialize_delimiters(self):
        """Initialize delimiter token parsers."""
        # Parentheses
        self.lparen = token('LPAREN')
        self.rparen = token('RPAREN')

        # Braces
        self.lbrace = token('LBRACE')
        self.rbrace = token('RBRACE')

        # Brackets
        self.lbracket = token('LBRACKET')
        self.rbracket = token('RBRACKET')

        # Double delimiters for special constructs
        self.double_lparen = token('DOUBLE_LPAREN')
        self.double_rparen = token('DOUBLE_RPAREN')
        self.double_lbracket = token('DOUBLE_LBRACKET')
        self.double_rbracket = token('DOUBLE_RBRACKET')
        self.double_semicolon = token('DOUBLE_SEMICOLON')

    def _initialize_keywords(self):
        """Initialize keyword parsers."""
        # Control structure keywords
        self.if_kw = keyword('if')
        self.then_kw = keyword('then')
        self.elif_kw = keyword('elif')
        self.else_kw = keyword('else')
        self.fi_kw = keyword('fi')

        # Loop keywords
        self.while_kw = keyword('while')
        self.for_kw = keyword('for')
        self.in_kw = keyword('in')
        self.do_kw = keyword('do')
        self.done_kw = keyword('done')

        # Case/select keywords
        self.case_kw = keyword('case')
        self.esac_kw = keyword('esac')
        self.select_kw = keyword('select')

        # Function keyword
        self.function_kw = keyword('function')

        # Pipeline-timing keyword
        self.time_kw = keyword('time')

    def _initialize_expansions(self):
        """Initialize expansion token parsers.

        (PARAM_EXPANSION was retired with WordToken — the lexer emits VARIABLE
        for every ``${...}``; the WordBuilder classifies it.)
        """
        self.variable = token('VARIABLE')

        # Command substitution
        self.command_sub = token('COMMAND_SUB')
        self.command_sub_backtick = token('COMMAND_SUB_BACKTICK')

        # Arithmetic expansion
        self.arith_expansion = token('ARITH_EXPANSION')

        # Process substitution
        self.process_sub_in = token('PROCESS_SUB_IN')
        self.process_sub_out = token('PROCESS_SUB_OUT')

        # Combined expansion parser
        self.expansion = (
            self.variable
            .or_else(self.command_sub)
            .or_else(self.command_sub_backtick)
            .or_else(self.arith_expansion)
            .or_else(self.process_sub_in)
            .or_else(self.process_sub_out)
        )

    def _initialize_special_tokens(self):
        """Initialize special token parsers."""
        # Pipeline negation
        self.exclamation = token('EXCLAMATION')

    def _initialize_combined_parsers(self):
        """Initialize combined/composite parsers."""
        # Statement terminators (semicolon or newline)
        self.statement_terminator = self.semicolon.or_else(self.newline)

        # Word-like tokens (words, strings, expansions, and [ which starts test commands)
        self.word_like = (
            self.word
            .or_else(self.string)
            .or_else(self.lbracket)
            .or_else(self.expansion)
            .or_else(self.process_sub_in)
            .or_else(self.process_sub_out)
        )

    def is_redirect_operator(self, token: Token) -> bool:
        """Check if a token is a redirection operator.

        Args:
            token: Token to check

        Returns:
            True if token is a redirection operator
        """
        redirect_types = {
            'REDIRECT_OUT', 'REDIRECT_IN', 'REDIRECT_APPEND',
            'REDIRECT_DUP', 'REDIRECT_READWRITE', 'REDIRECT_CLOBBER',
            'HEREDOC', 'HEREDOC_STRIP', 'HERE_STRING'
        }
        return token.type.name in redirect_types


# Convenience functions for creating token parsers

def create_token_parsers() -> TokenParsers:
    """Create and return a TokenParsers instance.

    Returns:
        Initialized TokenParsers object
    """
    return TokenParsers()
