"""
AST Visitor Pattern implementation for PSH.

This module provides a clean separation between AST structure and operations
performed on the AST, following the visitor design pattern.
"""

from .base import ASTVisitor
from .debug_ast_visitor import DebugASTVisitor
from .enhanced_validator_visitor import EnhancedValidatorVisitor, ValidatorConfig, VariableTracker
from .formatter_visitor import (
    FormatterVisitor,
    format_bash_command,
    format_case_header,
    format_for_header,
    format_function_definition,
)
from .linter_visitor import LinterConfig, LinterVisitor, LintLevel
from .metrics_visitor import MetricsVisitor
from .security_visitor import SecurityIssue, SecurityVisitor
from .validator_visitor import ValidatorVisitor

__all__ = [
    'ASTVisitor',
    'FormatterVisitor',
    'format_bash_command',
    'format_case_header',
    'format_for_header',
    'format_function_definition',
    'DebugASTVisitor',
    'ValidatorVisitor',
    'EnhancedValidatorVisitor',
    'ValidatorConfig',
    'VariableTracker',
    'MetricsVisitor',
    'LinterVisitor',
    'LinterConfig',
    'LintLevel',
    'SecurityVisitor',
    'SecurityIssue',
]
