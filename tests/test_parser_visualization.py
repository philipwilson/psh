"""Tests for parser visualization components."""

import pytest

from psh.lexer import tokenize
from psh.parser.recursive_descent.parser import Parser
from psh.parser.visualization import AsciiTreeRenderer, ASTDotGenerator, ASTPrettyPrinter
from psh.parser.visualization.ascii_tree import CompactAsciiTreeRenderer


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
        from psh.parser.visualization.ascii_tree import render_ast_tree, render_compact_tree

        tokens = tokenize("echo hello")
        parser = Parser(tokens)
        ast = parser.parse()

        # Test basic function
        output1 = render_ast_tree(ast)
        assert "SimpleCommand" in output1

        # Test compact function
        output2 = render_compact_tree(ast)
        assert "SimpleCommand" in output2

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


class TestB4VisualizationRepairs:
    """Pins for the reappraisal #19 B4 renderer repairs (H15 + H16 + dedup)."""

    @staticmethod
    def _ast(src):
        return Parser(tokenize(src)).parse()

    def test_h16_compact_render_differs_from_base_render(self):
        # H16: render() was a @staticmethod hard-coding AsciiTreeRenderer, so
        # CompactAsciiTreeRenderer.render(ast) rendered with BASE settings.
        # As a @classmethod it now builds the subclass, so a nested AST with
        # collapsible scalar fields (the C-style for loop's *_expr strings)
        # renders DIFFERENTLY through the compact renderer than the base one.
        ast = self._ast("for ((i=0; i<3; i++)); do echo hi; done")
        base = AsciiTreeRenderer.render(ast)
        compact = CompactAsciiTreeRenderer.render(ast)
        assert base != compact, "compact renderer must not equal the base renderer"

    def test_show_positions_is_real_in_every_renderer(self):
        # show_positions was a no-op in tree/dot (read a nonexistent
        # `position`) and unrendered in sexp; now all read node.line.
        from psh.parser.visualization import SExpressionRenderer
        ast = self._ast("echo hi")
        tree = AsciiTreeRenderer.render(ast, show_positions=True)
        assert "@line" in tree
        pretty = ASTPrettyPrinter(show_positions=True).visit(ast)
        assert "@line" in pretty
        sexp = SExpressionRenderer.render(ast, show_positions=True)
        assert "@line" in sexp
        dot = ASTDotGenerator(show_positions=True).to_dot(ast)
        assert "@line" in dot
        # ...and OFF by default (no positions leak in).
        assert "@line" not in AsciiTreeRenderer.render(ast)

    def test_no_phantom_property_fields_rendered(self):
        # H15: the old dir() walk rendered derived @property values as if they
        # were fields. A test expression's `left`/`right` (derived from
        # left_word/right_word) and a Word's is_unquoted_literal must NOT show
        # up as fields; the real fields must.
        out = AsciiTreeRenderer.render(self._ast('[[ ab == cd ]]'))
        assert "left_word" in out and "right_word" in out
        assert "left:" not in out and "right:" not in out
        assert "is_unquoted_literal" not in out

    def test_sexp_preserves_actual_and_or_operators(self):
        from psh.parser.visualization import SExpressionRenderer
        out = SExpressionRenderer.render(self._ast("a && b || c"))
        # Both operators must appear as themselves (the old collapse rewrote
        # any non-&& to ||; a pure && chain is the discriminating case).
        assert "&&" in out and "||" in out
        both_and = SExpressionRenderer.render(self._ast("a && b && c"))
        assert "&&" in both_and and "||" not in both_and

    def test_dot_single_pipeline_andorlist_has_no_pipe_label(self):
        # The `(|)` fallback mislabelled a single-pipeline and-or list with the
        # pipe operator; a bare AndOrList label is emitted instead.
        out = ASTDotGenerator().to_dot(self._ast("echo hi"))
        assert "AndOrList" in out
        assert "(|)" not in out and r"AndOrList\n(|)" not in out

    def test_dot_for_loop_renders_its_items(self):
        # DOT field drift: visit_ForLoop read a nonexistent `iterable`, so the
        # loop's iteration items never appeared in the graph. They must now.
        out = ASTDotGenerator().to_dot(self._ast("for i in 1 2 3; do echo $i; done"))
        assert "items" in out and "item_words" in out

    def test_export_surface(self):
        # D2-R1: SExpressionRenderer is production-imported (ast_debug.py) and
        # must be on the package export surface; node_fields is the shared walk.
        import psh.parser.visualization as viz
        assert "SExpressionRenderer" in viz.__all__
        assert "node_fields" in viz.__all__
        assert hasattr(viz, "SExpressionRenderer")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
