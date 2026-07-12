"""Renderer-output characterization corpus — the visualization drift-lock.

The four AST renderers (``ASTPrettyPrinter``, ``AsciiTreeRenderer`` +
its Compact/Detailed variants, ``SExpressionRenderer``, ``ASTDotGenerator``)
are structure-driven: they walk each node's dataclass fields. That makes them
correct-by-construction, but it also means an AST change (a renamed/added
field, a new node) silently reshapes their output with nothing to notice.

This corpus renders one nontrivial script (functions, for/if-else, while+read,
case, pipelines, and-or lists, redirects, subshell+background) plus a handful
of focused fragments through every renderer, at the SAME options the real
entry points use (``psh/utils/ast_debug.py`` for ``--debug-ast`` and
``psh/builtins/parse_tree.py`` for ``parse-tree``). The outputs are frozen as
golden files under ``visualization_corpus/``.

A legitimate AST change is meant to move this output — so when it does, the
failure is a **reviewable golden diff**, not a mystery. To adopt a change:

    PSH_UPDATE_VIZ_GOLDENS=1 python -m pytest tests/unit/parser/test_visualization_corpus.py

then read the ``git diff`` of ``visualization_corpus/`` and confirm every line
moved for a reason before committing.
"""

import os
from pathlib import Path

import pytest

from psh.lexer import tokenize
from psh.parser import Parser
from psh.parser.visualization import (
    AsciiTreeRenderer,
    ASTDotGenerator,
    ASTPrettyPrinter,
    CompactAsciiTreeRenderer,
    DetailedAsciiTreeRenderer,
    SExpressionRenderer,
)

GOLDEN_DIR = Path(__file__).parent / "visualization_corpus"

# One nontrivial script exercising the full grammar surface.
SCRIPT = r"""process_files() {
    for f in a b c; do
        if [ -f "$f" ]; then
            echo "found $f" >> log.txt
        else
            echo "missing $f" | tee -a errors.log
        fi
    done
    while read line; do
        echo "$line"
    done < input.txt
    (cd /tmp && ls) &
    case "$1" in
        start) echo starting ;;
        *) echo unknown ;;
    esac
}
process_files a && echo done || echo failed"""

# Focused fragments isolating specific renderer behaviours.
CORPUS = {
    "andor_chain": "cmd1 && cmd2 || cmd3",
    "single_cmd": "echo hello",
    "test_expr": "[[ ab == c\"d\" ]]",
    "for_words": "for i in 1 2 3; do echo $i; done",
    "script": SCRIPT,
}

# Renderer configs mirroring the real ast_debug.py / parse_tree.py invocations,
# so the golden locks the output users actually see.
RENDERERS = {
    "pretty": lambda ast: ASTPrettyPrinter(
        indent_size=2, show_positions=True, compact_mode=False).visit(ast),
    "tree": lambda ast: AsciiTreeRenderer.render(
        ast, show_positions=True, compact_mode=False),
    "compact": lambda ast: CompactAsciiTreeRenderer.render(ast),
    "detailed": lambda ast: DetailedAsciiTreeRenderer.render(ast),
    "sexp": lambda ast: SExpressionRenderer.render(
        ast, compact_mode=False, max_width=80, show_positions=True),
    "dot": lambda ast: ASTDotGenerator(
        show_positions=True, color_by_type=True).to_dot(ast),
}

CASES = [(name, renderer) for name in CORPUS for renderer in RENDERERS]


def _render(corpus_name: str, renderer_name: str) -> str:
    ast = Parser(tokenize(CORPUS[corpus_name]), source_text=CORPUS[corpus_name]).parse()
    return RENDERERS[renderer_name](ast) + "\n"


@pytest.mark.parametrize("corpus_name,renderer_name", CASES,
                         ids=[f"{c}-{r}" for c, r in CASES])
def test_visualization_golden(corpus_name, renderer_name):
    golden = GOLDEN_DIR / f"{corpus_name}.{renderer_name}.txt"
    actual = _render(corpus_name, renderer_name)

    if os.environ.get("PSH_UPDATE_VIZ_GOLDENS"):
        GOLDEN_DIR.mkdir(exist_ok=True)
        golden.write_text(actual)
        pytest.skip(f"regenerated {golden.name}")

    assert golden.exists(), (
        f"missing golden {golden.name}; regenerate with "
        f"PSH_UPDATE_VIZ_GOLDENS=1"
    )
    assert actual == golden.read_text(), (
        f"{golden.name} drifted; if the AST change is intended, regenerate "
        f"with PSH_UPDATE_VIZ_GOLDENS=1 and review the diff"
    )


def test_corpus_covers_every_renderer_and_construct():
    # Guard against silently dropping a renderer or the nontrivial script.
    assert set(RENDERERS) == {"pretty", "tree", "compact", "detailed", "sexp", "dot"}
    assert "script" in CORPUS
    # The script must exercise the full grammar surface the drift-lock claims.
    for construct in ("process_files()", "for f in", "if [ -f",
                      "while read", "case ", "| tee", ">> log.txt",
                      "< input.txt", "(cd /tmp", "&& echo done"):
        assert construct in SCRIPT
