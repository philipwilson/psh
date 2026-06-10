#!/usr/bin/env python3
"""
Proof of concept for eliminating parser duplication between statement
and pipeline context parsers.

This shows how we can refactor the existing code to use neutral parsers
with context setting.
"""

from enum import Enum
from typing import Optional

class ExecutionContext(Enum):
    STATEMENT = "statement"
    PIPELINE = "pipeline"

class Parser:
    """Simplified parser showing the refactoring pattern."""
    
    # BEFORE: Duplicate implementations
    def parse_if_statement_old(self):
        """Parse if statement for execution in current shell."""
        self.expect('if')
        condition = self.parse_command_list()
        self.expect('then')
        then_part = self.parse_command_list()
        # ... parse elif/else ...
        self.expect('fi')
        
        node = IfConditional(
            condition=condition,
            then_part=then_part,
            execution_context=ExecutionContext.STATEMENT
        )
        return node
    
    def parse_if_command_old(self):
        """Parse if as pipeline component (executes in subshell)."""
        self.expect('if')
        condition = self.parse_command_list()
        self.expect('then')
        then_part = self.parse_command_list()
        # ... parse elif/else ...
        self.expect('fi')
        
        node = IfConditional(
            condition=condition,
            then_part=then_part,
            execution_context=ExecutionContext.PIPELINE
        )
        return node
    
    # AFTER: Single implementation with context setting
    def _parse_if_neutral(self):
        """Parse if construct without setting execution context."""
        self.expect('if')
        condition = self.parse_command_list()
        self.expect('then')
        then_part = self.parse_command_list()
        
        elif_parts = []
        while self.match('elif'):
            self.advance()  # consume 'elif'
            elif_condition = self.parse_command_list()
            self.expect('then')
            elif_body = self.parse_command_list()
            elif_parts.append((elif_condition, elif_body))
        
        else_part = None
        if self.match('else'):
            self.advance()  # consume 'else'
            else_part = self.parse_command_list()
        
        self.expect('fi')
        
        # Return node without execution context set
        return IfConditional(
            condition=condition,
            then_part=then_part,
            elif_parts=elif_parts,
            else_part=else_part,
            execution_context=None  # Will be set by caller
        )
    
    def parse_if_statement(self):
        """Parse if statement for execution in current shell."""
        node = self._parse_if_neutral()
        node.execution_context = ExecutionContext.STATEMENT
        return node
    
    def parse_if_command(self):
        """Parse if as pipeline component (executes in subshell)."""
        node = self._parse_if_neutral()
        node.execution_context = ExecutionContext.PIPELINE
        return node
    
    # Same pattern for other control structures
    def parse_while_statement(self):
        node = self._parse_while_neutral()
        node.execution_context = ExecutionContext.STATEMENT
        return node
    
    def parse_while_command(self):
        node = self._parse_while_neutral()
        node.execution_context = ExecutionContext.PIPELINE
        return node
    
    def parse_for_statement(self):
        node = self._parse_for_neutral()
        node.execution_context = ExecutionContext.STATEMENT
        return node
    
    def parse_for_command(self):
        node = self._parse_for_neutral()
        node.execution_context = ExecutionContext.PIPELINE
        return node


# Benefits of this approach:
# 1. Eliminates ~200 lines of duplicate code
# 2. Single source of truth for parsing logic
# 3. Easier to maintain - fix bugs in one place
# 4. Neutral parsers already exist, just need to use them
# 5. No change to external API or behavior

# Implementation notes:
# - The neutral parsers already exist in the current code
# - Just need to update the statement/command parsers to use them
# - Can be done incrementally, one control structure at a time
# - Full test suite ensures no regressions