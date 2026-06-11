# Parser Combinator Control Structures Implementation Plan

## Overview

This document outlines the detailed plan for adding control structure support to the PSH parser combinator implementation. The goal is to extend the existing proof-of-concept parser combinator to handle all shell control structures (if/then/else, while, for, case) while maintaining the functional, composable design that makes parser combinators educational and elegant.

## Current State

The parser combinator implementation currently supports:
- ✅ Simple commands (`echo hello`)
- ✅ Pipelines (`cmd1 | cmd2 | cmd3`)
- ✅ And-or lists (`cmd1 && cmd2 || cmd3`)
- ✅ Basic redirections (`cmd > file`)
- ❌ Control structures (if, while, for, case)
- ❌ Function definitions
- ❌ Complex shell features

## Phase 1: Core Building Blocks

### 1.1 Enhanced Combinator Primitives

We need to add several fundamental combinators that will make control structure parsing cleaner and more maintainable:

```python
def lazy(parser_factory: Callable[[], Parser[T]]) -> Parser[T]:
    """Lazy evaluation for recursive grammars."""
    # Defers parser construction until first use
    # Essential for self-referential grammars
    
def between(open_p: Parser, close_p: Parser, content_p: Parser[T]) -> Parser[T]:
    """Parse content between delimiters."""
    # Useful for: if...fi, while...done, case...esac
    
def skip(parser: Parser) -> Parser[None]:
    """Parse but discard result."""
    # Useful for keywords we need to match but don't need in AST
    
def fail_with(msg: str) -> Parser[None]:
    """Parser that always fails with custom message."""
    # Better error reporting for specific contexts
    
def try_parse(parser: Parser[T]) -> Parser[Optional[T]]:
    """Backtracking support - try parser without consuming on failure."""
    # Critical for handling ambiguous grammar points
```

### 1.2 Keyword and Token Helpers

Enhanced keyword matching for shell-specific needs:

```python
def keyword_token(word: str) -> Parser[Token]:
    """Match keyword as token, ensuring word boundaries."""
    # Prevents matching 'if' in 'diff'
    
def statement_terminator() -> Parser[Token]:
    """Match newline or semicolon."""
    # Common pattern in shell syntax
    
def do_separator() -> Parser[Token]:
    """Match 'do' with required separator."""
    # Handles: '; do', '\n do', etc.
    
def then_separator() -> Parser[Token]:
    """Match 'then' with required separator."""
    # Handles: '; then', '\n then', etc.
```

### 1.3 Statement List Parser

The statement list parser needs special attention as it's recursive and used throughout control structures:

```python
# Forward declaration pattern for mutual recursion
self.statement_list_forward = ForwardParser[StatementList]()
self.command_forward = ForwardParser[Command]()

# Later definition
self.statement_list_forward.define(
    separated_by(
        self.statement,
        self.statement_terminator
    ).map(lambda stmts: StatementList(statements=stmts))
)
```

## Phase 2: Control Structure Implementation

### 2.1 If Statement Combinator

The if statement has complex structure with optional elif and else branches:

```python
def build_if_statement() -> Parser[IfConditional]:
    """
    Grammar:
        if_statement = 'if' condition separator 'then' then_part
                      elif_parts? else_part? 'fi'
        elif_parts = ('elif' condition separator 'then' then_part)*
        else_part = 'else' else_body
    """
    
    # Keywords
    if_kw = keyword_token('if')
    then_kw = keyword_token('then')
    elif_kw = keyword_token('elif')
    else_kw = keyword_token('else')
    fi_kw = keyword_token('fi')
    
    # Condition is a statement list
    condition = self.statement_list
    
    # Main if/then part
    if_then = sequence(
        skip(if_kw),
        condition,
        skip(statement_terminator()),
        skip(then_kw),
        skip(statement_terminator()),
        self.statement_list
    ).map(lambda parts: (parts[0], parts[1]))
    
    # Elif parts (zero or more)
    elif_part = sequence(
        skip(elif_kw),
        condition,
        skip(statement_terminator()),
        skip(then_kw),
        skip(statement_terminator()),
        self.statement_list
    ).map(lambda parts: (parts[0], parts[1]))
    
    elif_parts = many(elif_part)
    
    # Optional else part
    else_part = sequence(
        skip(else_kw),
        skip(statement_terminator()),
        self.statement_list
    ).map(lambda parts: parts[0])
    
    # Complete if statement
    return sequence(
        if_then,
        elif_parts,
        optional(else_part),
        skip(fi_kw)
    ).map(lambda parts: IfConditional(
        condition=parts[0][0],
        then_part=parts[0][1],
        elif_parts=parts[1],
        else_part=parts[2]
    ))
```

### 2.2 While Loop Combinator

While loops are simpler but need proper context handling:

```python
def build_while_loop() -> Parser[WhileLoop]:
    """
    Grammar:
        while_loop = 'while' condition separator 'do' body 'done'
    """
    
    while_kw = keyword_token('while')
    do_kw = keyword_token('do')
    done_kw = keyword_token('done')
    
    return sequence(
        skip(while_kw),
        self.statement_list,  # condition
        skip(statement_terminator()),
        skip(do_kw),
        skip(statement_terminator()),
        self.statement_list,  # body
        skip(done_kw)
    ).map(lambda parts: WhileLoop(
        condition=parts[0],
        body=parts[1]
    ))
```

### 2.3 For Loop Combinators

For loops have two variants that need different parsing strategies:

```python
def build_traditional_for_loop() -> Parser[ForLoop]:
    """
    Grammar:
        for_loop = 'for' WORD 'in' items separator 'do' body 'done'
    """
    
    for_kw = keyword_token('for')
    in_kw = keyword_token('in')
    do_kw = keyword_token('do')
    done_kw = keyword_token('done')
    
    # Items can be words or strings
    item = self.word.or_else(self.string)
    items = many(item)
    
    return sequence(
        skip(for_kw),
        self.word,  # variable name
        skip(in_kw),
        items,
        skip(statement_terminator()),
        skip(do_kw),
        skip(statement_terminator()),
        self.statement_list,  # body
        skip(done_kw)
    ).map(lambda parts: ForLoop(
        variable=parts[0].value,
        items=[item.value for item in parts[1]],
        body=parts[2]
    ))

def build_c_style_for_loop() -> Parser[CStyleForLoop]:
    """
    Grammar:
        c_for_loop = 'for' '((' init? ';' condition? ';' update? '))' 
                     separator 'do' body 'done'
    """
    
    for_kw = keyword_token('for')
    double_lparen = literal('((')
    double_rparen = literal('))')
    semicolon = literal(';')
    do_kw = keyword_token('do')
    done_kw = keyword_token('done')
    
    # Arithmetic expressions (simplified for now)
    arith_expr = many(self.word.or_else(self.operator))
    
    return sequence(
        skip(for_kw),
        skip(double_lparen),
        optional(arith_expr),  # init
        skip(semicolon),
        optional(arith_expr),  # condition
        skip(semicolon),
        optional(arith_expr),  # update
        skip(double_rparen),
        skip(statement_terminator()),
        skip(do_kw),
        skip(statement_terminator()),
        self.statement_list,  # body
        skip(done_kw)
    ).map(lambda parts: CStyleForLoop(
        init_expr=' '.join(t.value for t in parts[0]) if parts[0] else None,
        condition_expr=' '.join(t.value for t in parts[1]) if parts[1] else None,
        update_expr=' '.join(t.value for t in parts[2]) if parts[2] else None,
        body=parts[3]
    ))

def build_for_loops() -> Parser[Union[ForLoop, CStyleForLoop]]:
    """Combined for loop parser that tries both variants."""
    # Use lookahead to distinguish
    c_style = try_parse(
        sequence(keyword_token('for'), literal('(('))
    ).then(lambda _: build_c_style_for_loop())
    
    traditional = build_traditional_for_loop()
    
    return c_style.or_else(traditional)
```

### 2.4 Case Statement Combinator

Case statements are the most complex control structure:

```python
def build_case_statement() -> Parser[CaseConditional]:
    """
    Grammar:
        case_statement = 'case' expr 'in' case_items 'esac'
        case_items = case_item*
        case_item = patterns ')' commands case_terminator
        patterns = pattern ('|' pattern)*
        case_terminator = ';;' | ';&' | ';;&'
    """
    
    case_kw = keyword_token('case')
    in_kw = keyword_token('in')
    esac_kw = keyword_token('esac')
    rparen = literal(')')
    pipe = literal('|')
    
    # Case terminators
    double_semi = literal(';;')
    semi_amp = literal(';&')
    semi_semi_amp = literal(';;&')
    case_terminator = double_semi.or_else(semi_amp).or_else(semi_semi_amp)
    
    # Pattern can be word or string
    pattern = self.word.or_else(self.string)
    patterns = separated_by(pattern, pipe)
    
    # Case item
    case_item = sequence(
        patterns,
        skip(rparen),
        self.statement_list,
        optional(case_terminator)
    ).map(lambda parts: CaseItem(
        patterns=[CasePattern(p.value) for p in parts[0]],
        commands=parts[1],
        terminator=parts[2].value if parts[2] else ';;'
    ))
    
    return sequence(
        skip(case_kw),
        self.word,  # expression
        skip(in_kw),
        skip(optional(statement_terminator())),
        many(case_item),
        skip(esac_kw)
    ).map(lambda parts: CaseConditional(
        expr=parts[0].value,
        items=parts[1]
    ))
```

## Phase 3: Implementation Strategy

### 3.1 Code Organization

The implementation will be organized within `parser_combinator_example.py`:

```python
class ParserCombinatorShellParser(AbstractShellParser):
    def _build_grammar(self):
        # Existing grammar setup...
        
        # Add forward declarations
        self._setup_forward_declarations()
        
        # Build control structures
        self.if_statement = self._build_if_statement()
        self.while_loop = self._build_while_loop()
        self.for_loop = self._build_for_loops()
        self.case_statement = self._build_case_statement()
        
        # Add to main grammar
        self.control_structure = (
            self.if_statement
            .or_else(self.while_loop)
            .or_else(self.for_loop)
            .or_else(self.case_statement)
        )
        
        # Update command to include control structures
        self.command = self.simple_command.or_else(self.control_structure)
```

### 3.2 Forward Declaration Pattern

Handle circular dependencies in the grammar:

```python
def _setup_forward_declarations(self):
    """Setup forward declarations for recursive grammar rules."""
    self.statement_list_forward = ForwardParser[StatementList]()
    self.command_forward = ForwardParser[Command]()
    self.statement_forward = ForwardParser[Statement]()
    
    # Define them after all components are ready
    def _complete_forward_declarations(self):
        self.statement_list_forward.define(self.statement_list)
        self.command_forward.define(self.command)
        self.statement_forward.define(self.statement)
```

### 3.3 Error Handling

Enhance error messages for control structures:

```python
def with_error_context(parser: Parser[T], context: str) -> Parser[T]:
    """Add context to parser errors."""
    def contextualized_parse(tokens, pos):
        result = parser.parse(tokens, pos)
        if not result.success and result.error:
            result.error = f"{context}: {result.error}"
        return result
    return Parser(contextualized_parse)

# Usage:
if_statement = with_error_context(
    build_if_statement(),
    "In if statement"
)
```

## Phase 4: Testing Strategy

### 4.1 Unit Tests

Create comprehensive unit tests for each control structure:

```python
def test_if_statement_basic():
    """Test basic if/then/fi parsing."""
    tokens = tokenize("if true; then echo hello; fi")
    parser = ParserCombinatorShellParser()
    ast = parser.parse(tokens)
    
    assert isinstance(ast.statements[0], IfConditional)
    assert len(ast.statements[0].then_part.statements) == 1

def test_if_statement_elif_else():
    """Test if/elif/else parsing."""
    tokens = tokenize("""
        if test -f file; then
            echo "file exists"
        elif test -d file; then
            echo "directory exists"
        else
            echo "not found"
        fi
    """)
    parser = ParserCombinatorShellParser()
    ast = parser.parse(tokens)
    
    if_stmt = ast.statements[0]
    assert len(if_stmt.elif_parts) == 1
    assert if_stmt.else_part is not None
```

### 4.2 Integration Tests

Test control structures in complex scenarios:

```python
def test_nested_control_structures():
    """Test nested control structures."""
    tokens = tokenize("""
        for i in 1 2 3; do
            if test $i -eq 2; then
                echo "Found 2"
            fi
        done
    """)
    
def test_control_in_pipeline():
    """Test control structures in pipelines."""
    tokens = tokenize("if true; then cat file; fi | grep pattern")
    
def test_control_with_redirections():
    """Test control structures with redirections."""
    tokens = tokenize("while read line; do echo $line; done < input.txt")
```

### 4.3 Comparison Tests

Ensure parity with recursive descent parser:

```python
def test_ast_comparison():
    """Compare ASTs from both parsers."""
    test_cases = [
        "if true; then echo yes; fi",
        "while test -f lock; do sleep 1; done",
        "for x in a b c; do echo $x; done",
        "case $1 in a) echo A;; b|c) echo BC;; esac"
    ]
    
    for test in test_cases:
        tokens = tokenize(test)
        
        rd_parser = RecursiveDescentAdapter()
        pc_parser = ParserCombinatorShellParser()
        
        rd_ast = rd_parser.parse(tokens.copy())
        pc_ast = pc_parser.parse(tokens.copy())
        
        assert_ast_equivalent(rd_ast, pc_ast)
```

## Phase 5: Performance Optimizations

### 5.1 Memoization

Add memoization for expensive parsers:

```python
def memoize(parser: Parser[T]) -> Parser[T]:
    """Cache parser results by position."""
    cache = {}
    
    def memoized_parse(tokens, pos):
        key = (id(parser), pos)
        if key in cache:
            return cache[key]
        result = parser.parse(tokens, pos)
        cache[key] = result
        return result
    
    return Parser(memoized_parse)

# Apply to expensive parsers
self.statement_list = memoize(build_statement_list())
```

### 5.2 Left Factoring

Optimize common prefixes:

```python
# Instead of:
for_loop = traditional_for.or_else(c_style_for)

# Use lookahead:
for_loop = sequence(
    keyword_token('for'),
    lookahead(literal('((').or_else(word))
).then(lambda result: 
    c_style_for if result[1].value == '((' else traditional_for
)
```

## Implementation Timeline

### Day 1: Foundation
- [ ] Implement helper combinators (lazy, between, etc.)
- [ ] Add keyword and token helpers
- [ ] Set up forward declaration infrastructure
- [ ] Begin if statement implementation

### Day 2: If Statement & While Loop
- [ ] Complete if/then/elif/else/fi parser
- [ ] Implement while/do/done parser
- [ ] Add comprehensive tests for both
- [ ] Handle nested statement lists

### Day 3: For Loops
- [ ] Implement traditional for loop
- [ ] Implement C-style for loop
- [ ] Add lookahead for disambiguation
- [ ] Test with various item lists and quotes

### Day 4: Case Statement
- [ ] Implement pattern parsing
- [ ] Handle multiple patterns per case
- [ ] Support all case terminators
- [ ] Add default case handling

### Day 5: Integration & Polish
- [ ] Update main grammar with all control structures
- [ ] Run full test suite
- [ ] Compare with recursive descent parser
- [ ] Performance optimization
- [ ] Documentation updates

## Success Criteria

1. **Feature Parity**: All control structures parse correctly
2. **AST Compatibility**: Generated ASTs match recursive descent parser
3. **Error Handling**: Clear error messages for malformed input
4. **Performance**: Reasonable performance for typical scripts
5. **Maintainability**: Clean, composable implementation
6. **Test Coverage**: Comprehensive test suite passes

## Future Enhancements

After control structures are complete:
- Function definitions
- Arithmetic expressions
- Advanced expansions
- Here documents
- Coprocesses

This implementation will demonstrate the power and elegance of parser combinators while providing a fully functional shell parser for educational comparison with the recursive descent approach.