# Parser Experimentation Framework Design

## Overview

This document describes a framework for experimenting with alternative parser implementations in PSH while maintaining the existing recursive descent parser. The design allows switching between different parsing strategies at runtime for educational comparison.

## Goals

1. **Preserve Existing Parser**: Keep the hand-coded recursive descent parser as the default
2. **Enable Experimentation**: Allow easy integration of alternative parser implementations
3. **Educational Value**: Make it easy to compare different parsing approaches
4. **Runtime Switching**: Select parser implementation at runtime
5. **Consistent Interface**: All parsers produce the same AST format

## Architecture

### Abstract Parser Interface

```python
from abc import ABC, abstractmethod
from typing import List, Optional, Union
from psh.ast_nodes import TopLevel, CommandList
from psh.token_types import Token

class AbstractShellParser(ABC):
    """Abstract base class for all parser implementations."""
    
    @abstractmethod
    def parse(self, tokens: List[Token]) -> Union[TopLevel, CommandList]:
        """Parse tokens into an AST."""
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Return parser implementation name."""
        pass
    
    @abstractmethod
    def get_description(self) -> str:
        """Return parser description for educational purposes."""
        pass
    
    def get_characteristics(self) -> dict:
        """Return parser characteristics for comparison."""
        return {
            "type": "unknown",
            "complexity": "unknown",
            "error_recovery": False,
            "backtracking": False,
            "memoization": False
        }
```

### Parser Registry

```python
class ParserRegistry:
    """Registry for available parser implementations."""
    
    _parsers: Dict[str, Type[AbstractShellParser]] = {}
    
    @classmethod
    def register(cls, name: str, parser_class: Type[AbstractShellParser]):
        """Register a parser implementation."""
        cls._parsers[name] = parser_class
    
    @classmethod
    def get(cls, name: str) -> Optional[Type[AbstractShellParser]]:
        """Get a parser implementation by name."""
        return cls._parsers.get(name)
    
    @classmethod
    def list_parsers(cls) -> List[str]:
        """List all registered parser names."""
        return list(cls._parsers.keys())
    
    @classmethod
    def get_parser_info(cls) -> List[dict]:
        """Get information about all parsers."""
        info = []
        for name, parser_class in cls._parsers.items():
            parser = parser_class()
            info.append({
                "name": name,
                "description": parser.get_description(),
                "characteristics": parser.get_characteristics()
            })
        return info
```

### Parser Strategy Pattern

```python
class ParserStrategy:
    """Strategy pattern for parser selection."""
    
    def __init__(self, parser_name: str = "recursive_descent"):
        self._parser_name = parser_name
        self._parser = None
        self._load_parser()
    
    def _load_parser(self):
        """Load the selected parser implementation."""
        parser_class = ParserRegistry.get(self._parser_name)
        if not parser_class:
            raise ValueError(f"Unknown parser: {self._parser_name}")
        self._parser = parser_class()
    
    def parse(self, tokens: List[Token]) -> Union[TopLevel, CommandList]:
        """Parse using the selected implementation."""
        return self._parser.parse(tokens)
    
    def switch_parser(self, parser_name: str):
        """Switch to a different parser implementation."""
        self._parser_name = parser_name
        self._load_parser()
```

## Implementation Examples

### 1. Recursive Descent Parser (Existing)

```python
from psh.parser import Parser as RecursiveDescentParser

class RecursiveDescentParserAdapter(AbstractShellParser):
    """Adapter for existing recursive descent parser."""
    
    def parse(self, tokens: List[Token]) -> Union[TopLevel, CommandList]:
        parser = RecursiveDescentParser(tokens)
        return parser.parse()
    
    def get_name(self) -> str:
        return "recursive_descent"
    
    def get_description(self) -> str:
        return "Hand-coded recursive descent parser with excellent error messages"
    
    def get_characteristics(self) -> dict:
        return {
            "type": "recursive_descent",
            "complexity": "medium",
            "error_recovery": True,
            "backtracking": "limited",
            "memoization": False,
            "hand_coded": True
        }

# Register the existing parser
ParserRegistry.register("recursive_descent", RecursiveDescentParserAdapter)
ParserRegistry.register("default", RecursiveDescentParserAdapter)
```

### 2. Parser Combinator Implementation

```python
class ParserCombinatorShellParser(AbstractShellParser):
    """Parser combinator-based shell parser."""
    
    def __init__(self):
        self._build_parser()
    
    def _build_parser(self):
        """Build parser using combinators."""
        # Parser combinator definitions
        self.word = token('WORD')
        self.pipe = token('PIPE')
        self.semicolon = token('SEMICOLON')
        
        # Grammar rules using combinators
        self.simple_command = sequence(
            self.word,
            many(self.word)
        ).map(self._build_simple_command)
        
        self.pipeline = sequence(
            self.simple_command,
            many(sequence(self.pipe, self.simple_command))
        ).map(self._build_pipeline)
        
        self.statement_list = separated_by(
            self.pipeline,
            self.semicolon
        ).map(self._build_statement_list)
    
    def parse(self, tokens: List[Token]) -> CommandList:
        result = self.statement_list.parse(TokenStream(tokens))
        if result.is_success():
            return result.value
        else:
            raise ParseError(result.error)
    
    def get_name(self) -> str:
        return "parser_combinator"
    
    def get_description(self) -> str:
        return "Functional parser built from composable combinators"
    
    def get_characteristics(self) -> dict:
        return {
            "type": "parser_combinator",
            "complexity": "high",
            "error_recovery": False,
            "backtracking": True,
            "memoization": True,
            "functional": True
        }
```

### 3. Grammar DSL Parser

```python
class GrammarDSLShellParser(AbstractShellParser):
    """Parser generated from grammar DSL."""
    
    GRAMMAR = """
    # Shell Grammar DSL
    
    statement_list = statement (";" statement)* ;
    statement = pipeline ;
    pipeline = command ("|" command)* ;
    command = word+ ;
    word = WORD | STRING ;
    """
    
    def __init__(self):
        self._parser = self._generate_parser_from_grammar()
    
    def _generate_parser_from_grammar(self):
        """Generate parser from grammar DSL."""
        grammar = Grammar(self.GRAMMAR)
        return grammar.build_parser()
    
    def parse(self, tokens: List[Token]) -> CommandList:
        return self._parser.parse(tokens)
    
    def get_name(self) -> str:
        return "grammar_dsl"
    
    def get_description(self) -> str:
        return "Parser generated from BNF-like grammar DSL"
    
    def get_characteristics(self) -> dict:
        return {
            "type": "grammar_based",
            "complexity": "low",
            "error_recovery": "automatic",
            "backtracking": True,
            "memoization": "optional",
            "generated": True
        }
```

### 4. Pratt Parser (Operator Precedence)

```python
class PrattShellParser(AbstractShellParser):
    """Pratt parser for operator precedence handling."""
    
    def __init__(self):
        self._init_precedence_table()
    
    def _init_precedence_table(self):
        """Initialize operator precedence table."""
        self.precedences = {
            'PIPE': 10,      # | pipeline
            'AND_IF': 20,    # && operator  
            'OR_IF': 20,     # || operator
            'SEMICOLON': 30, # ; separator
        }
    
    def parse(self, tokens: List[Token]) -> CommandList:
        self.tokens = tokens
        self.position = 0
        return self._parse_expression(0)
    
    def get_name(self) -> str:
        return "pratt_parser"
    
    def get_description(self) -> str:
        return "Top-down operator precedence parser (Pratt parser)"
```

## Integration Points

### 1. Shell Integration

```python
# In psh/shell.py

class Shell:
    def __init__(self, parser_impl="default", ...):
        self.parser_strategy = ParserStrategy(parser_impl)
    
    def set_parser(self, parser_name: str):
        """Switch to a different parser implementation."""
        self.parser_strategy.switch_parser(parser_name)
        print(f"Switched to {parser_name} parser")
    
    def execute_string(self, command_string: str):
        tokens = self.lexer.tokenize(command_string)
        
        # Use selected parser implementation
        ast = self.parser_strategy.parse(tokens)
        
        # Rest of execution remains the same
        return self.executor.execute(ast)
```

### 2. Parser Selection Command

```python
@builtin
class ParserSelectBuiltin(Builtin):
    """Select parser implementation."""
    name = "parser-select"
    
    def execute(self, args: List[str], shell: 'Shell') -> int:
        if len(args) == 1:
            # List available parsers
            print("Available parsers:")
            for info in ParserRegistry.get_parser_info():
                print(f"  {info['name']}: {info['description']}")
            current = shell.parser_strategy._parser_name
            print(f"\nCurrent parser: {current}")
            return 0
        
        parser_name = args[1]
        if parser_name not in ParserRegistry.list_parsers():
            self.error(f"Unknown parser: {parser_name}", shell)
            return 1
        
        shell.set_parser(parser_name)
        return 0
```

### 3. Parser Comparison Command

```python
@builtin  
class ParserCompareBuiltin(Builtin):
    """Compare different parser implementations."""
    name = "parser-compare"
    
    def execute(self, args: List[str], shell: 'Shell') -> int:
        if len(args) < 2:
            self.error("Usage: parser-compare 'command'", shell)
            return 1
        
        command = args[1]
        tokens = shell.lexer.tokenize(command)
        
        print(f"Comparing parsers for: {command}\n")
        
        for parser_name in ParserRegistry.list_parsers():
            parser_class = ParserRegistry.get(parser_name)
            parser = parser_class()
            
            print(f"=== {parser.get_name()} ===")
            print(f"Description: {parser.get_description()}")
            
            try:
                start_time = time.time()
                ast = parser.parse(tokens.copy())
                elapsed = time.time() - start_time
                
                print(f"✓ Parsed successfully in {elapsed:.4f}s")
                print(f"AST type: {type(ast).__name__}")
                
            except Exception as e:
                print(f"✗ Parse failed: {e}")
            
            print()
        
        return 0
```

## Usage Examples

### Interactive Parser Experimentation

```bash
# List available parsers
$ parser-select
Available parsers:
  recursive_descent: Hand-coded recursive descent parser with excellent error messages
  parser_combinator: Functional parser built from composable combinators
  grammar_dsl: Parser generated from BNF-like grammar DSL
  pratt_parser: Top-down operator precedence parser (Pratt parser)

Current parser: recursive_descent

# Switch to parser combinator
$ parser-select parser_combinator
Switched to parser_combinator parser

# Try parsing with new parser
$ echo hello | grep world
hello

# Compare parsers
$ parser-compare 'echo hello | grep world && echo done'
Comparing parsers for: echo hello | grep world && echo done

=== recursive_descent ===
Description: Hand-coded recursive descent parser with excellent error messages
✓ Parsed successfully in 0.0012s
AST type: CommandList

=== parser_combinator ===
Description: Functional parser built from composable combinators  
✓ Parsed successfully in 0.0023s
AST type: CommandList

=== grammar_dsl ===
Description: Parser generated from BNF-like grammar DSL
✓ Parsed successfully in 0.0019s
AST type: CommandList
```

### Programmatic Usage

```python
# Create shell with specific parser
shell = Shell(parser_impl="parser_combinator")

# Switch parser at runtime
shell.set_parser("grammar_dsl")

# Execute with current parser
shell.execute_string("echo hello")
```

## Benefits

1. **Educational**: Compare parsing techniques side-by-side
2. **Experimental**: Test new parsing approaches easily
3. **Modular**: Clean separation between parser implementations
4. **Consistent**: All parsers produce the same AST format
5. **Extensible**: Easy to add new parser implementations

## Implementation Path

1. Create abstract parser interface
2. Implement parser registry
3. Adapt existing parser to new interface
4. Create example alternative parsers
5. Add shell integration
6. Implement selection commands
7. Create comparison tools
8. Document examples

This framework enables rich experimentation with different parsing approaches while maintaining the stability of the existing implementation.