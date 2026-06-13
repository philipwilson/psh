"""Legacy string-only AST fallbacks: classification tests (audit 2026-06-12).

The Word-AST migration left compatibility fallbacks for string-only nodes.
Each was audited and classified (docs/reviews/
code_quality_subsystem_reassessment_2026-06-12.md, Remaining Quality Risks
section 2):

(a) required compatibility  -> kept + exercised here
    - ForLoop/SelectLoop item_words empty/length-mismatched (manually
      constructed ASTs are an explicitly supported educational pattern;
      since A2 the field is a non-Optional List[Word] defaulting to []):
      items iterate as literal fields.
(b) parser migration bridge -> kept + exercised here
    - CaseConditional pattern with CasePattern.word=None: the combinator
      parser emits it when build_word_from_token rejects the pattern token
      (e.g. $(...) containing a function definition).
(c) unreachable defensive branches -> now raise internal errors
    - ArrayInitialization elements without parallel Words,
    - ArrayElementAssignment without value_word (since A2 value_word is a
      REQUIRED field: omitting it is a TypeError at construction),
    - SimpleCommand args/words divergence (now unrepresentable:
      args is a property derived from words),
    - non-Word arguments to the expansion engine.
(d) dead code -> deleted (ArrayOperationExecutor._add_expanded_element_to_array
    and the string [index]=value re-parsers; their only live path diverged
    from bash, see test_quoted_bracket_element_stays_literal).
"""

import pytest

from psh.ast_nodes import (
    ArrayElementAssignment,
    ArrayInitialization,
    CaseConditional,
    CaseItem,
    CasePattern,
    ExpansionPart,
    ForLoop,
    LiteralPart,
    SelectLoop,
    SimpleCommand,
    StatementList,
    VariableExpansion,
    Word,
)


def _echo_var_command(name: str) -> SimpleCommand:
    """Build `echo "$name"` with full Word AST (the executor requires Words)."""
    return SimpleCommand(
        words=[
            Word(parts=[LiteralPart('echo')]),
            Word(parts=[ExpansionPart(VariableExpansion(name),
                                      quoted=True, quote_char='"')]),
        ],
    )


def _echo_literal_command(text: str) -> SimpleCommand:
    return SimpleCommand(
        words=[Word(parts=[LiteralPart('echo')]),
               Word(parts=[LiteralPart(text)])],
    )


class TestClassARequiredCompatibility:
    """(a) empty item_words on manually constructed for/select loops."""

    def test_for_loop_without_item_words_iterates_literals(self, shell, capsys):
        """A manual ForLoop (item_words=[]) takes items as literal fields."""
        body = StatementList(statements=[_echo_var_command('i')])
        node = ForLoop(variable='i', items=['one', 'two $x', '*'], body=body)
        assert node.item_words == []  # dataclass default — the fallback
        rc = shell.execute_command_list(StatementList(statements=[node]))
        assert rc == 0
        # Literal fields: no expansion, no splitting, no globbing
        assert capsys.readouterr().out == 'one\ntwo $x\n*\n'

    def test_select_loop_without_item_words_uses_literal_menu(self, captured_shell):
        """_expand_loop_items on a manual SelectLoop returns literal items."""
        node = SelectLoop(variable='v', items=['a b', '$x'],
                          body=StatementList(statements=[]))
        assert node.item_words == []
        from psh.executor.control_flow import ControlFlowExecutor
        executor = ControlFlowExecutor(captured_shell)
        assert executor._expand_loop_items(node) == ['a b', '$x']

    def test_parser_built_for_loop_still_expands(self, captured_shell):
        """Contrast: parser-built loops expand items through the Word engine."""
        rc = captured_shell.run_command('x="p q"; for i in $x; do echo "$i"; done')
        assert rc == 0
        assert captured_shell.get_stdout() == 'p\nq\n'


class TestClassBParserMigrationBridge:
    """(b) CasePattern.word=None — combinator parser bridge."""

    def test_combinator_emits_wordless_pattern(self):
        """The combinator parser really produces CasePattern(word=None)
        for a $(...) pattern it cannot build a Word for — the bridge is
        reachable, not dead. If this starts failing because word is set,
        the combinator gained support: reclassify the executor fallback."""
        from psh.lexer import tokenize
        from psh.parser.combinators.parser import ParserCombinatorShellParser
        ast = ParserCombinatorShellParser().parse(
            tokenize('case x in $(f() { :; })) echo a;; *) echo b;; esac'))

        import dataclasses

        found = []

        def walk(node):
            if isinstance(node, CaseConditional):
                found.append(node)
            if dataclasses.is_dataclass(node):
                for f in dataclasses.fields(node):
                    value = getattr(node, f.name)
                    children = value if isinstance(value, list) else [value]
                    for child in children:
                        if dataclasses.is_dataclass(child):
                            walk(child)
        walk(ast)
        assert found, "combinator did not produce a CaseConditional"
        first_pattern = found[0].items[0].patterns[0]
        assert first_pattern.word is None
        assert first_pattern.pattern == '$(f() { :; })'

    def test_combinator_wordless_pattern_executes_like_bash(self, captured_shell):
        """End-to-end through the legacy string path (bash 5.2 prints b)."""
        rc = captured_shell.run_command(
            'parser-select combinator\n'
            'case x in $(f() { :; })) echo a;; *) echo b;; esac')
        assert rc == 0
        assert captured_shell.get_stdout().strip().endswith('b')

    def test_manual_wordless_pattern_expands_variables(self, shell, capsys):
        """The legacy path expands $vars in the pattern string (bash: M)."""
        shell.run_command('pat="hel*"; x=hello')
        node = CaseConditional(
            expr='$x',
            items=[
                CaseItem(patterns=[CasePattern('$pat')],  # word=None default
                         commands=StatementList(
                             statements=[_echo_literal_command('M')])),
                CaseItem(patterns=[CasePattern('*')],
                         commands=StatementList(
                             statements=[_echo_literal_command('N')])),
            ])
        rc = shell.execute_command_list(StatementList(statements=[node]))
        assert rc == 0
        assert capsys.readouterr().out == 'M\n'


class TestClassCUnreachableBranchesRaise:
    """(c) word-less nodes: ``words`` is the single source of truth.

    The array-init value computation (ArrayOperationExecutor.build_indexed_array
    / build_associative_array, shared by the bare ``a=(...)`` path and the
    declaration builtins) iterates ``node.words`` exclusively; ``elements`` is
    display-only derived metadata the executor never reads. A node whose
    ``words`` is empty therefore yields an EMPTY array — the
    elements/words divergence the old guard policed is now unrepresentable at
    execution time (it cannot pick the wrong representation: there is only
    one)."""

    def test_array_initialization_words_are_authoritative(self, shell):
        from psh.executor import ExecutorVisitor
        # elements claims one entry, but words (the sole truth) is empty:
        # the result is an empty indexed array, not an error.
        node = ArrayInitialization(name='a', elements=['x'])  # words=[]
        assert ExecutorVisitor(shell).visit(node) == 0
        from psh.core import IndexedArray
        var = shell.state.scope_manager.get_variable_object('a')
        assert isinstance(var.value, IndexedArray)
        assert var.value.indices() == []

    def test_assoc_array_initialization_words_are_authoritative(self, shell):
        from psh.executor import ExecutorVisitor
        shell.run_command('declare -A h')
        node = ArrayInitialization(name='h', elements=['[k]=v'])  # words=[]
        assert ExecutorVisitor(shell).visit(node) == 0
        from psh.core import AssociativeArray
        var = shell.state.scope_manager.get_variable_object('h')
        assert isinstance(var.value, AssociativeArray)
        assert var.value.keys() == []

    def test_array_element_assignment_without_value_word_raises(self):
        """value_word is a REQUIRED field since A2: a node built without it
        is a TypeError at construction (stronger than the old runtime
        internal-error guard, which is now structurally unreachable)."""
        with pytest.raises(TypeError):
            ArrayElementAssignment(name='a', index='0', value='v')

    def test_args_words_divergence_is_unrepresentable(self):
        """SimpleCommand(args=['x=1'], words=[]) used to silently assign a
        partially-expanded value, then (v0.300+) raised an internal error.
        Since args became a property DERIVED from words, the diseased
        state cannot be constructed at all: there is no args field to
        diverge, and the derived view always matches words."""
        node = SimpleCommand(words=[])
        assert node.args == []
        with pytest.raises(TypeError):
            SimpleCommand(args=['x=1'], words=[])  # no such field
        with pytest.raises(AttributeError):
            node.args = ['x=1']  # read-only property

    def test_expansion_engine_rejects_non_word(self, shell):
        from psh.expansion.word_expander import COMMAND_ARGUMENT
        with pytest.raises(TypeError, match='expects a Word'):
            shell.expansion_manager.expand_word_to_fields(
                'not a word', COMMAND_ARGUMENT)
        with pytest.raises(TypeError, match='expects a Word'):
            shell.expansion_manager.expand_assignment_value_word(42)


class TestClassDDeletedLegacyPathBashParity:
    """(d) behavior previously masked by the deleted string re-parser."""

    def test_quoted_bracket_element_stays_literal(self, shell):
        """a=("[0]"=x): bash keeps the element literal; the deleted legacy
        branch wrongly treated it as an explicit [0]=x assignment."""
        assert shell.run_command('a=("[0]"=x)') == 0
        var = shell.state.scope_manager.get_variable_object('a')
        assert var.value.get(0) == '[0]=x'

    def test_unquoted_explicit_assignment_still_works(self, shell):
        assert shell.run_command('a=([1]=x [3]=y z)') == 0
        var = shell.state.scope_manager.get_variable_object('a')
        arr = var.value
        assert [arr.get(i) for i in arr.indices()] == ['x', 'y', 'z']
        assert list(arr.indices()) == [1, 3, 4]
