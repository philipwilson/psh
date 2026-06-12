"""Legacy string-only AST fallbacks: classification tests (audit 2026-06-12).

The Word-AST migration left compatibility fallbacks for string-only nodes.
Each was audited and classified (docs/reviews/
code_quality_subsystem_reassessment_2026-06-12.md, Remaining Quality Risks
section 2):

(a) required compatibility  -> kept + exercised here
    - ForLoop/SelectLoop item_words=None (manually constructed ASTs are an
      explicitly supported educational pattern; the field is Optional by
      design): items iterate as literal fields.
(b) parser migration bridge -> kept + exercised here
    - CaseConditional pattern with CasePattern.word=None: the combinator
      parser emits it when build_word_from_token rejects the pattern token
      (e.g. $(...) containing a function definition).
(c) unreachable defensive branches -> now raise internal errors
    - ArrayInitialization elements without parallel Words,
    - ArrayElementAssignment without value_word,
    - SimpleCommand assignment words without Word AST,
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
        args=['echo', f'${name}'],
        words=[
            Word(parts=[LiteralPart('echo')]),
            Word(parts=[ExpansionPart(VariableExpansion(name),
                                      quoted=True, quote_char='"')],
                 quote_type='"'),
        ],
    )


def _echo_literal_command(text: str) -> SimpleCommand:
    return SimpleCommand(
        args=['echo', text],
        words=[Word(parts=[LiteralPart('echo')]),
               Word(parts=[LiteralPart(text)])],
    )


class TestClassARequiredCompatibility:
    """(a) item_words=None on manually constructed for/select loops."""

    def test_for_loop_without_item_words_iterates_literals(self, shell, capsys):
        """A manual ForLoop (item_words=None) takes items as literal fields."""
        body = StatementList(statements=[_echo_var_command('i')])
        node = ForLoop(variable='i', items=['one', 'two $x', '*'], body=body)
        assert node.item_words is None  # dataclass default — the fallback
        rc = shell.execute_command_list(StatementList(statements=[node]))
        assert rc == 0
        # Literal fields: no expansion, no splitting, no globbing
        assert capsys.readouterr().out == 'one\ntwo $x\n*\n'

    def test_select_loop_without_item_words_uses_literal_menu(self, captured_shell):
        """_expand_loop_items on a manual SelectLoop returns literal items."""
        node = SelectLoop(variable='v', items=['a b', '$x'],
                          body=StatementList(statements=[]))
        assert node.item_words is None
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
    """(c) word-less nodes that no parser can produce now fail loudly."""

    def test_array_initialization_without_words_raises(self, shell):
        from psh.executor import ExecutorVisitor
        node = ArrayInitialization(name='a', elements=['x'])  # words=[]
        with pytest.raises(RuntimeError, match='internal error'):
            ExecutorVisitor(shell).visit(node)

    def test_assoc_array_initialization_without_words_raises(self, shell):
        from psh.executor import ExecutorVisitor
        shell.run_command('declare -A h')
        node = ArrayInitialization(name='h', elements=['[k]=v'])  # words=[]
        with pytest.raises(RuntimeError, match='internal error'):
            ExecutorVisitor(shell).visit(node)

    def test_array_element_assignment_without_value_word_raises(self, shell):
        from psh.executor import ExecutorVisitor
        node = ArrayElementAssignment(name='a', index='0', value='v')
        assert node.value_word is None
        with pytest.raises(RuntimeError, match='internal error'):
            ExecutorVisitor(shell).visit(node)

    def test_assignment_without_word_ast_fails_loudly(self, shell, capsys):
        """SimpleCommand(args=['x=1'], words=[]) used to silently assign a
        partially-expanded value; now it surfaces as an internal error
        (caught by the executor's last-resort guard, status 1)."""
        node = SimpleCommand(args=['x=1'], words=[])
        rc = shell.execute_command_list(StatementList(statements=[node]))
        assert rc == 1
        assert 'internal error' in capsys.readouterr().err

    def test_expansion_engine_rejects_non_word(self, shell):
        with pytest.raises(TypeError, match='expects a Word'):
            shell.expansion_manager.expand_word_to_fields('not a word')
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
