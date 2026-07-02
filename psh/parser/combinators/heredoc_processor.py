"""Heredoc content processor for the shell parser combinator.

This module provides post-processing for heredoc content in parsed AST nodes.
After the main parsing phase, this processor traverses the AST and populates
heredoc content in redirect nodes that have heredoc operators.
"""

from typing import Any, Dict, List, Union

from ...ast_nodes import (
    AndOrList,
    ArithmeticEvaluation,
    ASTNode,
    BraceGroup,
    CaseConditional,
    CommandList,
    CStyleForLoop,
    EnhancedTestStatement,
    ForLoop,
    FunctionDef,
    IfConditional,
    Pipeline,
    Redirect,
    SelectLoop,
    SimpleCommand,
    StatementList,
    SubshellGroup,
    WhileLoop,
)


class HeredocProcessor:
    """Processes heredoc content in parsed AST.

    This class provides functionality to traverse an AST and populate
    heredoc content in redirect nodes that reference heredocs. The heredoc
    content is collected during lexing/parsing and then populated in a
    second pass through the AST.
    """

    def __init__(self):
        """Initialize the heredoc processor."""
        pass

    def populate_heredocs(self, ast: ASTNode,
                         heredoc_contents: Dict[str, Any]) -> None:
        """Populate heredoc content in AST nodes.

        This method traverses the AST and looks for redirect nodes that
        have heredoc operators. When found, it populates the heredoc_content
        field with the corresponding content from the heredoc_contents map.

        Args:
            ast: The root AST node to process
            heredoc_contents: Map of heredoc keys to their content
        """
        if not heredoc_contents:
            return

        self._traverse_node(ast, heredoc_contents)

    def _traverse_node(self, node: ASTNode,
                      heredoc_contents: Dict[str, Any]) -> None:
        """Recursively traverse AST nodes to populate heredoc content.

        Args:
            node: Current AST node to process
            heredoc_contents: Map of heredoc keys to their content
        """
        if node is None:
            return

        # Every node's own redirects are handled HERE — one chokepoint — so
        # trailing redirects on compounds (`done <<EOF`, `fi <<EOF`) populate
        # exactly like a simple command's.
        redirects = getattr(node, 'redirects', None)
        if redirects:
            self._process_redirects(redirects, heredoc_contents)

        # Process simple commands (redirects handled above; no children)
        if isinstance(node, SimpleCommand):
            return

        # Process pipelines
        elif isinstance(node, Pipeline):
            self._process_pipeline(node, heredoc_contents)

        # Process and-or lists
        elif isinstance(node, AndOrList):
            self._process_and_or_list(node, heredoc_contents)

        # Process if conditionals
        elif isinstance(node, IfConditional):
            self._process_if_conditional(node, heredoc_contents)

        # Process while loops
        elif isinstance(node, WhileLoop):
            self._process_while_loop(node, heredoc_contents)

        # Process for loops
        elif isinstance(node, ForLoop):
            self._process_for_loop(node, heredoc_contents)

        # Process C-style for loops
        elif isinstance(node, CStyleForLoop):
            self._process_c_style_for_loop(node, heredoc_contents)

        # Process case statements
        elif isinstance(node, CaseConditional):
            self._process_case_statement(node, heredoc_contents)

        # Process select loops
        elif isinstance(node, SelectLoop):
            self._process_select_loop(node, heredoc_contents)

        # Process function definitions
        elif isinstance(node, FunctionDef):
            self._process_function_def(node, heredoc_contents)

        # Process subshell groups
        elif isinstance(node, SubshellGroup):
            self._process_subshell_group(node, heredoc_contents)

        # Process brace groups
        elif isinstance(node, BraceGroup):
            self._process_brace_group(node, heredoc_contents)

        # Arithmetic evaluations and enhanced tests: redirects handled
        # above; no command children to traverse.
        elif isinstance(node, (ArithmeticEvaluation, EnhancedTestStatement)):
            return

        # Process command lists and statement lists
        elif isinstance(node, (CommandList, StatementList)):
            self._process_statement_list(node, heredoc_contents)

        # Generic fallback for other node types
        else:
            self._process_generic_node(node, heredoc_contents)

    def _process_redirects(self, redirects: List[Redirect],
                          heredoc_contents: Dict[str, Any]) -> None:
        """Process redirections to populate heredoc content.

        Args:
            redirects: List of redirect nodes
            heredoc_contents: Map of heredoc keys to their content — either
                a bare string, or the heredoc lexer's ``{'content': ...,
                'quoted': ...}`` entry (the live tokenize_with_heredocs format)
        """
        for redirect in redirects:
            if (hasattr(redirect, 'heredoc_key') and
                redirect.heredoc_key and
                redirect.heredoc_key in heredoc_contents):
                info = heredoc_contents[redirect.heredoc_key]
                if isinstance(info, dict):
                    redirect.heredoc_content = info['content']
                    redirect.heredoc_quoted = info.get('quoted', False)
                else:
                    redirect.heredoc_content = info

    def _process_pipeline(self, node: Pipeline,
                         heredoc_contents: Dict[str, Any]) -> None:
        """Process pipeline node.

        Args:
            node: Pipeline node
            heredoc_contents: Map of heredoc keys to their content
        """
        for command in node.commands:
            self._traverse_node(command, heredoc_contents)

    def _process_and_or_list(self, node: AndOrList,
                            heredoc_contents: Dict[str, Any]) -> None:
        """Process and-or list node.

        Args:
            node: And-or list node
            heredoc_contents: Map of heredoc keys to their content
        """
        for pipeline in node.pipelines:
            self._traverse_node(pipeline, heredoc_contents)

    def _process_if_conditional(self, node: IfConditional,
                               heredoc_contents: Dict[str, Any]) -> None:
        """Process if conditional node.

        Args:
            node: If conditional node
            heredoc_contents: Map of heredoc keys to their content
        """
        # Process condition
        self._traverse_node(node.condition, heredoc_contents)

        # Process then part
        self._traverse_node(node.then_part, heredoc_contents)

        # Process elif parts
        if node.elif_parts:
            for elif_condition, elif_body in node.elif_parts:
                self._traverse_node(elif_condition, heredoc_contents)
                self._traverse_node(elif_body, heredoc_contents)

        # Process else part
        if node.else_part:
            self._traverse_node(node.else_part, heredoc_contents)

    def _process_while_loop(self, node: WhileLoop,
                           heredoc_contents: Dict[str, Any]) -> None:
        """Process while loop node.

        Args:
            node: While loop node
            heredoc_contents: Map of heredoc keys to their content
        """
        self._traverse_node(node.condition, heredoc_contents)
        self._traverse_node(node.body, heredoc_contents)

    def _process_for_loop(self, node: ForLoop,
                         heredoc_contents: Dict[str, Any]) -> None:
        """Process for loop node.

        Args:
            node: For loop node
            heredoc_contents: Map of heredoc keys to their content
        """
        # For loops don't have a condition that could contain commands
        # Only process the body
        self._traverse_node(node.body, heredoc_contents)

    def _process_c_style_for_loop(self, node: CStyleForLoop,
                                 heredoc_contents: Dict[str, Any]) -> None:
        """Process C-style for loop node.

        Args:
            node: C-style for loop node
            heredoc_contents: Map of heredoc keys to their content
        """
        # C-style for loops have expressions, not commands, in their header
        # Only process the body
        self._traverse_node(node.body, heredoc_contents)

    def _process_case_statement(self, node: CaseConditional,
                               heredoc_contents: Dict[str, Any]) -> None:
        """Process case statement node.

        Args:
            node: Case statement node
            heredoc_contents: Map of heredoc keys to their content
        """
        for item in node.items:
            self._traverse_node(item.commands, heredoc_contents)

    def _process_select_loop(self, node: SelectLoop,
                            heredoc_contents: Dict[str, Any]) -> None:
        """Process select loop node.

        Args:
            node: Select loop node
            heredoc_contents: Map of heredoc keys to their content
        """
        # Process body
        self._traverse_node(node.body, heredoc_contents)

    def _process_function_def(self, node: FunctionDef,
                             heredoc_contents: Dict[str, Any]) -> None:
        """Process function definition node.

        Args:
            node: Function definition node
            heredoc_contents: Map of heredoc keys to their content
        """
        self._traverse_node(node.body, heredoc_contents)

    def _process_subshell_group(self, node: SubshellGroup,
                               heredoc_contents: Dict[str, Any]) -> None:
        """Process subshell group node.

        Args:
            node: Subshell group node
            heredoc_contents: Map of heredoc keys to their content
        """
        self._traverse_node(node.statements, heredoc_contents)

    def _process_brace_group(self, node: BraceGroup,
                           heredoc_contents: Dict[str, Any]) -> None:
        """Process brace group node.

        Args:
            node: Brace group node
            heredoc_contents: Map of heredoc keys to their content
        """
        self._traverse_node(node.statements, heredoc_contents)

    def _process_statement_list(self, node: Union[CommandList, StatementList],
                               heredoc_contents: Dict[str, Any]) -> None:
        """Process command list or statement list node.

        Args:
            node: Command list or statement list node
            heredoc_contents: Map of heredoc keys to their content
        """
        for statement in node.statements:
            self._traverse_node(statement, heredoc_contents)

    def _process_generic_node(self, node: ASTNode,
                            heredoc_contents: Dict[str, Any]) -> None:
        """Process any other node type generically.

        This is a fallback for node types that aren't explicitly handled.
        It traverses all attributes looking for AST nodes to process.

        Args:
            node: Any AST node
            heredoc_contents: Map of heredoc keys to their content
        """
        if not hasattr(node, '__dict__'):
            return

        for attr_name, attr_value in node.__dict__.items():
            # Skip private attributes
            if attr_name.startswith('_'):
                continue

            # Process single AST node attributes
            if self._is_ast_node(attr_value):
                self._traverse_node(attr_value, heredoc_contents)

            # Process lists of AST nodes
            elif isinstance(attr_value, list):
                for item in attr_value:
                    if self._is_ast_node(item):
                        self._traverse_node(item, heredoc_contents)

            # Process tuples of AST nodes (like elif_parts)
            elif isinstance(attr_value, tuple):
                for item in attr_value:
                    if self._is_ast_node(item):
                        self._traverse_node(item, heredoc_contents)

    def _is_ast_node(self, obj: Any) -> bool:
        """Check if an object is likely an AST node.

        Args:
            obj: Object to check

        Returns:
            True if the object appears to be an AST node
        """
        if obj is None:
            return False

        # Check if it has a class and module
        if not (hasattr(obj, '__class__') and
                hasattr(obj.__class__, '__module__')):
            return False

        # Check if it's from the ast_nodes module
        module_name = str(obj.__class__.__module__)
        return 'ast_nodes' in module_name


# Convenience functions

def create_heredoc_processor() -> HeredocProcessor:
    """Create and return a HeredocProcessor instance.

    Returns:
        Initialized HeredocProcessor object
    """
    return HeredocProcessor()


def populate_heredocs(ast: ASTNode, heredoc_contents: Dict[str, Any]) -> None:
    """Convenience function to populate heredoc content in an AST.

    Args:
        ast: The root AST node to process
        heredoc_contents: Map of heredoc keys to their content
    """
    processor = HeredocProcessor()
    processor.populate_heredocs(ast, heredoc_contents)
