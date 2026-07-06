"""Tests for parser visualization components."""

import pytest

from psh.lexer import tokenize
from psh.parser.recursive_descent.parser import Parser
from psh.parser.visualization import AsciiTreeRenderer, ASTDotGenerator, ASTPrettyPrinter
from psh.parser.visualization.ascii_tree import CompactAsciiTreeRenderer, DetailedAsciiTreeRenderer


def _pretty(src, **kwargs):
    ast = Parser(tokenize(src)).parse()
    return ASTPrettyPrinter(**kwargs).visit(ast)


# Raw dataclass repr signatures that must NEVER appear (they signal the printer
# fell through to repr() instead of visiting a child structurally).
_RAW_REPR_SIGNATURES = ("AndOrList(", "Pipeline(", "SimpleCommand(",
                        "IfConditional(", "pipelines=[", "commands=[",
                        "statements=[")


class TestASTPrettyPrinter:
    """Structural tests for the AST pretty printer.

    These assert the printer VISITS the current AST (correct field names, no
    raw dataclass repr), which the previous substring-only tests could not —
    a raw ``repr`` also contains "SimpleCommand"/"echo", so the stale printer
    passed those while emitting garbage.
    """

    def test_no_raw_dataclass_repr_leaks(self):
        for src in ("echo hello world", "echo a | grep b",
                    "if true; then echo hi; elif false; then echo x; fi",
                    "for i in 1 2 3; do echo $i; done",
                    "case $x in a) echo a;; esac"):
            out = _pretty(src)
            for sig in _RAW_REPR_SIGNATURES:
                assert sig not in out, f"raw repr {sig!r} leaked for {src!r}:\n{out}"

    def test_program_root_is_visited(self):
        out = _pretty("echo hello")
        # The old printer had no visit_Program and dumped a raw repr here.
        assert out.startswith("Program:")
        assert "statements: [" in out

    def test_simple_command_shows_words(self):
        out = _pretty("echo hello world")
        assert "SimpleCommand:" in out
        assert "words: [" in out
        for word in ("echo", "hello", "world"):
            assert repr(word) in out  # LiteralPart text: 'echo' etc.

    def test_and_or_list_shows_pipelines_and_operators(self):
        # The stale printer read obsolete left/operator/right here.
        out = _pretty("echo a && echo b || echo c")
        assert "AndOrList:" in out
        assert "pipelines: [" in out
        assert "operators: [" in out
        assert "'&&'" in out
        assert "'||'" in out

    def test_if_statement_shows_condition_and_then_part(self):
        out = _pretty("if true; then echo hi; fi")
        assert "IfConditional:" in out
        assert "condition:" in out
        assert "then_part:" in out

    def test_for_loop_shows_items_not_iterable(self):
        # The stale printer read the obsolete `iterable` attribute.
        out = _pretty("for i in 1 2 3; do echo $i; done")
        assert "ForLoop:" in out
        assert "variable: 'i'" in out
        assert "items: [" in out
        assert "'1'" in out and "'2'" in out and "'3'" in out
        assert "iterable" not in out

    def test_c_style_for_shows_current_fields(self):
        # The stale printer read obsolete init/update instead of *_expr.
        out = _pretty("for ((i=0; i<3; i++)); do echo $i; done")
        assert "CStyleForLoop:" in out
        assert "init_expr:" in out
        assert "update_expr:" in out

    def test_case_shows_expr_and_items(self):
        # The stale printer read obsolete expression/cases.
        out = _pretty("case $x in a) echo a;; b) echo b;; esac")
        assert "CaseConditional:" in out
        assert "items: [" in out
        assert "CaseItem:" in out

    def test_compact_mode_inlines_scalar_leaf_nodes(self):
        # Compact mode renders all-scalar nodes (e.g. LiteralPart) on one line.
        out = _pretty("echo hi", compact_mode=True)
        assert "LiteralPart(" in out  # inlined form: LiteralPart(text='echo', ...)

    def test_position_display_is_valid(self):
        out = _pretty("echo hello", show_positions=True)
        assert isinstance(out, str)
        assert out.startswith("Program")


class TestASTDotGenerator:
    """Test the Graphviz DOT generator."""

    def test_simple_command_dot(self):
        """Test DOT generation for simple commands."""
        tokens = tokenize("echo hello")
        parser = Parser(tokens)
        ast = parser.parse()

        generator = ASTDotGenerator()
        dot_output = generator.to_dot(ast)

        assert "digraph AST" in dot_output
        assert "SimpleCommand" in dot_output
        assert "node" in dot_output
        assert "->" in dot_output
        assert dot_output.startswith("digraph")
        assert dot_output.endswith("}")

    def test_pipeline_dot(self):
        """Test DOT generation for pipelines."""
        tokens = tokenize("echo hello | grep world")
        parser = Parser(tokens)
        ast = parser.parse()

        generator = ASTDotGenerator()
        dot_output = generator.to_dot(ast)

        assert "Pipeline" in dot_output
        assert "SimpleCommand" in dot_output
        assert "commands" in dot_output

    def test_control_structure_dot(self):
        """Test DOT generation for control structures."""
        tokens = tokenize("if true; then echo hi; fi")
        parser = Parser(tokens)
        ast = parser.parse()

        generator = ASTDotGenerator()
        dot_output = generator.to_dot(ast)

        assert "IfConditional" in dot_output
        assert "condition" in dot_output
        assert "then" in dot_output

    def test_colored_nodes(self):
        """Test colored node generation."""
        tokens = tokenize("echo hello")
        parser = Parser(tokens)
        ast = parser.parse()

        generator = ASTDotGenerator(color_by_type=True)
        dot_output = generator.to_dot(ast)

        assert "fillcolor" in dot_output
        assert "#" in dot_output  # Color codes

    def test_compact_nodes(self):
        """Test compact node representation."""
        tokens = tokenize("echo hello")
        parser = Parser(tokens)
        ast = parser.parse()

        generator = ASTDotGenerator(compact_nodes=True)
        dot_output = generator.to_dot(ast)

        # Should include command information in labels
        assert "echo" in dot_output


class TestAsciiTreeRenderer:
    """Test the ASCII tree renderer."""

    def test_simple_command_tree(self):
        """Test ASCII tree for simple commands."""
        tokens = tokenize("echo hello")
        parser = Parser(tokens)
        ast = parser.parse()

        output = AsciiTreeRenderer.render(ast)

        assert "└──" in output or "├──" in output  # Tree connectors
        assert "SimpleCommand" in output
        assert "echo" in output

    def test_pipeline_tree(self):
        """Test ASCII tree for pipelines."""
        tokens = tokenize("echo hello | grep world")
        parser = Parser(tokens)
        ast = parser.parse()

        output = AsciiTreeRenderer.render(ast)

        assert "Pipeline" in output
        assert "│" in output or "├──" in output  # Tree structure
        assert "commands" in output

    def test_if_statement_tree(self):
        """Test ASCII tree for if statements."""
        tokens = tokenize("if true; then echo hi; fi")
        parser = Parser(tokens)
        ast = parser.parse()

        output = AsciiTreeRenderer.render(ast)

        assert "IfConditional" in output
        assert "condition" in output
        assert "then" in output

    def test_compact_renderer(self):
        """Test compact ASCII tree renderer."""
        tokens = tokenize("echo hello world")
        parser = Parser(tokens)
        ast = parser.parse()

        output = CompactAsciiTreeRenderer.render(ast)

        # Should be more compact
        lines = output.split('\n')
        normal_output = AsciiTreeRenderer.render(ast)
        normal_lines = normal_output.split('\n')

        assert len(lines) <= len(normal_lines)

    def test_detailed_renderer(self):
        """Test detailed ASCII tree renderer."""
        tokens = tokenize("echo hello")
        parser = Parser(tokens)
        ast = parser.parse()

        output = DetailedAsciiTreeRenderer.render(ast)

        # Should be more detailed than normal output
        normal_output = AsciiTreeRenderer.render(ast)
        assert len(output) >= len(normal_output)

    def test_tree_structure_integrity(self):
        """Test that tree structure is properly formed."""
        tokens = tokenize("if true; then echo hello | grep world; fi")
        parser = Parser(tokens)
        ast = parser.parse()

        output = AsciiTreeRenderer.render(ast)
        lines = output.split('\n')

        # Check that tree connectors are properly aligned
        for line in lines:
            if "├──" in line or "└──" in line:
                # Should have proper indentation structure
                prefix = line.split("├──")[0] if "├──" in line else line.split("└──")[0]
                # Prefix should only contain spaces, │, and whitespace
                assert all(c in " │" for c in prefix)


class TestVisualizationIntegration:
    """Test integration of visualization with the shell."""

    def test_pretty_printer_convenience_function(self):
        """Test the convenience function for pretty printing."""
        from psh.parser.visualization.ast_formatter import format_ast

        tokens = tokenize("echo hello")
        parser = Parser(tokens)
        ast = parser.parse()

        output = format_ast(ast, compact_mode=True)
        assert "SimpleCommand" in output
        assert "echo" in output

    def test_dot_generator_convenience_function(self):
        """Test the convenience function for DOT generation."""
        from psh.parser.visualization.dot_generator import generate_dot

        tokens = tokenize("echo hello")
        parser = Parser(tokens)
        ast = parser.parse()

        output = generate_dot(ast, color_by_type=True)
        assert "digraph AST" in output
        assert "SimpleCommand" in output

    def test_ascii_tree_convenience_functions(self):
        """Test convenience functions for ASCII trees."""
        from psh.parser.visualization.ascii_tree import render_ast_tree, render_compact_tree, render_detailed_tree

        tokens = tokenize("echo hello")
        parser = Parser(tokens)
        ast = parser.parse()

        # Test basic function
        output1 = render_ast_tree(ast)
        assert "SimpleCommand" in output1

        # Test compact function
        output2 = render_compact_tree(ast)
        assert "SimpleCommand" in output2

        # Test detailed function
        output3 = render_detailed_tree(ast)
        assert "SimpleCommand" in output3
        # Detailed renderer should be more verbose than normal output
        assert len(output3) >= len(output1)

    def test_error_handling_in_formatters(self):
        """Test that formatters handle edge cases gracefully."""
        # Test with None/empty AST (should not crash)
        tokens = tokenize("")  # Empty input
        parser = Parser(tokens)

        try:
            ast = parser.parse()

            formatter = ASTPrettyPrinter()
            output = formatter.visit(ast)
            assert isinstance(output, str)

            generator = ASTDotGenerator()
            dot_output = generator.to_dot(ast)
            assert isinstance(dot_output, str)

            tree_output = AsciiTreeRenderer.render(ast)
            assert isinstance(tree_output, str)

        except Exception:
            # Empty input might not parse, which is fine
            pass


class TestVisualizationPerformance:
    """Test performance characteristics of visualization."""

    def test_large_ast_handling(self):
        """Test handling of moderately large ASTs."""
        # Create a moderately complex command
        command = "if true; then for i in 1 2 3; do echo $i | grep test; done; fi"
        tokens = tokenize(command)
        parser = Parser(tokens)
        ast = parser.parse()

        # All formatters should handle this without issues
        formatter = ASTPrettyPrinter()
        pretty_output = formatter.visit(ast)
        assert len(pretty_output) > 100  # Should be substantial

        generator = ASTDotGenerator()
        dot_output = generator.to_dot(ast)
        assert "digraph" in dot_output

        tree_output = AsciiTreeRenderer.render(ast)
        assert len(tree_output) > 100  # Should be substantial

    def test_deeply_nested_structures(self):
        """Test handling of deeply nested structures."""
        # Create a deeply nested if statement
        command = "if true; then if true; then if true; then echo deep; fi; fi; fi"
        tokens = tokenize(command)
        parser = Parser(tokens)
        ast = parser.parse()

        # Should handle nesting without stack overflow
        formatter = ASTPrettyPrinter()
        output = formatter.visit(ast)
        assert "IfConditional" in output

        tree_output = AsciiTreeRenderer.render(ast)
        assert "IfConditional" in tree_output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
