"""AST canonical-field invariants (safety net for Tier A2).

Tier A2 of the lexer/parser/AST architecture review
(``docs/reviews/lexer_parser_ast_architecture_review_2026-06-13.md``)
will DERIVE or DELETE the legacy parallel fields on several AST nodes,
keeping only the canonical ``Word``-based ones. Before that refactor
runs, this file locks the invariant that the production recursive
descent parser ALWAYS populates the canonical fields, so a regression
that drops a Word during A2 is caught here rather than at runtime.

Canonical (Word-based) vs legacy fields covered:

| Node                    | Canonical          | Legacy                                          |
|-------------------------|--------------------|-------------------------------------------------|
| SimpleCommand           | words              | args (now a derived property)                   |
| ArrayInitialization     | words              | elements (element_types/element_quote_types now derived props) |
| ArrayElementAssignment  | value_word         | value (value_type/value_quote_type now derived props)         |
| ForLoop                 | item_words         | items (item_quote_types removed in A2)          |
| SelectLoop              | item_words         | items (item_quote_types removed in A2)          |
| CasePattern             | word               | pattern                                         |

Each snippet in CORPUS is parsed through the SAME entry the shell uses
(``Parser(tokenize(src), source_text=src).parse()``), then the AST is
walked generically over dataclass fields (so invariants hold for NESTED
occurrences: an array assignment inside a function inside an if).

Findings as of v0.328 (all invariants hold for the RD parser):
- ``for x; do`` with no ``in`` list is normalized by the parser to
  ``for x in "$@"``, so item_words is ALWAYS populated for ForLoop.
- ``CStyleForLoop`` is a distinct node with no item_words field — its
  iteration is the C-style header, not a word list (asserted separately).
- Empty array ``a=()`` yields words=[] consistent with elements=[].
"""

import dataclasses

import pytest

from psh.ast_nodes import (
    ArrayElementAssignment,
    ArrayInitialization,
    ASTNode,
    CasePattern,
    CStyleForLoop,
    ForLoop,
    SelectLoop,
    SimpleCommand,
    Word,
)
from psh.lexer import tokenize
from psh.parser import Parser

# -- Corpus: representative snippets exercising every covered node type. ----
#
# Grouped by node type. Several snippets nest constructs (function / if /
# loop wrappers) so the generic walker also exercises the invariants on
# deeply nested occurrences.
CORPUS = [
    # --- SimpleCommand: plain / quoted / composite / expansions / redir ---
    'echo hello world',
    'echo "a b" c',
    "echo 'lit $x'",
    'echo a"b"$c',                       # composite word
    'echo $x ${x} ${x:-d} ${#x} a${x}b',
    'echo $(date) `pwd` $((1 + 2))',
    'cat <(echo a) >(cat)',
    'echo hi > out.txt 2>&1',            # redirections
    'cmd1 -o v | cmd2 |& cmd3',          # pipeline
    'NAME=val cmd arg',                  # assignment prefix + command
    'a=1 b=$x echo c',
    # --- ArrayInitialization ---
    'a=(1 2 3)',
    'a=("x y" z)',
    'a=([2]=x [5]=y)',                   # indexed initializers
    'declare -a a=(1 2 3)',
    'a=()',                              # empty
    'a+=(four five)',                    # append
    'declare -a arr=(\'one\' "two $x" three$y)',
    # --- ArrayElementAssignment ---
    'a[0]=x',
    'a[i+1]=y',                          # index expression
    'a[k]+=z',                           # append
    'a[0]="q v"',                        # quoted value
    # --- ForLoop / SelectLoop ---
    'for x in a b c; do echo $x; done',
    'for x in "$@"; do echo $x; done',
    'for x; do echo $x; done',           # no list -> normalized to "$@"
    'select x in a b; do echo $x; done',
    # --- CStyleForLoop (no item_words by design) ---
    'for ((i=0; i<3; i++)); do echo $i; done',
    # --- CasePattern ---
    'case $x in a) ;; b|c) ;; *) ;; esac',
    # --- Deeply nested: array elem inside function inside if ---
    'f() { if true; then a[i+1]=v; arr=(1 2); for y in p q; do echo $y; done; fi; }',
]


def _rd_parse(source):
    """Parse via the same entry the shell uses (recursive descent)."""
    return Parser(tokenize(source), source_text=source).parse()


def _walk(node, acc):
    """Generic AST walk over dataclass fields (collects every ASTNode)."""
    acc.append(node)
    if dataclasses.is_dataclass(node):
        for f in dataclasses.fields(node):
            value = getattr(node, f.name, None)
            children = value if isinstance(value, list) else [value]
            for child in children:
                if isinstance(child, ASTNode):
                    _walk(child, acc)


def _collect(node_type):
    """All nodes of ``node_type`` across the whole corpus."""
    found = []
    for source in CORPUS:
        acc = []
        _walk(_rd_parse(source), acc)
        for n in acc:
            if isinstance(n, node_type):
                found.append((source, n))
    return found


def _derived_args(words):
    """The documented args derivation rule (SimpleCommand.args)."""
    return [''.join(str(part) for part in word.parts) for word in words]


def test_corpus_parses_and_is_nonempty():
    """Every corpus snippet parses, and the corpus is meaningfully sized."""
    assert len(CORPUS) >= 25
    for source in CORPUS:
        ast = _rd_parse(source)  # must not raise
        assert ast is not None, source


# --- Invariant 1: SimpleCommand.words present; args derives from words. ----

def test_simple_command_args_derive_from_words():
    found = _collect(SimpleCommand)
    assert len(found) >= 25, "corpus must exercise many SimpleCommands"
    for source, node in found:
        assert node.words is not None, source
        # All words are Word instances.
        assert all(isinstance(w, Word) for w in node.words), source
        # args is derived, never stored: same length and same bytes.
        assert len(node.words) == len(node.args), source
        assert node.args == _derived_args(node.words), source


# --- Invariant 2: ArrayInitialization.words parallel to elements. ----------

def test_array_initialization_words_populated():
    found = _collect(ArrayInitialization)
    assert found, "corpus must contain array initializations"
    saw_nonempty = False
    for source, node in found:
        assert isinstance(node.words, list), source
        # words is parallel to the legacy flat elements list.
        assert len(node.words) == len(node.elements), source
        assert all(isinstance(w, Word) for w in node.words), source
        if node.words:
            saw_nonempty = True
    assert saw_nonempty, "corpus must include a non-empty array init"


# --- Invariant 3: ArrayElementAssignment.value_word is NON-None. -----------
# A2 will drop the Optional and make value_word structural.

def test_array_element_assignment_value_word_present():
    found = _collect(ArrayElementAssignment)
    assert len(found) >= 4, "corpus must exercise element assignments"
    for source, node in found:
        assert node.value_word is not None, (
            f"value_word is None for {source!r} -- A2 invariant violated"
        )
        assert isinstance(node.value_word, Word), source


# --- Invariant 4: ForLoop / SelectLoop with a list have NON-None item_words.

def test_for_loop_item_words_present_and_consistent():
    found = _collect(ForLoop)
    assert found, "corpus must contain for loops"
    for source, node in found:
        # The RD parser normalizes ``for x; do`` to ``for x in "$@"``,
        # so EVERY ForLoop has a populated item_words list.
        assert node.item_words is not None, (
            f"item_words is None for {source!r}"
        )
        assert len(node.item_words) == len(node.items), source
        assert all(isinstance(w, Word) for w in node.item_words), source


def test_select_loop_item_words_present_and_consistent():
    found = _collect(SelectLoop)
    assert found, "corpus must contain a select loop"
    for source, node in found:
        assert node.item_words is not None, source
        assert len(node.item_words) == len(node.items), source
        assert all(isinstance(w, Word) for w in node.item_words), source


def test_c_style_for_loop_has_no_item_words_field():
    """C-style ``for ((...))`` is a distinct node with no word list."""
    found = _collect(CStyleForLoop)
    assert found, "corpus must contain a C-style for loop"
    field_names = {f.name for f in dataclasses.fields(CStyleForLoop)}
    assert 'item_words' not in field_names
    assert 'items' not in field_names


# --- Invariant 5: every CasePattern from the RD parser has NON-None word. --

def test_case_pattern_word_present():
    found = _collect(CasePattern)
    assert len(found) >= 4, "corpus must exercise multiple case patterns"
    for source, node in found:
        assert node.word is not None, (
            f"CasePattern.word is None for {source!r}"
        )
        assert isinstance(node.word, Word), source


@pytest.mark.parametrize('source', CORPUS)
def test_no_canonical_field_is_none_anywhere(source):
    """End-to-end: walk each snippet, assert no canonical field is missing.

    Mirrors the per-node tests but runs per-snippet so a failure points
    straight at the offending source string.
    """
    acc = []
    _walk(_rd_parse(source), acc)
    for node in acc:
        if isinstance(node, SimpleCommand):
            assert node.words is not None
            assert len(node.words) == len(node.args)
        elif isinstance(node, ArrayInitialization):
            assert len(node.words) == len(node.elements)
        elif isinstance(node, ArrayElementAssignment):
            assert node.value_word is not None
        elif isinstance(node, (ForLoop, SelectLoop)):
            assert node.item_words is not None
            assert len(node.item_words) == len(node.items)
        elif isinstance(node, CasePattern):
            assert node.word is not None
