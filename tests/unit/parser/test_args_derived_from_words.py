"""SimpleCommand.args is DERIVED from words (Textbook B7).

Before v0.322, ``SimpleCommand`` stored ``args: List[str]`` and
``words: List[Word]`` as parallel lists that every producer had to keep
in sync (the parser appended in lockstep, the executor sliced and
rewrote both, four strategy sites built args-only carrier nodes). A
3,593-command characterization harness (every ``run_command``/``-c``
string in the test tree plus the lexer B6 corpus and a hand battery)
verified the derived rule below reproduces the recursive-descent
parser's stored args byte-for-byte across 4,455 SimpleCommands — then
the stored field was deleted and ``args`` became a read-only property.

This file keeps the harness's assertion as a permanent invariant:

1. For every parsed SimpleCommand (both parsers), ``node.args`` equals
   the flattening rule ``[''.join(str(p) for p in w.parts) for w in
   words]`` — guarding against anyone re-introducing a stored/shadowed
   args list.
2. A frozen golden table pins the flattening RULE itself (quote
   removal, expansion rendering, array-init flat strings), since args
   bytes feed --debug-ast, the analysis visitors, and assignment-name
   extraction.

The rule renders a ``$name`` through the single brace authority
``ast_nodes.words.variable_expansion_text``, so the SOURCE spelling
survives: ``${y}`` stays ``${y}`` and a bare ``$y`` stays bare. It used to
normalize every braced simple variable to the bare form, which is lossy —
``a${x}b`` flattened to ``a$xb``, naming a different variable — so the two
goldens that froze that normalization were re-pinned to the source
spelling. Execution semantics always came from ``words``.

Note: the combinator parser previously stored slightly different bytes for
a few shapes (``${y}`` stayed braced via format_token_value); since the
property, both parsers share the Word-derived view.
"""

import dataclasses

import pytest

from psh.ast_nodes import (
    ASTNode,
    ExpansionPart,
    SimpleCommand,
    VariableExpansion,
    next_rendered_part,
    variable_expansion_text,
)
from psh.lexer import tokenize

# Representative battery over the word shapes the flattening rule must
# handle: plain/quoted literals, composites, every expansion kind,
# assignment prefixes, array initializations, test/[ with !.
BATTERY = [
    'echo hello',
    'echo "a b" c',
    "echo 'lit $x'",
    'echo $x ${x} ${x:-def} ${#x} ${x}b a${x}b',
    'echo $1x ${1}x $v{1,2} ${v}{1,2}',
    'echo $v""{1,2} "$v"{1,2} $v""x',
    'echo "a$x b" "a${y}b"',
    'echo $(date) `pwd` $((1 + 2)) pre$(cmd)post',
    'cat <(echo a) >(cat)',
    'echo $1 $@ "$*" $? $$ $!',
    'a=1 b=$x echo c',
    'x=$(echo hi) y=`echo lo` env',
    'declare -a arr=(1 2)',
    'declare -a arr=(\'one\' "two $x" three$y)',
    'declare -a arr=(${y}b ${y} "q v")',
    'declare -A m=([k]="v 1" [j]=$w)',
    'local a=(1 2)',
    'test ! -f foo',
    '[ ! -e f ]',
    'echo a\\ b \\$x',
    '\\echo hi',
    "echo $'tab\\there'",
    'echo "x"y\'z\'$w',
    'echo ${x/a/b} ${x##p} ${x%%s} ${arr[@]} ${arr[0]} ${#arr[@]}',
    'cmd1 -o val | cmd2 |& cmd3',
    'a && b || c',
    'echo a; echo b & echo c',
    'echo {a,b}{1,2} ~/x *.py [ab]c ?x',
    'if true; then echo y; fi; for i in 1 2; do echo $i; done',
]

# Frozen flattening-rule goldens: source -> expected args of the FIRST
# SimpleCommand. Generated from the pre-B7 parser (v0.321.0), where args
# was still the stored list — do not regenerate from the parser under
# test; if the rule deliberately changes, re-verify consumers
# (--debug-ast, visitors, assignment extraction) first.
GOLDEN_FIRST_COMMAND_ARGS = {
    'echo "a b" c': ['echo', 'a b', 'c'],
    "echo 'lit $x'": ['echo', 'lit $x'],
    # the source's own spelling survives: braced stays braced (dropping the
    # braces in `a${x}b` would name `xb`), bare stays bare
    'echo ${x} ${x:-def} a${x}b': ['echo', '${x}', '${x:-def}', 'a${x}b'],
    'echo $xb $v{1,2} ${v}{1,2}': ['echo', '$xb', '$v{1,2}', '${v}{1,2}'],
    # a separator the flattening drops (an empty part, or a quote boundary)
    # already stopped the fusion, so the braces have to carry it
    'echo $v""{1,2} "$v"{1,2} $v""x':
        ['echo', '${v}{1,2}', '${v}{1,2}', '${v}x'],
    # a bare positional before a name char must be braced to stay `$1`
    'echo $1x': ['echo', '${1}x'],
    'echo "a$x b"': ['echo', 'a$x b'],
    'echo $(date) `pwd` $((1 + 2))': ['echo', '$(date)', '`pwd`', '$((1 + 2))'],
    # array initialization stays one flat argument (consumed by
    # declare/local's initializer parser; element source preserved)
    'declare -a arr=(${y}b "q v")': ['declare', '-a', 'arr=(${y}b "q v")'],
    'a=1 b=$x echo c': ['a=1', 'b=$x', 'echo', 'c'],
    '\\echo hi': ['\\echo', 'hi'],
    'echo "x"y\'z\'$w': ['echo', 'xyz$w'],
}


def _walk(node, acc):
    if isinstance(node, SimpleCommand):
        acc.append(node)
    if dataclasses.is_dataclass(node):
        for f in dataclasses.fields(node):
            value = getattr(node, f.name, None)
            children = value if isinstance(value, list) else [value]
            for child in children:
                if isinstance(child, ASTNode):
                    _walk(child, acc)


def _derived(words):
    """The flattening rule, restated: each part's source text, joined.

    A ``$name`` part is spelled by the single brace authority, asked about the
    neighbour ``next_rendered_part`` names — the next part that actually PRINTS,
    and whether the source separated them with something a rendering may drop.
    Both answers are TAKEN from the authority module, never recomputed here, so
    this restates only the JOIN and cannot fork the spelling rule.
    """
    out = []
    for word in words:
        chunks = []
        for i, part in enumerate(word.parts):
            if (isinstance(part, ExpansionPart)
                    and isinstance(part.expansion, VariableExpansion)):
                nxt, separated = next_rendered_part(word.parts, i)
                chunks.append(
                    variable_expansion_text(part.expansion, nxt, separated))
            else:
                chunks.append(str(part))
        out.append(''.join(chunks))
    return out


def _rd_parse(source):
    from psh.parser import Parser
    return Parser(tokenize(source), source_text=source).parse()


def _combinator_parse(source):
    from psh.parser.combinators.parser import ParserCombinatorShellParser
    return ParserCombinatorShellParser().parse(list(tokenize(source)))


@pytest.mark.parametrize('parse', [_rd_parse, _combinator_parse],
                         ids=['recursive_descent', 'combinator'])
def test_every_simple_command_args_matches_derived_rule(parse):
    """args == the Word flattening rule for every parsed SimpleCommand."""
    checked = 0
    for source in BATTERY:
        try:
            ast = parse(source)
        except Exception:
            continue  # combinator gaps are documented, not findings
        commands = []
        _walk(ast, commands)
        for node in commands:
            assert node.args == _derived(node.words), source
            checked += 1
    assert checked > 25  # the battery must actually exercise the rule


def test_flattening_rule_goldens():
    """The derived-args RULE itself is pinned (pre-B7 stored bytes)."""
    for source, expected in GOLDEN_FIRST_COMMAND_ARGS.items():
        ast = _rd_parse(source)
        commands = []
        _walk(ast, commands)
        assert commands, source
        assert commands[0].args == expected, source


def test_args_is_read_only_and_not_a_field():
    """The parallel-list disease is unrepresentable: no stored args."""
    node = SimpleCommand()
    assert node.args == []
    assert 'args' not in {f.name for f in dataclasses.fields(SimpleCommand)}
    with pytest.raises(AttributeError):
        node.args = ['echo']
    with pytest.raises(TypeError):
        SimpleCommand(args=['echo'])
