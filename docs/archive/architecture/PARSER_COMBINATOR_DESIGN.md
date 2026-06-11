# PSH Parser Combinator Design Document

## Executive Summary

This document presents a comprehensive design for reimplementing the PSH parser using Parser Combinators. The design maintains PSH's educational clarity while providing the composability, testability, and maintainability benefits of combinatorial parsing. The approach leverages insights from the successful lexer refactoring and addresses the specific challenges of shell syntax parsing.

## Table of Contents

1. [Introduction](#introduction)
2. [Parser Combinator Fundamentals](#parser-combinator-fundamentals)
3. [Core Architecture](#core-architecture)
4. [Basic Combinator Implementation](#basic-combinator-implementation)
5. [Shell-Specific Combinators](#shell-specific-combinators)
6. [Grammar Definition](#grammar-definition)
7. [Context Management](#context-management)
8. [Error Handling and Recovery](#error-handling-and-recovery)
9. [Integration with Existing Infrastructure](#integration-with-existing-infrastructure)
10. [Performance Optimizations](#performance-optimizations)
11. [Migration Strategy](#migration-strategy)
12. [Example Implementations](#example-implementations)
13. [Testing Strategy](#testing-strategy)
14. [Benefits and Trade-offs](#benefits-and-trade-offs)

## Introduction

Parser combinators offer a functional approach to parsing where complex parsers are built by combining simpler ones. For PSH, this approach would:

- Replace hand-coded recursive descent with composable building blocks
- Make the grammar more explicit and declarative
- Improve testability through isolated parser testing
- Enable better error recovery and reporting
- Facilitate grammar experimentation and extension

## Parser Combinator Fundamentals

### What is a Parser Combinator?

A parser combinator is a higher-order function that accepts parsers as input and returns a new parser as output. The fundamental idea:

```python
# A parser is a function: TokenStream → Result[T, TokenStream]
Parser[T] = Callable[[TokenStream], Result[T, TokenStream]]

# Combinators transform or combine parsers
Combinator = Callable[[Parser, ...], Parser]
```

### Core Benefits for PSH

1. **Composability**: Build complex parsers from simple ones
2. **Declarative Grammar**: Grammar rules closely match implementation
3. **Type Safety**: Strong typing of parse results
4. **Modularity**: Each parser is independently testable
5. **Reusability**: Common patterns can be abstracted

## Core Architecture

### Base Parser Type

```python
from typing import TypeVar, Generic, Callable, Optional, Tuple, Union
from dataclasses import dataclass
from abc import ABC, abstractmethod

T = TypeVar('T')
U = TypeVar('U')

@dataclass
class ParseResult(Generic[T]):
    """Result of a parse attempt."""
    success: bool
    value: Optional[T] = None
    remaining: Optional['TokenStream'] = None
    error: Optional['ParseError'] = None
    consumed: int = 0  # Tokens consumed for error recovery

class Parser(ABC, Generic[T]):
    """Base parser class using combinator pattern."""
    
    @abstractmethod
    def parse(self, stream: TokenStream, ctx: ParserContext) -> ParseResult[T]:
        """Attempt to parse from the token stream."""
        pass
    
    def __rshift__(self, other: 'Parser[U]') -> 'Parser[Tuple[T, U]]':
        """Sequence combinator: self >> other"""
        return SequenceParser(self, other)
    
    def __or__(self, other: 'Parser[T]') -> 'Parser[T]':
        """Choice combinator: self | other"""
        return ChoiceParser(self, other)
    
    def __lshift__(self, other: 'Parser[U]') -> 'Parser[T]':
        """Left-biased sequence: self << other (parse other but return self's result)"""
        return LeftBiasedSequence(self, other)
    
    def map(self, f: Callable[[T], U]) -> 'Parser[U]':
        """Transform parse result."""
        return MappedParser(self, f)
    
    def bind(self, f: Callable[[T], 'Parser[U]']) -> 'Parser[U]':
        """Monadic bind for context-sensitive parsing."""
        return BoundParser(self, f)
    
    def optional(self) -> 'Parser[Optional[T]]':
        """Make parser optional."""
        return OptionalParser(self)
    
    def many(self) -> 'Parser[List[T]]':
        """Parse zero or more times."""
        return ManyParser(self)
    
    def many1(self) -> 'Parser[List[T]]':
        """Parse one or more times."""
        return Many1Parser(self)
    
    def sep_by(self, separator: 'Parser') -> 'Parser[List[T]]':
        """Parse items separated by separator."""
        return SeparatedByParser(self, separator)
    
    def with_context(self, ctx_modifier: Callable[[ParserContext], ParserContext]) -> 'Parser[T]':
        """Run parser with modified context."""
        return ContextualParser(self, ctx_modifier)
```

### Parser Context

Learning from the lexer's successful context management:

```python
@dataclass
class ParserContext:
    """Unified parser context (inspired by LexerContext)."""
    # Token stream state
    stream: TokenStream
    position: int = 0
    
    # Parse state
    in_function_body: bool = False
    in_arithmetic: bool = False
    in_test_expr: bool = False
    in_case_pattern: bool = False
    in_command_substitution: bool = False
    in_pipeline: bool = False
    
    # Nesting tracking
    paren_depth: int = 0
    brace_depth: int = 0
    
    # Configuration
    config: ParserConfig = field(default_factory=ParserConfig)
    
    # Error handling
    errors: List[ParseError] = field(default_factory=list)
    recovery_points: List[int] = field(default_factory=list)
    
    # Performance
    memo_table: Dict[Tuple[str, int], ParseResult] = field(default_factory=dict)
    
    def with_flag(self, **kwargs) -> 'ParserContext':
        """Create new context with modified flags."""
        new_ctx = copy(self)
        for key, value in kwargs.items():
            setattr(new_ctx, key, value)
        return new_ctx
```

## Basic Combinator Implementation

### Primitive Parsers

```python
class TokenParser(Parser[Token]):
    """Parse a specific token type."""
    def __init__(self, token_type: TokenType):
        self.token_type = token_type
    
    def parse(self, stream: TokenStream, ctx: ParserContext) -> ParseResult[Token]:
        if stream.at_end():
            return ParseResult(False, error=ParseError("Unexpected end of input"))
        
        token = stream.peek()
        if token.type == self.token_type:
            return ParseResult(True, value=token, remaining=stream.advance())
        else:
            return ParseResult(False, error=ParseError(
                f"Expected {self.token_type}, got {token.type}"
            ))

class PredicateParser(Parser[Token]):
    """Parse token matching predicate."""
    def __init__(self, predicate: Callable[[Token], bool], description: str = ""):
        self.predicate = predicate
        self.description = description
    
    def parse(self, stream: TokenStream, ctx: ParserContext) -> ParseResult[Token]:
        if stream.at_end():
            return ParseResult(False, error=ParseError("Unexpected end of input"))
        
        token = stream.peek()
        if self.predicate(token):
            return ParseResult(True, value=token, remaining=stream.advance())
        else:
            return ParseResult(False, error=ParseError(
                f"Token does not match {self.description}"
            ))

def keyword(kw: str) -> Parser[Token]:
    """Parse specific keyword."""
    return PredicateParser(
        lambda t: t.type == TokenType.WORD and t.value == kw,
        f"keyword '{kw}'"
    )

def literal(value: str) -> Parser[Token]:
    """Parse specific literal value."""
    return PredicateParser(
        lambda t: t.value == value,
        f"literal '{value}'"
    )
```

### Combinator Implementations

```python
class SequenceParser(Parser[Tuple[T, U]], Generic[T, U]):
    """Parse first then second parser."""
    def __init__(self, first: Parser[T], second: Parser[U]):
        self.first = first
        self.second = second
    
    def parse(self, stream: TokenStream, ctx: ParserContext) -> ParseResult[Tuple[T, U]]:
        first_result = self.first.parse(stream, ctx)
        if not first_result.success:
            return ParseResult(False, error=first_result.error)
        
        second_result = self.second.parse(first_result.remaining, ctx)
        if not second_result.success:
            return ParseResult(False, error=second_result.error,
                             consumed=first_result.consumed)
        
        return ParseResult(
            True,
            value=(first_result.value, second_result.value),
            remaining=second_result.remaining,
            consumed=first_result.consumed + second_result.consumed
        )

class ChoiceParser(Parser[T], Generic[T]):
    """Try first parser, if it fails try second."""
    def __init__(self, first: Parser[T], second: Parser[T]):
        self.first = first
        self.second = second
    
    def parse(self, stream: TokenStream, ctx: ParserContext) -> ParseResult[T]:
        # Try first parser
        first_result = self.first.parse(stream, ctx)
        if first_result.success:
            return first_result
        
        # Only try second if first consumed no input
        if first_result.consumed > 0:
            return first_result  # Committed to first parser
        
        # Try second parser
        return self.second.parse(stream, ctx)

class ManyParser(Parser[List[T]], Generic[T]):
    """Parse zero or more times."""
    def __init__(self, parser: Parser[T]):
        self.parser = parser
    
    def parse(self, stream: TokenStream, ctx: ParserContext) -> ParseResult[List[T]]:
        results = []
        current_stream = stream
        total_consumed = 0
        
        while True:
            result = self.parser.parse(current_stream, ctx)
            if not result.success:
                # Stop on failure, but this is still success for many
                return ParseResult(True, value=results, 
                                 remaining=current_stream,
                                 consumed=total_consumed)
            
            results.append(result.value)
            current_stream = result.remaining
            total_consumed += result.consumed
            
            # Prevent infinite loops
            if result.consumed == 0:
                break
        
        return ParseResult(True, value=results, 
                         remaining=current_stream,
                         consumed=total_consumed)
```

## Shell-Specific Combinators

### Lookahead Combinators

```python
class LookaheadParser(Parser[T], Generic[T]):
    """Parse with lookahead to resolve ambiguities."""
    def __init__(self, parser: Parser[T], lookahead: Parser, consume_lookahead: bool = False):
        self.parser = parser
        self.lookahead = lookahead
        self.consume_lookahead = consume_lookahead
    
    def parse(self, stream: TokenStream, ctx: ParserContext) -> ParseResult[T]:
        # Check lookahead without consuming
        lookahead_result = self.lookahead.parse(stream, ctx)
        if not lookahead_result.success:
            return ParseResult(False, error=ParseError("Lookahead failed"))
        
        # Parse main content
        result = self.parser.parse(stream, ctx)
        if not result.success:
            return result
        
        # Optionally consume lookahead
        if self.consume_lookahead:
            final_stream = lookahead_result.remaining
        else:
            final_stream = result.remaining
        
        return ParseResult(True, value=result.value, 
                         remaining=final_stream,
                         consumed=result.consumed)

def followed_by(parser: Parser[T], lookahead: Parser) -> Parser[T]:
    """Ensure parser is followed by lookahead pattern."""
    return LookaheadParser(parser, lookahead, consume_lookahead=False)

def not_followed_by(parser: Parser[T], lookahead: Parser) -> Parser[T]:
    """Ensure parser is NOT followed by lookahead pattern."""
    class NegativeLookahead(Parser[T]):
        def parse(self, stream: TokenStream, ctx: ParserContext) -> ParseResult[T]:
            # First try the main parser
            result = parser.parse(stream, ctx)
            if not result.success:
                return result
            
            # Check that lookahead fails
            lookahead_result = lookahead.parse(result.remaining, ctx)
            if lookahead_result.success:
                return ParseResult(False, error=ParseError("Negative lookahead failed"))
            
            return result
    
    return NegativeLookahead()
```

### Context-Sensitive Combinators

```python
class ContextGuardParser(Parser[T], Generic[T]):
    """Only parse if context matches predicate."""
    def __init__(self, parser: Parser[T], predicate: Callable[[ParserContext], bool],
                 error_msg: str = "Context requirement not met"):
        self.parser = parser
        self.predicate = predicate
        self.error_msg = error_msg
    
    def parse(self, stream: TokenStream, ctx: ParserContext) -> ParseResult[T]:
        if not self.predicate(ctx):
            return ParseResult(False, error=ParseError(self.error_msg))
        return self.parser.parse(stream, ctx)

def in_context(parser: Parser[T], **context_flags) -> Parser[T]:
    """Run parser with specific context flags set."""
    def parse_with_context(stream: TokenStream, ctx: ParserContext) -> ParseResult[T]:
        new_ctx = ctx.with_flag(**context_flags)
        return parser.parse(stream, new_ctx)
    
    class ContextParser(Parser[T]):
        def parse(self, stream: TokenStream, ctx: ParserContext) -> ParseResult[T]:
            return parse_with_context(stream, ctx)
    
    return ContextParser()
```

### Memoization Combinator

```python
class MemoizedParser(Parser[T], Generic[T]):
    """Cache parse results for performance."""
    def __init__(self, parser: Parser[T], name: str):
        self.parser = parser
        self.name = name
    
    def parse(self, stream: TokenStream, ctx: ParserContext) -> ParseResult[T]:
        # Create memoization key
        key = (self.name, stream.position)
        
        # Check memo table
        if key in ctx.memo_table:
            return ctx.memo_table[key]
        
        # Parse and memoize
        result = self.parser.parse(stream, ctx)
        ctx.memo_table[key] = result
        return result

def memo(name: str):
    """Decorator to memoize parser results."""
    def decorator(parser: Parser[T]) -> Parser[T]:
        return MemoizedParser(parser, name)
    return decorator
```

## Grammar Definition

### Shell Grammar Using Combinators

```python
class ShellGrammar:
    """Complete shell grammar defined using parser combinators."""
    
    def __init__(self):
        # Token parsers
        self.word = TokenParser(TokenType.WORD)
        self.string = TokenParser(TokenType.STRING)
        self.variable = TokenParser(TokenType.VARIABLE)
        self.pipe = TokenParser(TokenType.PIPE)
        self.semicolon = TokenParser(TokenType.SEMICOLON)
        self.newline = TokenParser(TokenType.NEWLINE)
        self.and_and = TokenParser(TokenType.AND_AND)
        self.or_or = TokenParser(TokenType.OR_OR)
        
        # Build grammar bottom-up
        self._build_grammar()
    
    def _build_grammar(self):
        """Build the complete grammar using combinators."""
        # Forward declarations for recursive rules
        self.statement_list = ForwardParser[StatementList]()
        self.command = ForwardParser[Command]()
        
        # Simple command
        self.simple_command = self._build_simple_command()
        
        # Compound commands
        self.if_statement = self._build_if_statement()
        self.while_loop = self._build_while_loop()
        self.for_loop = self._build_for_loop()
        self.case_statement = self._build_case_statement()
        
        # Control structures can be commands
        self.compound_command = (
            self.if_statement |
            self.while_loop |
            self.for_loop |
            self.case_statement |
            self.subshell_group |
            self.brace_group
        )
        
        # Complete command definition
        self.command.define(self.simple_command | self.compound_command)
        
        # Pipeline
        self.pipeline = self._build_pipeline()
        
        # And-or list
        self.and_or_list = self._build_and_or_list()
        
        # Statement
        self.statement = (
            self.function_def |
            self.and_or_list |
            self.if_statement |
            self.while_loop |
            self.for_loop |
            self.case_statement
        )
        
        # Statement list
        self.statement_list.define(
            self.statement.sep_by(self.statement_separator).map(
                lambda stmts: StatementList(statements=stmts)
            )
        )
    
    def _build_simple_command(self) -> Parser[SimpleCommand]:
        """Build parser for simple commands."""
        # Command word
        command_word = self.word | self.string | self.variable
        
        # Arguments
        argument = command_word | self.process_substitution
        
        # Redirections
        redirection = self._build_redirection()
        
        # Array assignments
        array_assignment = self._build_array_assignment()
        
        # Complete simple command
        @build_ast
        def simple_command_parser(stream: TokenStream, ctx: ParserContext) -> ParseResult[SimpleCommand]:
            # Collect components
            assignments = []
            args = []
            redirects = []
            
            # Parse array assignments
            while True:
                assign_result = array_assignment.parse(stream, ctx)
                if assign_result.success:
                    assignments.append(assign_result.value)
                    stream = assign_result.remaining
                else:
                    break
            
            # Parse command and arguments
            first_arg = argument.parse(stream, ctx)
            if not first_arg.success and not assignments:
                return ParseResult(False, error=ParseError("Expected command"))
            
            if first_arg.success:
                args.append(first_arg.value)
                stream = first_arg.remaining
                
                # Parse remaining arguments and redirections
                while True:
                    # Try redirection
                    redir_result = redirection.parse(stream, ctx)
                    if redir_result.success:
                        redirects.append(redir_result.value)
                        stream = redir_result.remaining
                        continue
                    
                    # Try argument
                    arg_result = argument.parse(stream, ctx)
                    if arg_result.success:
                        args.append(arg_result.value)
                        stream = arg_result.remaining
                        continue
                    
                    break
            
            # Check for background
            bg_result = TokenParser(TokenType.AMPERSAND).parse(stream, ctx)
            background = bg_result.success
            if background:
                stream = bg_result.remaining
            
            return ParseResult(
                True,
                value=SimpleCommand(
                    args=[a.value for a in args],
                    arg_types=[a.type.name for a in args],
                    redirects=redirects,
                    background=background,
                    array_assignments=assignments
                ),
                remaining=stream
            )
        
        return Parser.from_function(simple_command_parser)
    
    def _build_pipeline(self) -> Parser[Pipeline]:
        """Build parser for pipelines."""
        # Negation
        negation = TokenParser(TokenType.BANG).optional()
        
        # Commands separated by pipes
        pipeline_body = self.command.sep_by1(self.pipe)
        
        # Complete pipeline
        return (negation >> pipeline_body).map(
            lambda parts: Pipeline(
                commands=parts[1],
                negated=parts[0] is not None
            )
        )
    
    def _build_if_statement(self) -> Parser[IfConditional]:
        """Build parser for if statements."""
        # Keywords
        if_kw = keyword("if")
        then_kw = keyword("then")
        elif_kw = keyword("elif")
        else_kw = keyword("else")
        fi_kw = keyword("fi")
        
        # Statement separators
        sep = self.statement_separator
        
        # Condition is a statement list
        condition = self.statement_list
        
        # Then part
        then_part = then_kw >> sep >> self.statement_list
        
        # Elif parts (zero or more)
        elif_part = (elif_kw >> sep >> condition >> sep >> then_part).many()
        
        # Else part (optional)
        else_part = (else_kw >> sep >> self.statement_list).optional()
        
        # Complete if statement
        return (
            if_kw >> sep >> 
            condition >> sep >> 
            then_part >>
            elif_part >>
            else_part <<
            fi_kw
        ).map(lambda parts: IfConditional(
            condition=parts[0],
            then_part=parts[1],
            elif_parts=[(p[0], p[1]) for p in parts[2]],
            else_part=parts[3]
        ))
```

### Context-Aware Grammar Rules

```python
def _build_c_style_for_loop(self) -> Parser[CStyleForLoop]:
    """Build parser for C-style for loops with context."""
    for_kw = keyword("for")
    double_paren_open = literal("((")
    double_paren_close = literal("))")
    
    # Arithmetic expressions with proper context
    arithmetic_expr = in_context(
        self.arithmetic_expression,
        in_arithmetic=True
    )
    
    # Parse the three parts of C-style for
    init = arithmetic_expr.optional()
    condition = (self.semicolon >> arithmetic_expr).optional()
    update = (self.semicolon >> arithmetic_expr).optional()
    
    # Body with loop context
    body = in_context(
        self.statement_list,
        in_loop=True
    )
    
    return (
        for_kw >> double_paren_open >>
        init >> condition >> update <<
        double_paren_close >>
        body
    ).map(lambda parts: CStyleForLoop(
        init_expr=parts[0],
        condition_expr=parts[1],
        update_expr=parts[2],
        body=parts[3]
    ))
```

## Context Management

### Context Stack Management

```python
class ContextStackParser(Parser[T], Generic[T]):
    """Parser that maintains a context stack."""
    def __init__(self, parser: Parser[T], push_context: Dict[str, any],
                 pop_keys: Optional[List[str]] = None):
        self.parser = parser
        self.push_context = push_context
        self.pop_keys = pop_keys or list(push_context.keys())
    
    def parse(self, stream: TokenStream, ctx: ParserContext) -> ParseResult[T]:
        # Save current context values
        saved_values = {key: getattr(ctx, key) for key in self.pop_keys}
        
        # Push new context
        for key, value in self.push_context.items():
            setattr(ctx, key, value)
        
        try:
            # Parse with new context
            result = self.parser.parse(stream, ctx)
            return result
        finally:
            # Restore context
            for key, value in saved_values.items():
                setattr(ctx, key, value)

def with_context_stack(**context_values) -> Callable[[Parser[T]], Parser[T]]:
    """Decorator to run parser with stacked context."""
    def decorator(parser: Parser[T]) -> Parser[T]:
        return ContextStackParser(parser, context_values)
    return decorator
```

## Error Handling and Recovery

### Error Production Rules

```python
class ErrorProductionParser(Parser[T], Generic[T]):
    """Parser with built-in error productions."""
    def __init__(self, parser: Parser[T], error_productions: List[Tuple[Parser, str]]):
        self.parser = parser
        self.error_productions = error_productions
    
    def parse(self, stream: TokenStream, ctx: ParserContext) -> ParseResult[T]:
        # Try main parser
        result = self.parser.parse(stream, ctx)
        if result.success:
            return result
        
        # Try error productions
        for error_parser, error_msg in self.error_productions:
            error_result = error_parser.parse(stream, ctx)
            if error_result.success:
                # Report error but continue parsing
                ctx.errors.append(ParseError(
                    error_msg,
                    token=stream.peek(),
                    recovery_hint="Pattern recognized and corrected"
                ))
                return error_result
        
        # No recovery possible
        return result

# Example: if statement with common errors
def build_if_with_errors() -> Parser[IfConditional]:
    correct_if = build_if_statement()
    
    # Common error: missing semicolon before 'then'
    missing_semi = (
        keyword("if") >> 
        statement_list >>
        keyword("then")  # Missing semicolon
    ).map(lambda parts: {
        "error": "Missing ';' before 'then'",
        "correction": lambda: correct_if
    })
    
    return ErrorProductionParser(
        correct_if,
        [(missing_semi, "Missing semicolon before 'then'")]
    )
```

### Recovery Strategies

```python
class RecoveryParser(Parser[T], Generic[T]):
    """Parser with panic mode recovery."""
    def __init__(self, parser: Parser[T], sync_tokens: Set[TokenType]):
        self.parser = parser
        self.sync_tokens = sync_tokens
    
    def parse(self, stream: TokenStream, ctx: ParserContext) -> ParseResult[T]:
        result = self.parser.parse(stream, ctx)
        
        if not result.success and ctx.config.enable_recovery:
            # Skip to synchronization token
            consumed = 0
            while not stream.at_end():
                if stream.peek().type in self.sync_tokens:
                    # Found sync point
                    ctx.recovery_points.append(stream.position)
                    return ParseResult(
                        False,
                        error=result.error,
                        remaining=stream,
                        consumed=consumed
                    )
                stream = stream.advance()
                consumed += 1
        
        return result

# Wrap parser with recovery
def with_recovery(parser: Parser[T], sync_tokens: Set[TokenType]) -> Parser[T]:
    return RecoveryParser(parser, sync_tokens)
```

## Integration with Existing Infrastructure

### Unified Token Integration

```python
class EnhancedTokenParser(Parser[Token]):
    """Parser that leverages enhanced token metadata."""
    def __init__(self, requirements: Dict[str, any]):
        self.requirements = requirements
    
    def parse(self, stream: TokenStream, ctx: ParserContext) -> ParseResult[Token]:
        if stream.at_end():
            return ParseResult(False, error=ParseError("Unexpected end"))
        
        token = stream.peek()
        
        # Check enhanced token metadata
        if hasattr(token, 'metadata') and token.metadata:
            for key, expected in self.requirements.items():
                actual = getattr(token.metadata, key, None)
                if actual != expected:
                    return ParseResult(False, error=ParseError(
                        f"Token metadata mismatch: {key}={actual}, expected {expected}"
                    ))
        
        return ParseResult(True, value=token, remaining=stream.advance())
```

### AST Construction Helpers

```python
def build_ast(parser_func: Callable) -> Parser:
    """Decorator to create parser from function with AST building."""
    class ASTBuildingParser(Parser):
        def parse(self, stream: TokenStream, ctx: ParserContext) -> ParseResult:
            return parser_func(stream, ctx)
    
    return ASTBuildingParser()

# Example usage
@build_ast
def parse_variable_assignment(stream: TokenStream, ctx: ParserContext) -> ParseResult[Assignment]:
    # Parse: NAME=VALUE
    name = TokenParser(TokenType.WORD).parse(stream, ctx)
    if not name.success:
        return ParseResult(False, error=name.error)
    
    equals = literal("=").parse(name.remaining, ctx)
    if not equals.success:
        return ParseResult(False, error=ParseError("Expected '='"))
    
    value = (word | string | variable).parse(equals.remaining, ctx)
    if not value.success:
        return ParseResult(False, error=ParseError("Expected value"))
    
    return ParseResult(
        True,
        value=Assignment(
            name=name.value.value,
            value=value.value.value,
            value_type=value.value.type
        ),
        remaining=value.remaining
    )
```

## Performance Optimizations

### Left Factoring

```python
class LeftFactoredParser(Parser[T], Generic[T]):
    """Optimize common prefixes in choice parsing."""
    def __init__(self, prefix: Parser, branches: Dict[str, Parser[T]]):
        self.prefix = prefix
        self.branches = branches
    
    def parse(self, stream: TokenStream, ctx: ParserContext) -> ParseResult[T]:
        # Parse common prefix
        prefix_result = self.prefix.parse(stream, ctx)
        if not prefix_result.success:
            return ParseResult(False, error=prefix_result.error)
        
        # Determine which branch based on next token
        if prefix_result.remaining.at_end():
            return ParseResult(False, error=ParseError("Unexpected end after prefix"))
        
        next_token = prefix_result.remaining.peek()
        for key, branch_parser in self.branches.items():
            if self._matches_branch(next_token, key):
                return branch_parser.parse(prefix_result.remaining, ctx)
        
        return ParseResult(False, error=ParseError(f"No matching branch for {next_token}"))

# Example: for loop variants
for_loop = LeftFactoredParser(
    prefix=keyword("for"),
    branches={
        "((": c_style_for_parser,      # for ((;;))
        "WORD": traditional_for_parser  # for var in ...
    }
)
```

### Lazy Evaluation

```python
class LazyParser(Parser[T], Generic[T]):
    """Defer parser construction until needed."""
    def __init__(self, parser_factory: Callable[[], Parser[T]]):
        self.parser_factory = parser_factory
        self._parser: Optional[Parser[T]] = None
    
    def parse(self, stream: TokenStream, ctx: ParserContext) -> ParseResult[T]:
        if self._parser is None:
            self._parser = self.parser_factory()
        return self._parser.parse(stream, ctx)

# Use for recursive grammars
statement_list = LazyParser(lambda: build_statement_list())
```

## Migration Strategy

### Phase 1: Parser Combinator Infrastructure
1. Implement core combinator classes
2. Create basic token parsers
3. Set up testing framework
4. Integrate with existing ParserContext

### Phase 2: Incremental Grammar Migration
1. Start with simple constructs (literals, operators)
2. Migrate arithmetic expressions
3. Move to simple commands
4. Progress to control structures

### Phase 3: Advanced Features
1. Implement error productions
2. Add recovery strategies
3. Optimize with memoization
4. Add grammar validation

### Phase 4: Full Integration
1. Replace recursive descent parser
2. Maintain backward compatibility
3. Performance tuning
4. Documentation

## Example Implementations

### Complete Pipeline Parser

```python
def build_pipeline_parser() -> Parser[Pipeline]:
    """Complete pipeline parser with all features."""
    # Components
    simple_cmd = build_simple_command()
    compound_cmd = build_compound_command()
    command = simple_cmd | compound_cmd
    
    # Negation
    bang = TokenParser(TokenType.BANG).optional()
    
    # Build pipeline
    def parse_pipeline(negated: Optional[Token], 
                      commands: List[Command]) -> Pipeline:
        return Pipeline(
            commands=commands,
            negated=negated is not None
        )
    
    # Parser definition
    pipeline = (
        bang >>
        command.sep_by1(TokenParser(TokenType.PIPE))
    ).map(lambda parts: parse_pipeline(parts[0], parts[1]))
    
    # Add context for pipeline execution
    return in_context(pipeline, in_pipeline=True)
```

### Function Definition Parser

```python
def build_function_parser() -> Parser[FunctionDef]:
    """Parser for function definitions with lookahead."""
    # Function name
    name = TokenParser(TokenType.WORD)
    
    # Parentheses
    lparen = literal("(")
    rparen = literal(")")
    
    # Function body
    lbrace = literal("{")
    rbrace = literal("}")
    
    # Lookahead to distinguish from command
    function_pattern = name >> lparen >> rparen
    
    # Parse with lookahead
    @with_context_stack(in_function_body=True)
    def parse_function(stream: TokenStream, ctx: ParserContext) -> ParseResult[FunctionDef]:
        # Try function pattern
        pattern_result = function_pattern.parse(stream, ctx)
        if not pattern_result.success:
            return ParseResult(False, error=ParseError("Not a function definition"))
        
        name_token, _, _ = pattern_result.value
        stream = pattern_result.remaining
        
        # Optional whitespace/newline before body
        stream = skip_whitespace(stream)
        
        # Parse body
        body_result = (lbrace >> statement_list << rbrace).parse(stream, ctx)
        if not body_result.success:
            return ParseResult(False, error=ParseError("Expected function body"))
        
        return ParseResult(
            True,
            value=FunctionDef(
                name=name_token.value,
                body=body_result.value[1]  # Extract from tuple
            ),
            remaining=body_result.remaining
        )
    
    return Parser.from_function(parse_function)
```

## Testing Strategy

### Unit Testing Combinators

```python
class ParserTestCase:
    """Base class for parser tests."""
    def assert_parse_success(self, parser: Parser[T], input_tokens: List[Token],
                           expected: T, remaining: int = 0):
        """Assert parser succeeds with expected result."""
        stream = TokenStream(input_tokens)
        ctx = ParserContext(stream=stream)
        result = parser.parse(stream, ctx)
        
        assert result.success, f"Parse failed: {result.error}"
        assert result.value == expected
        assert len(result.remaining.tokens) == remaining
    
    def assert_parse_failure(self, parser: Parser[T], input_tokens: List[Token]):
        """Assert parser fails."""
        stream = TokenStream(input_tokens)
        ctx = ParserContext(stream=stream)
        result = parser.parse(stream, ctx)
        
        assert not result.success

# Example test
def test_simple_command():
    parser = build_simple_command()
    
    tokens = [
        Token(TokenType.WORD, "echo", 0),
        Token(TokenType.STRING, "hello", 5),
        Token(TokenType.REDIRECT_OUT, ">", 11),
        Token(TokenType.WORD, "file.txt", 13)
    ]
    
    expected = SimpleCommand(
        args=["echo", "hello"],
        arg_types=["WORD", "STRING"],
        redirects=[Redirect(type=">", target="file.txt")]
    )
    
    assert_parse_success(parser, tokens, expected)
```

### Property-Based Testing

```python
from hypothesis import given, strategies as st

@given(st.lists(st.sampled_from(["&&", "||"])))
def test_and_or_associativity(operators):
    """Test that and-or lists parse correctly regardless of associativity."""
    # Generate tokens
    tokens = [Token(TokenType.WORD, "cmd1", 0)]
    for i, op in enumerate(operators):
        tokens.append(Token(TokenType.AND_AND if op == "&&" else TokenType.OR_OR, op, 0))
        tokens.append(Token(TokenType.WORD, f"cmd{i+2}", 0))
    
    # Parse
    parser = build_and_or_list()
    result = parser.parse(TokenStream(tokens), ParserContext())
    
    # Verify structure
    assert result.success
    assert len(result.value.pipelines) == len(operators) + 1
    assert result.value.operators == operators
```

## Benefits and Trade-offs

### Benefits

1. **Composability**: Complex parsers built from simple, reusable components
2. **Declarative**: Grammar closely matches specification
3. **Type Safety**: Strong typing catches errors at compile time
4. **Testability**: Each combinator independently testable
5. **Maintainability**: Clear separation of parsing logic
6. **Extensibility**: Easy to add new constructs
7. **Error Handling**: Systematic approach to error recovery
8. **Performance**: Memoization and optimization opportunities

### Trade-offs

1. **Learning Curve**: Functional programming concepts may be unfamiliar
2. **Debugging**: Stack traces can be deep with nested combinators
3. **Performance Overhead**: Function call overhead vs. hand-coded parser
4. **Memory Usage**: Closure and intermediate object creation

### Mitigation Strategies

1. **Documentation**: Comprehensive examples and patterns
2. **Debugging Tools**: Parser trace and visualization utilities
3. **Optimization**: Selective hand-coding of hot paths
4. **Profiling**: Regular performance analysis

## Conclusion

A parser combinator implementation for PSH would provide significant benefits in terms of maintainability, extensibility, and correctness while preserving the educational value of the project. The design presented here:

- Leverages lessons from the successful lexer refactoring
- Addresses specific challenges of shell syntax
- Integrates cleanly with existing infrastructure
- Provides a clear migration path
- Maintains PSH's commitment to clarity and education

The functional approach of parser combinators aligns well with PSH's goal of providing clear, understandable implementations while also delivering production-quality parsing capabilities.