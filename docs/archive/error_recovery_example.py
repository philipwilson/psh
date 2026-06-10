#!/usr/bin/env python3
"""
Example implementation of Error Recovery for PSH Parser.

This demonstrates how error recovery could work in the PSH parser,
allowing it to continue parsing after encountering syntax errors.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple
from enum import Enum, auto


# Token types
class TokenType(Enum):
    WORD = auto()
    IF = auto()
    THEN = auto()
    ELSE = auto()
    FI = auto()
    SEMICOLON = auto()
    NEWLINE = auto()
    STRING = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    EOF = auto()
    PIPE = auto()


@dataclass
class Token:
    type: TokenType
    value: str
    line: int
    column: int


# AST Nodes
@dataclass
class ASTNode:
    pass


@dataclass
class ErrorNode(ASTNode):
    """Node representing a parse error."""
    message: str
    tokens: List[Token]
    expected: List[TokenType]
    partial_node: Optional[ASTNode] = None
    line: int = 0
    column: int = 0


@dataclass
class SimpleCommand(ASTNode):
    args: List[str]


@dataclass
class IfStatement(ASTNode):
    condition: Optional[ASTNode]
    then_part: Optional[ASTNode]
    else_part: Optional[ASTNode] = None


@dataclass
class CommandList(ASTNode):
    commands: List[ASTNode]


# Parser with error recovery
class ErrorRecoveringParser:
    """Parser that can recover from syntax errors."""
    
    def __init__(self, tokens: List[Token], source_lines: List[str]):
        self.tokens = tokens
        self.source_lines = source_lines
        self.current = 0
        self.errors: List[ErrorNode] = []
        self.recover_mode = True  # Enable error recovery
    
    def peek(self) -> Optional[Token]:
        """Look at current token."""
        if self.current < len(self.tokens):
            return self.tokens[self.current]
        return None
    
    def advance(self) -> Optional[Token]:
        """Consume current token."""
        token = self.peek()
        if self.current < len(self.tokens) - 1:
            self.current += 1
        return token
    
    def match(self, *types: TokenType) -> bool:
        """Check if current token matches any type."""
        token = self.peek()
        return token and token.type in types
    
    def parse(self) -> Tuple[CommandList, List[ErrorNode]]:
        """Parse with error recovery."""
        commands = []
        
        while not self._at_end():
            try:
                if self.match(TokenType.IF):
                    commands.append(self.parse_if_statement())
                elif self.match(TokenType.WORD):
                    commands.append(self.parse_simple_command())
                else:
                    # Skip unexpected token
                    token = self.advance()
                    error = ErrorNode(
                        message=f"Unexpected token: {token.value}",
                        tokens=[token],
                        expected=[TokenType.WORD, TokenType.IF],
                        line=token.line,
                        column=token.column
                    )
                    self.errors.append(error)
                    commands.append(error)
                
                # Skip separators
                while self.match(TokenType.SEMICOLON, TokenType.NEWLINE):
                    self.advance()
                    
            except ParseError as e:
                if self.recover_mode:
                    # Record error and recover
                    error_node = e.to_error_node()
                    self.errors.append(error_node)
                    commands.append(error_node)
                    
                    # Synchronize to next statement
                    self._synchronize()
                else:
                    raise
        
        return CommandList(commands), self.errors
    
    def parse_if_statement(self) -> IfStatement:
        """Parse if statement with error recovery."""
        start_token = self.advance()  # consume 'if'
        
        # Parse condition
        condition = None
        try:
            condition = self.parse_test_condition()
        except ParseError as e:
            if self.recover_mode:
                # Report missing condition
                self.errors.append(ErrorNode(
                    message="Missing or invalid condition after 'if'",
                    tokens=self._collect_until(TokenType.THEN),
                    expected=[TokenType.LBRACKET],
                    line=start_token.line,
                    column=start_token.column
                ))
                # Try to find 'then'
                self._skip_until(TokenType.THEN)
            else:
                raise
        
        # Expect 'then'
        then_part = None
        if self.match(TokenType.THEN):
            self.advance()
            then_part = self.parse_command_list_until(
                {TokenType.ELSE, TokenType.FI}
            )
        else:
            # Missing 'then'
            error = ErrorNode(
                message="Missing 'then' after if condition",
                tokens=[self.peek()] if self.peek() else [],
                expected=[TokenType.THEN],
                line=self.peek().line if self.peek() else start_token.line,
                column=self.peek().column if self.peek() else 0
            )
            self.errors.append(error)
            
            # Try to parse commands anyway
            then_part = self.parse_command_list_until(
                {TokenType.ELSE, TokenType.FI}
            )
        
        # Optional else
        else_part = None
        if self.match(TokenType.ELSE):
            self.advance()
            else_part = self.parse_command_list_until({TokenType.FI})
        
        # Expect 'fi'
        if self.match(TokenType.FI):
            self.advance()
        else:
            # Missing 'fi'
            error = ErrorNode(
                message="Missing 'fi' to close if statement",
                tokens=[self.peek()] if self.peek() else [],
                expected=[TokenType.FI],
                line=self.peek().line if self.peek() else start_token.line,
                column=self.peek().column if self.peek() else 0
            )
            self.errors.append(error)
        
        return IfStatement(condition, then_part, else_part)
    
    def parse_test_condition(self) -> SimpleCommand:
        """Parse test condition like [ -f file ]."""
        if not self.match(TokenType.LBRACKET):
            raise ParseError(
                "Expected '[' to start test condition",
                self.peek(),
                [TokenType.LBRACKET]
            )
        
        self.advance()  # consume '['
        
        # Collect arguments until ]
        args = ['[']
        while not self._at_end() and not self.match(TokenType.RBRACKET):
            if self.match(TokenType.WORD, TokenType.STRING):
                args.append(self.advance().value)
            else:
                # Unexpected token in test
                token = self.advance()
                raise ParseError(
                    f"Unexpected token in test condition: {token.value}",
                    token,
                    [TokenType.WORD, TokenType.RBRACKET]
                )
        
        if self.match(TokenType.RBRACKET):
            self.advance()
            args.append(']')
        else:
            # Missing closing bracket
            raise ParseError(
                "Missing ']' to close test condition",
                self.peek(),
                [TokenType.RBRACKET]
            )
        
        return SimpleCommand(args)
    
    def parse_simple_command(self) -> SimpleCommand:
        """Parse a simple command."""
        args = []
        
        while self.match(TokenType.WORD, TokenType.STRING):
            args.append(self.advance().value)
        
        if not args:
            raise ParseError(
                "Expected command",
                self.peek(),
                [TokenType.WORD]
            )
        
        return SimpleCommand(args)
    
    def parse_command_list_until(self, stop_tokens: Set[TokenType]) -> CommandList:
        """Parse commands until we hit a stop token."""
        commands = []
        
        while not self._at_end() and not self.match(*stop_tokens):
            try:
                if self.match(TokenType.WORD):
                    commands.append(self.parse_simple_command())
                elif self.match(TokenType.IF):
                    commands.append(self.parse_if_statement())
                else:
                    # Skip unexpected token
                    self.advance()
                
                # Skip separators
                while self.match(TokenType.SEMICOLON, TokenType.NEWLINE):
                    self.advance()
                    
            except ParseError as e:
                if self.recover_mode:
                    error_node = e.to_error_node()
                    self.errors.append(error_node)
                    commands.append(error_node)
                    self._synchronize()
                else:
                    raise
        
        return CommandList(commands)
    
    def _synchronize(self):
        """Synchronize after parse error."""
        # Skip tokens until we find a statement boundary
        sync_tokens = {
            TokenType.SEMICOLON,
            TokenType.NEWLINE,
            TokenType.FI,
            TokenType.THEN,
            TokenType.ELSE,
            TokenType.EOF
        }
        
        while not self._at_end() and not self.match(*sync_tokens):
            self.advance()
        
        # Consume sync token if it's a separator
        if self.match(TokenType.SEMICOLON, TokenType.NEWLINE):
            self.advance()
    
    def _skip_until(self, target: TokenType) -> bool:
        """Skip tokens until we find target."""
        while not self._at_end():
            if self.match(target):
                return True
            self.advance()
        return False
    
    def _collect_until(self, target: TokenType) -> List[Token]:
        """Collect tokens until target."""
        tokens = []
        while not self._at_end() and not self.match(target):
            tokens.append(self.advance())
        return tokens
    
    def _at_end(self) -> bool:
        """Check if at end of input."""
        return self.peek() is None or self.match(TokenType.EOF)


@dataclass
class ParseError(Exception):
    """Parse error with context."""
    message: str
    token: Optional[Token]
    expected: List[TokenType]
    
    def to_error_node(self) -> ErrorNode:
        """Convert to error node."""
        return ErrorNode(
            message=self.message,
            tokens=[self.token] if self.token else [],
            expected=self.expected,
            line=self.token.line if self.token else 0,
            column=self.token.column if self.token else 0
        )


def format_errors(errors: List[ErrorNode], source_lines: List[str]) -> str:
    """Format errors with source context."""
    if not errors:
        return "No errors found."
    
    output = [f"Found {len(errors)} error(s):\n"]
    
    for i, error in enumerate(errors, 1):
        output.append(f"Error {i}: {error.message}")
        output.append(f"  at line {error.line}, column {error.column}")
        
        # Show source line
        if 0 <= error.line - 1 < len(source_lines):
            line = source_lines[error.line - 1]
            output.append(f"  {error.line} | {line}")
            output.append(f"  {' ' * len(str(error.line))} | {' ' * error.column}^")
        
        if error.expected:
            expected_str = ", ".join(t.name for t in error.expected)
            output.append(f"  Expected: {expected_str}")
        
        output.append("")
    
    return "\n".join(output)


def demo_error_recovery():
    """Demonstrate error recovery with various syntax errors."""
    
    # Test cases with errors
    test_cases = [
        # Missing 'then'
        """if [ -f /etc/passwd ]
    echo "File exists"
fi""",
        
        # Missing closing bracket
        """if [ -f /etc/passwd
then
    echo "File exists"
fi""",
        
        # Missing 'fi'
        """if [ -f file ]
then
    echo "Found"
else
    echo "Not found"
""",
        
        # Multiple errors
        """if [ -f file
    echo "Missing then and bracket"
echo "Another command"
if [ -d dir ]
then
    echo "Dir exists"
"""
    ]
    
    for i, source in enumerate(test_cases, 1):
        print(f"\n{'=' * 60}")
        print(f"Test Case {i}:")
        print(f"{'=' * 60}")
        print("Source:")
        print(source)
        print("\n" + "-" * 40)
        
        # Tokenize (simplified for demo)
        tokens = simple_tokenize(source)
        source_lines = source.split('\n')
        
        # Parse with error recovery
        parser = ErrorRecoveringParser(tokens, source_lines)
        ast, errors = parser.parse()
        
        # Show errors
        print("\nErrors found:")
        print(format_errors(errors, source_lines))
        
        # Show recovered AST structure
        print("Recovered AST structure:")
        print_ast(ast, indent=0)


def simple_tokenize(source: str) -> List[Token]:
    """Simple tokenizer for demo purposes."""
    tokens = []
    lines = source.split('\n')
    
    keywords = {'if', 'then', 'else', 'fi'}
    
    for line_no, line in enumerate(lines, 1):
        col = 0
        words = line.split()
        
        for word in words:
            token_type = TokenType.WORD
            
            if word in keywords:
                token_type = TokenType[word.upper()]
            elif word == '[':
                token_type = TokenType.LBRACKET
            elif word == ']':
                token_type = TokenType.RBRACKET
            elif word == ';':
                token_type = TokenType.SEMICOLON
            elif word.startswith('"') and word.endswith('"'):
                token_type = TokenType.STRING
            
            tokens.append(Token(token_type, word, line_no, col))
            col += len(word) + 1
        
        if words:  # Add newline after non-empty lines
            tokens.append(Token(TokenType.NEWLINE, '\n', line_no, col))
    
    tokens.append(Token(TokenType.EOF, '', len(lines) + 1, 0))
    return tokens


def print_ast(node: ASTNode, indent: int = 0):
    """Simple AST printer."""
    prefix = "  " * indent
    
    if isinstance(node, ErrorNode):
        print(f"{prefix}ERROR: {node.message}")
    elif isinstance(node, SimpleCommand):
        print(f"{prefix}Command: {' '.join(node.args)}")
    elif isinstance(node, IfStatement):
        print(f"{prefix}If:")
        if node.condition:
            print(f"{prefix}  Condition:")
            print_ast(node.condition, indent + 2)
        if node.then_part:
            print(f"{prefix}  Then:")
            print_ast(node.then_part, indent + 2)
        if node.else_part:
            print(f"{prefix}  Else:")
            print_ast(node.else_part, indent + 2)
    elif isinstance(node, CommandList):
        for cmd in node.commands:
            print_ast(cmd, indent)


if __name__ == '__main__':
    demo_error_recovery()