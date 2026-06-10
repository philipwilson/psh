#!/usr/bin/env python3
"""
Example implementation of the Visitor Pattern for PSH AST.

This is a proof-of-concept showing how the visitor pattern could be
implemented for PSH. It's not integrated into the main codebase but
demonstrates the design principles.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, List, Optional, Dict
from enum import Enum, auto


# Simplified AST node definitions for the example
@dataclass
class ASTNode:
    """Base class for all AST nodes."""
    pass


@dataclass
class SimpleCommand(ASTNode):
    """A simple command with arguments."""
    args: List[str]
    redirects: List['Redirect'] = None


@dataclass
class Pipeline(ASTNode):
    """A pipeline of commands."""
    commands: List[SimpleCommand]


@dataclass
class IfStatement(ASTNode):
    """An if/then/else statement."""
    condition: 'CommandList'
    then_part: 'CommandList'
    else_part: Optional['CommandList'] = None


@dataclass
class ForLoop(ASTNode):
    """A for loop."""
    variable: str
    items: List[str]
    body: 'CommandList'


@dataclass
class CommandList(ASTNode):
    """A list of commands."""
    commands: List[ASTNode]


@dataclass
class Redirect(ASTNode):
    """An I/O redirect."""
    type: str  # '>', '<', '>>', etc.
    target: str
    fd: Optional[int] = None


# Base Visitor Class
class ASTVisitor(ABC):
    """Base class for AST visitors using double dispatch."""
    
    def visit(self, node: ASTNode) -> Any:
        """Dispatch to the appropriate visit method."""
        method_name = f'visit_{node.__class__.__name__}'
        visitor = getattr(self, method_name, self.generic_visit)
        return visitor(node)
    
    def generic_visit(self, node: ASTNode) -> Any:
        """Called if no explicit visitor method exists for a node."""
        raise Exception(f'No visit_{node.__class__.__name__} method defined')


# Concrete Visitor: Pretty Printer
class PrettyPrintVisitor(ASTVisitor):
    """Visitor that pretty-prints the AST."""
    
    def __init__(self, indent: int = 2):
        super().__init__()
        self.indent = indent
        self.level = 0
    
    def _indent(self) -> str:
        """Get current indentation."""
        return ' ' * (self.level * self.indent)
    
    def visit_SimpleCommand(self, node: SimpleCommand) -> str:
        """Pretty print a simple command."""
        result = self._indent() + ' '.join(node.args)
        
        if node.redirects:
            for redirect in node.redirects:
                result += f" {self.visit(redirect)}"
        
        return result
    
    def visit_Pipeline(self, node: Pipeline) -> str:
        """Pretty print a pipeline."""
        parts = []
        for i, cmd in enumerate(node.commands):
            if i > 0:
                parts.append(' | ')
            # Don't indent pipeline components
            parts.append(' '.join(cmd.args))
        
        return self._indent() + ''.join(parts)
    
    def visit_IfStatement(self, node: IfStatement) -> str:
        """Pretty print an if statement."""
        lines = []
        
        lines.append(self._indent() + 'if')
        self.level += 1
        lines.append(self.visit(node.condition))
        self.level -= 1
        
        lines.append(self._indent() + 'then')
        self.level += 1
        lines.append(self.visit(node.then_part))
        self.level -= 1
        
        if node.else_part:
            lines.append(self._indent() + 'else')
            self.level += 1
            lines.append(self.visit(node.else_part))
            self.level -= 1
        
        lines.append(self._indent() + 'fi')
        
        return '\n'.join(lines)
    
    def visit_ForLoop(self, node: ForLoop) -> str:
        """Pretty print a for loop."""
        lines = []
        
        items_str = ' '.join(f'"{item}"' if ' ' in item else item 
                           for item in node.items)
        lines.append(f"{self._indent()}for {node.variable} in {items_str}")
        lines.append(self._indent() + 'do')
        
        self.level += 1
        lines.append(self.visit(node.body))
        self.level -= 1
        
        lines.append(self._indent() + 'done')
        
        return '\n'.join(lines)
    
    def visit_CommandList(self, node: CommandList) -> str:
        """Pretty print a command list."""
        lines = []
        for cmd in node.commands:
            lines.append(self.visit(cmd))
        return '\n'.join(lines)
    
    def visit_Redirect(self, node: Redirect) -> str:
        """Pretty print a redirect."""
        if node.fd is not None:
            return f"{node.fd}{node.type}{node.target}"
        return f"{node.type}{node.target}"


# Concrete Visitor: Command Counter
class CommandCounterVisitor(ASTVisitor):
    """Visitor that counts different types of commands."""
    
    def __init__(self):
        self.counts = {
            'simple_commands': 0,
            'pipelines': 0,
            'if_statements': 0,
            'for_loops': 0,
            'redirects': 0
        }
    
    def visit_SimpleCommand(self, node: SimpleCommand) -> None:
        """Count a simple command."""
        self.counts['simple_commands'] += 1
        
        if node.redirects:
            for redirect in node.redirects:
                self.visit(redirect)
    
    def visit_Pipeline(self, node: Pipeline) -> None:
        """Count a pipeline."""
        self.counts['pipelines'] += 1
        
        # Count commands in pipeline
        for cmd in node.commands:
            self.visit(cmd)
    
    def visit_IfStatement(self, node: IfStatement) -> None:
        """Count an if statement."""
        self.counts['if_statements'] += 1
        
        # Count commands in condition and branches
        self.visit(node.condition)
        self.visit(node.then_part)
        if node.else_part:
            self.visit(node.else_part)
    
    def visit_ForLoop(self, node: ForLoop) -> None:
        """Count a for loop."""
        self.counts['for_loops'] += 1
        
        # Count commands in body
        self.visit(node.body)
    
    def visit_CommandList(self, node: CommandList) -> None:
        """Count commands in a list."""
        for cmd in node.commands:
            self.visit(cmd)
    
    def visit_Redirect(self, node: Redirect) -> None:
        """Count a redirect."""
        self.counts['redirects'] += 1
    
    def get_summary(self) -> str:
        """Get a summary of counts."""
        lines = ["Command counts:"]
        for cmd_type, count in self.counts.items():
            if count > 0:
                lines.append(f"  {cmd_type}: {count}")
        return '\n'.join(lines)


# Concrete Visitor: Builtin Detector
class BuiltinDetectorVisitor(ASTVisitor):
    """Visitor that finds all builtin commands used."""
    
    # Known builtins
    BUILTINS = {
        'cd', 'echo', 'exit', 'export', 'pwd', 'read', 'source',
        'unset', 'alias', 'unalias', 'set', 'shift', 'test', '['
    }
    
    def __init__(self):
        self.builtins_used = set()
        self.external_commands = set()
    
    def visit_SimpleCommand(self, node: SimpleCommand) -> None:
        """Check if command is a builtin."""
        if node.args:
            cmd = node.args[0]
            if cmd in self.BUILTINS:
                self.builtins_used.add(cmd)
            else:
                self.external_commands.add(cmd)
        
        # Check redirects
        if node.redirects:
            for redirect in node.redirects:
                self.visit(redirect)
    
    def visit_Pipeline(self, node: Pipeline) -> None:
        """Check commands in pipeline."""
        for cmd in node.commands:
            self.visit(cmd)
    
    def visit_IfStatement(self, node: IfStatement) -> None:
        """Check commands in if statement."""
        self.visit(node.condition)
        self.visit(node.then_part)
        if node.else_part:
            self.visit(node.else_part)
    
    def visit_ForLoop(self, node: ForLoop) -> None:
        """Check commands in for loop."""
        self.visit(node.body)
    
    def visit_CommandList(self, node: CommandList) -> None:
        """Check commands in list."""
        for cmd in node.commands:
            self.visit(cmd)
    
    def visit_Redirect(self, node: Redirect) -> None:
        """Redirects don't contain commands."""
        pass
    
    def get_report(self) -> str:
        """Get report of command usage."""
        lines = []
        
        if self.builtins_used:
            lines.append("Builtin commands used:")
            for builtin in sorted(self.builtins_used):
                lines.append(f"  - {builtin}")
        
        if self.external_commands:
            lines.append("\nExternal commands used:")
            for cmd in sorted(self.external_commands):
                lines.append(f"  - {cmd}")
        
        return '\n'.join(lines)


# Example usage
def demo_visitor_pattern():
    """Demonstrate the visitor pattern with a sample AST."""
    
    # Build a sample AST
    ast = CommandList([
        SimpleCommand(['echo', 'Starting process...']),
        
        IfStatement(
            condition=CommandList([
                SimpleCommand(['test', '-f', '/etc/config'])
            ]),
            then_part=CommandList([
                SimpleCommand(['echo', 'Config found']),
                SimpleCommand(['source', '/etc/config'])
            ]),
            else_part=CommandList([
                SimpleCommand(['echo', 'No config found'])
            ])
        ),
        
        ForLoop(
            variable='file',
            items=['data1.txt', 'data2.txt', 'output file.txt'],
            body=CommandList([
                Pipeline([
                    SimpleCommand(['cat', '$file']),
                    SimpleCommand(['grep', 'pattern']),
                    SimpleCommand(['wc', '-l'])
                ])
            ])
        ),
        
        SimpleCommand(
            ['echo', 'Done'], 
            redirects=[Redirect('>>', 'logfile.txt')]
        )
    ])
    
    # Use different visitors
    print("=== Pretty Printed AST ===")
    printer = PrettyPrintVisitor()
    print(printer.visit(ast))
    
    print("\n=== Command Statistics ===")
    counter = CommandCounterVisitor()
    counter.visit(ast)
    print(counter.get_summary())
    
    print("\n=== Command Analysis ===")
    detector = BuiltinDetectorVisitor()
    detector.visit(ast)
    print(detector.get_report())


if __name__ == '__main__':
    demo_visitor_pattern()