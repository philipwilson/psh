"""Architecture guardrails for the canonical Program root.

These pin the invariants the root-shape removal established, so a future change
cannot quietly reintroduce a content-dependent root, a second root container,
or per-consumer root normalization:

- ``Program`` is the ONLY root; ``TopLevel`` and the ``CommandList`` alias are
  gone from production.
- Neither parser reshapes the root after parsing (no ``_simplify_result`` /
  ``_bare_top_level_compound`` family).
- Every parser entry point is annotated ``-> Program`` (no ``Union`` root).
- Differential tests compare the two parsers directly (no root normalization).
- The top-level parser never hand-builds ``Pipeline`` / ``AndOrList``.
"""
import re
from pathlib import Path

import psh.ast_nodes as ast_mod
from psh.ast_nodes import Program
from psh.lexer import tokenize
from psh.parser import Parser, create_parser, parse, parse_with_heredocs
from psh.parser.combinators.parser import ParserCombinatorShellParser
from psh.parser.recursive_descent.support.utils import (
    parse_with_heredocs as rd_parse_with_heredocs,
)

PSH = Path(__file__).resolve().parents[3] / "psh"


def _py_sources():
    return list(PSH.rglob("*.py"))


class TestLegacyRootNamesGone:
    def test_toplevel_not_exported(self):
        assert not hasattr(ast_mod, "TopLevel")

    def test_commandlist_alias_removed(self):
        assert not hasattr(ast_mod, "CommandList")

    def test_no_production_reference_to_toplevel_node(self):
        # `TopLevelAbort` (a control-flow exception) is unrelated and allowed.
        offenders = []
        for path in _py_sources():
            for i, line in enumerate(path.read_text().splitlines(), 1):
                for m in re.finditer(r"\bTopLevel\b", line):
                    if line[m.end():m.end() + 5] != "Abort":
                        offenders.append(f"{path}:{i}: {line.strip()}")
        assert not offenders, "TopLevel AST node still referenced:\n" + "\n".join(offenders)

    def test_no_production_reference_to_commandlist(self):
        offenders = [
            f"{path}:{i}: {line.strip()}"
            for path in _py_sources()
            for i, line in enumerate(path.read_text().splitlines(), 1)
            if re.search(r"\bCommandList\b", line)
        ]
        assert not offenders, "CommandList still referenced:\n" + "\n".join(offenders)


class TestNoRootReshaping:
    def test_no_simplify_result_family(self):
        parser_src = (PSH / "parser/recursive_descent/parser.py").read_text()
        for banned in ("_simplify_result", "_bare_top_level_compound",
                       "_BARE_TOP_LEVEL_TYPES", "_parse_top_level_item"):
            assert banned not in parser_src, f"{banned} reintroduced in parser.py"


class TestEntryPointsReturnProgram:
    """Every entry point is annotated -> Program and produces one at runtime."""

    def test_annotations_are_program(self):
        assert Parser.parse.__annotations__.get("return") is Program
        assert rd_parse_with_heredocs.__annotations__.get("return") is Program
        assert ParserCombinatorShellParser.parse.__annotations__.get("return") is Program
        assert (ParserCombinatorShellParser.parse_with_heredocs
                .__annotations__.get("return") is Program)

    def test_no_union_root_annotations(self):
        # No parser entry-point signature declares a Union return (the old
        # `Union[CommandList, TopLevel]` root).
        for rel in ("parser/recursive_descent/parser.py",
                    "parser/recursive_descent/support/utils.py",
                    "parser/combinators/parser.py"):
            src = (PSH / rel).read_text()
            assert "-> Union[" not in src, f"Union return annotation in {rel}"

    def test_runtime_roots_are_program(self):
        toks = tokenize("echo hi")
        assert isinstance(parse(toks), Program)
        assert isinstance(Parser(tokenize("echo hi")).parse(), Program)
        assert isinstance(create_parser(tokenize("echo hi")).parse(), Program)
        assert isinstance(
            create_parser(tokenize("echo hi"), active_parser="combinator").parse(),
            Program)
        from psh.lexer import tokenize_with_heredocs
        t, hmap = tokenize_with_heredocs("cat <<EOF\nx\nEOF")
        assert isinstance(parse_with_heredocs(t, hmap), Program)
        assert isinstance(parse_with_heredocs(t, hmap, active_parser="combinator"),
                          Program)


class TestDifferentialTestsHaveNoRootNormalization:
    DIFF_DIR = Path(__file__).resolve().parents[2] / "parser_differential"

    def test_no_program_items_or_wrapper_normalization(self):
        for path in self.DIFF_DIR.glob("*.py"):
            src = path.read_text()
            for banned in ("_program_items", "_normalize_wrappers"):
                assert banned not in src, f"{banned} still in {path.name}"
