"""
Parser utilities for PSH shell.

This module contains utility functions for parser operations like heredoc handling.
"""

from typing import List

from ....ast_nodes import Program
from ....lexer.token_types import Token


class ParserUtils:
    """Utility functions for parser operations."""

    def __init__(self, main_parser):
        """Initialize with reference to main parser."""
        self.parser = main_parser

    def populate_heredoc_content(self, node, heredoc_map: dict):
        """Recursively populate heredoc content in AST nodes."""
        if hasattr(node, 'redirects') and node.redirects:
            for redirect in node.redirects:
                if redirect.type in ('<<', '<<-'):
                    # Use the heredoc key if available
                    if hasattr(redirect, 'heredoc_key') and redirect.heredoc_key in heredoc_map:
                        heredoc_info = heredoc_map[redirect.heredoc_key]
                        if isinstance(heredoc_info, dict):
                            redirect.heredoc_content = heredoc_info['content']
                            redirect.heredoc_quoted = heredoc_info.get('quoted', False)
                        else:
                            redirect.heredoc_content = heredoc_info
                    else:
                        # Fallback: find by delimiter when heredoc_key is absent
                        for key, heredoc_info in heredoc_map.items():
                            if key.endswith(f'_{redirect.target}'):
                                if isinstance(heredoc_info, dict):
                                    redirect.heredoc_content = heredoc_info['content']
                                    redirect.heredoc_quoted = heredoc_info.get('quoted', False)
                                else:
                                    redirect.heredoc_content = heredoc_info
                                break

        # Recursively process child nodes
        if hasattr(node, 'statements') and node.statements:
            statements = node.statements
            # A group node's `.statements` is a StatementList wrapper, not a
            # bare list (unlike a StatementList node, whose `.statements` IS
            # the list); unwrap before iterating, as the `commands` branch does.
            if hasattr(statements, 'statements'):
                statements = statements.statements
            for stmt in statements:
                self.populate_heredoc_content(stmt, heredoc_map)

        if hasattr(node, 'commands') and node.commands:
            commands = node.commands
            # StatementList wraps a list; unwrap before iterating
            if hasattr(commands, 'statements'):
                commands = commands.statements
            if hasattr(commands, '__iter__'):
                for cmd in commands:
                    self.populate_heredoc_content(cmd, heredoc_map)
            else:
                self.populate_heredoc_content(commands, heredoc_map)

        if hasattr(node, 'pipelines') and node.pipelines:
            for pipeline in node.pipelines:
                self.populate_heredoc_content(pipeline, heredoc_map)

        # Handle control structures
        if hasattr(node, 'condition'):
            self.populate_heredoc_content(node.condition, heredoc_map)
        if hasattr(node, 'then_part'):
            self.populate_heredoc_content(node.then_part, heredoc_map)
        if hasattr(node, 'else_part') and node.else_part:
            self.populate_heredoc_content(node.else_part, heredoc_map)
        if hasattr(node, 'elif_parts'):
            for elif_condition, elif_then in node.elif_parts:
                self.populate_heredoc_content(elif_condition, heredoc_map)
                self.populate_heredoc_content(elif_then, heredoc_map)
        if hasattr(node, 'body'):
            self.populate_heredoc_content(node.body, heredoc_map)
        if hasattr(node, 'items') and hasattr(node.items, '__iter__'):
            for item in node.items:
                self.populate_heredoc_content(item, heredoc_map)


def parse_with_heredocs(tokens: List[Token], heredoc_map: dict) -> Program:
    """Parse a list of tokens into an AST with pre-collected heredoc content."""
    from ..parser import Parser
    parser = Parser(tokens)
    ast = parser.parse()
    # Populate heredoc content in the AST
    parser.utils.populate_heredoc_content(ast, heredoc_map)
    return ast
