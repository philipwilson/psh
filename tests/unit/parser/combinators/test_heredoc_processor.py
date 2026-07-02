"""Tests for heredoc content processor."""

from psh.ast_nodes import (
    AndOrList,
    ArithmeticEvaluation,
    BinaryTestExpression,
    BraceGroup,
    CaseConditional,
    CaseItem,
    CasePattern,
    CommandList,
    CStyleForLoop,
    EnhancedTestStatement,
    ForLoop,
    FunctionDef,
    IfConditional,
    LiteralPart,
    Pipeline,
    Redirect,
    SelectLoop,
    SimpleCommand,
    StatementList,
    SubshellGroup,
    WhileLoop,
    Word,
)
from psh.parser.combinators.heredoc_processor import HeredocProcessor, create_heredoc_processor, populate_heredocs


class TestHeredocProcessor:
    """Test heredoc processor functionality."""

    def test_simple_command_heredoc(self):
        """Test heredoc population in simple command."""
        processor = HeredocProcessor()

        # Create a redirect with heredoc metadata
        redirect = Redirect(
            type='<<',
            target='EOF',
            heredoc_quoted=False
        )
        redirect.heredoc_key = 'heredoc_1'

        # Create simple command with the redirect
        command = SimpleCommand(
            words=[Word(parts=[LiteralPart('cat')])],
            redirects=[redirect]
        )

        # Populate heredoc content
        heredoc_contents = {'heredoc_1': 'Hello\nWorld\n'}
        processor.populate_heredocs(command, heredoc_contents)

        # Verify content was populated
        assert redirect.heredoc_content == 'Hello\nWorld\n'

    def test_pipeline_heredoc(self):
        """Test heredoc population in pipeline."""
        processor = HeredocProcessor()

        # Create commands with heredocs
        redirect1 = Redirect(
            type='<<',
            target='EOF1',
            heredoc_quoted=False
        )
        redirect1.heredoc_key = 'heredoc_1'

        redirect2 = Redirect(
            type='<<-',
            target='EOF2',
            heredoc_quoted=True
        )
        redirect2.heredoc_key = 'heredoc_2'

        cmd1 = SimpleCommand(
            words=[Word(parts=[LiteralPart('cat')])],
            redirects=[redirect1]
        )

        cmd2 = SimpleCommand(
            words=[Word(parts=[LiteralPart('wc')])],
            redirects=[redirect2]
        )

        pipeline = Pipeline(commands=[cmd1, cmd2])

        # Populate heredoc content
        heredoc_contents = {
            'heredoc_1': 'First\nContent\n',
            'heredoc_2': 'Second\nContent\n'
        }
        processor.populate_heredocs(pipeline, heredoc_contents)

        # Verify both heredocs were populated
        assert redirect1.heredoc_content == 'First\nContent\n'
        assert redirect2.heredoc_content == 'Second\nContent\n'

    def test_if_conditional_heredoc(self):
        """Test heredoc population in if conditional."""
        processor = HeredocProcessor()

        # Create redirects with heredocs
        redirect_cond = Redirect(
            type='<<',
            target='COND',
            heredoc_quoted=False
        )
        redirect_cond.heredoc_key = 'heredoc_cond'

        redirect_then = Redirect(
            type='<<',
            target='THEN',
            heredoc_quoted=False
        )
        redirect_then.heredoc_key = 'heredoc_then'

        redirect_elif = Redirect(
            type='<<',
            target='ELIF',
            heredoc_quoted=False
        )
        redirect_elif.heredoc_key = 'heredoc_elif'

        redirect_else = Redirect(
            type='<<',
            target='ELSE',
            heredoc_quoted=False
        )
        redirect_else.heredoc_key = 'heredoc_else'

        # Create commands with redirects
        cond_cmd = SimpleCommand(
            words=[Word(parts=[LiteralPart('test')])],
            redirects=[redirect_cond]
        )

        then_cmd = SimpleCommand(
            words=[Word(parts=[LiteralPart('echo')])],
            redirects=[redirect_then]
        )

        elif_cmd = SimpleCommand(
            words=[Word(parts=[LiteralPart('test2')])],
            redirects=[redirect_elif]
        )

        else_cmd = SimpleCommand(
            words=[Word(parts=[LiteralPart('echo2')])],
            redirects=[redirect_else]
        )

        # Create if conditional
        if_node = IfConditional(
            condition=CommandList(statements=[cond_cmd]),
            then_part=CommandList(statements=[then_cmd]),
            elif_parts=[(CommandList(statements=[elif_cmd]), CommandList(statements=[]))],
            else_part=CommandList(statements=[else_cmd])
        )

        # Populate heredoc content
        heredoc_contents = {
            'heredoc_cond': 'Condition\n',
            'heredoc_then': 'Then\n',
            'heredoc_elif': 'Elif\n',
            'heredoc_else': 'Else\n'
        }
        processor.populate_heredocs(if_node, heredoc_contents)

        # Verify all heredocs were populated
        assert redirect_cond.heredoc_content == 'Condition\n'
        assert redirect_then.heredoc_content == 'Then\n'
        assert redirect_elif.heredoc_content == 'Elif\n'
        assert redirect_else.heredoc_content == 'Else\n'

    def test_while_loop_heredoc(self):
        """Test heredoc population in while loop."""
        processor = HeredocProcessor()

        # Create redirects with heredocs
        redirect_cond = Redirect(
            type='<<',
            target='COND',
            heredoc_quoted=False
        )
        redirect_cond.heredoc_key = 'heredoc_cond'

        redirect_body = Redirect(
            type='<<',
            target='BODY',
            heredoc_quoted=False
        )
        redirect_body.heredoc_key = 'heredoc_body'

        # Create commands
        cond_cmd = SimpleCommand(
            words=[Word(parts=[LiteralPart('read')])],
            redirects=[redirect_cond]
        )

        body_cmd = SimpleCommand(
            words=[Word(parts=[LiteralPart('process')])],
            redirects=[redirect_body]
        )

        # Create while loop
        while_node = WhileLoop(
            condition=CommandList(statements=[cond_cmd]),
            body=CommandList(statements=[body_cmd])
        )

        # Populate heredoc content
        heredoc_contents = {
            'heredoc_cond': 'Condition content\n',
            'heredoc_body': 'Body content\n'
        }
        processor.populate_heredocs(while_node, heredoc_contents)

        # Verify heredocs were populated
        assert redirect_cond.heredoc_content == 'Condition content\n'
        assert redirect_body.heredoc_content == 'Body content\n'

    def test_for_loop_heredoc(self):
        """Test heredoc population in for loop."""
        processor = HeredocProcessor()

        # Create redirect with heredoc in body
        redirect = Redirect(
            type='<<',
            target='DATA',
            heredoc_quoted=False
        )
        redirect.heredoc_key = 'heredoc_1'

        # Create command
        cmd = SimpleCommand(
            words=[Word(parts=[LiteralPart('process')])],
            redirects=[redirect]
        )

        # Create for loop
        for_node = ForLoop(
            variable='item',
            items=['a', 'b', 'c'],
            body=CommandList(statements=[cmd])
        )

        # Populate heredoc content
        heredoc_contents = {'heredoc_1': 'Loop data\n'}
        processor.populate_heredocs(for_node, heredoc_contents)

        # Verify heredoc was populated
        assert redirect.heredoc_content == 'Loop data\n'

    def test_c_style_for_loop_heredoc(self):
        """Test heredoc population in C-style for loop."""
        processor = HeredocProcessor()

        # Create redirect with heredoc in body
        redirect = Redirect(
            type='<<',
            target='DATA',
            heredoc_quoted=False
        )
        redirect.heredoc_key = 'heredoc_1'

        # Create command
        cmd = SimpleCommand(
            words=[Word(parts=[LiteralPart('process')])],
            redirects=[redirect]
        )

        # Create C-style for loop
        for_node = CStyleForLoop(
            init_expr='i=0',
            condition_expr='i<10',
            update_expr='i++',
            body=CommandList(statements=[cmd])
        )

        # Populate heredoc content
        heredoc_contents = {'heredoc_1': 'C-style loop data\n'}
        processor.populate_heredocs(for_node, heredoc_contents)

        # Verify heredoc was populated
        assert redirect.heredoc_content == 'C-style loop data\n'

    def test_case_statement_heredoc(self):
        """Test heredoc population in case statement."""
        processor = HeredocProcessor()

        # Create redirects with heredocs for different cases
        redirect1 = Redirect(
            type='<<',
            target='CASE1',
            heredoc_quoted=False
        )
        redirect1.heredoc_key = 'heredoc_1'

        redirect2 = Redirect(
            type='<<',
            target='CASE2',
            heredoc_quoted=False
        )
        redirect2.heredoc_key = 'heredoc_2'

        # Create commands
        cmd1 = SimpleCommand(
            words=[Word(parts=[LiteralPart('echo')])],
            redirects=[redirect1]
        )

        cmd2 = SimpleCommand(
            words=[Word(parts=[LiteralPart('cat')])],
            redirects=[redirect2]
        )

        # Create case items
        item1 = CaseItem(
            patterns=[CasePattern('pattern1')],
            commands=CommandList(statements=[cmd1]),
            terminator=';;'
        )

        item2 = CaseItem(
            patterns=[CasePattern('pattern2')],
            commands=CommandList(statements=[cmd2]),
            terminator=';;'
        )

        # Create case statement
        case_node = CaseConditional(
            expr='$var',
            items=[item1, item2]
        )

        # Populate heredoc content
        heredoc_contents = {
            'heredoc_1': 'Case 1 data\n',
            'heredoc_2': 'Case 2 data\n'
        }
        processor.populate_heredocs(case_node, heredoc_contents)

        # Verify heredocs were populated
        assert redirect1.heredoc_content == 'Case 1 data\n'
        assert redirect2.heredoc_content == 'Case 2 data\n'

    def test_select_loop_heredoc(self):
        """Test heredoc population in select loop."""
        processor = HeredocProcessor()

        # Create redirect with heredoc in body
        redirect_body = Redirect(
            type='<<',
            target='DATA',
            heredoc_quoted=False
        )
        redirect_body.heredoc_key = 'heredoc_body'

        # Create redirect for the select loop itself
        redirect_loop = Redirect(
            type='<<',
            target='MENU',
            heredoc_quoted=False
        )
        redirect_loop.heredoc_key = 'heredoc_loop'

        # Create command
        cmd = SimpleCommand(
            words=[Word(parts=[LiteralPart('process')])],
            redirects=[redirect_body]
        )

        # Create select loop
        select_node = SelectLoop(
            variable='choice',
            items=['opt1', 'opt2', 'opt3'],
            body=CommandList(statements=[cmd]),
            redirects=[redirect_loop],
            background=False
        )

        # Populate heredoc content
        heredoc_contents = {
            'heredoc_body': 'Body data\n',
            'heredoc_loop': 'Menu data\n'
        }
        processor.populate_heredocs(select_node, heredoc_contents)

        # Verify heredocs were populated
        assert redirect_body.heredoc_content == 'Body data\n'
        assert redirect_loop.heredoc_content == 'Menu data\n'

    def test_function_def_heredoc(self):
        """Test heredoc population in function definition."""
        processor = HeredocProcessor()

        # Create redirect with heredoc
        redirect = Redirect(
            type='<<',
            target='FUNC',
            heredoc_quoted=False
        )
        redirect.heredoc_key = 'heredoc_func'

        # Create command
        cmd = SimpleCommand(
            words=[Word(parts=[LiteralPart('echo')])],
            redirects=[redirect]
        )

        # Create function definition
        func_node = FunctionDef(
            name='myfunc',
            body=StatementList(statements=[cmd])
        )

        # Populate heredoc content
        heredoc_contents = {'heredoc_func': 'Function data\n'}
        processor.populate_heredocs(func_node, heredoc_contents)

        # Verify heredoc was populated
        assert redirect.heredoc_content == 'Function data\n'

    def test_subshell_group_heredoc(self):
        """Test heredoc population in subshell group."""
        processor = HeredocProcessor()

        # Create redirect with heredoc inside subshell
        redirect_inner = Redirect(
            type='<<',
            target='INNER',
            heredoc_quoted=False
        )
        redirect_inner.heredoc_key = 'heredoc_inner'

        # Create redirect for subshell itself
        redirect_outer = Redirect(
            type='<<',
            target='OUTER',
            heredoc_quoted=False
        )
        redirect_outer.heredoc_key = 'heredoc_outer'

        # Create command
        cmd = SimpleCommand(
            words=[Word(parts=[LiteralPart('cat')])],
            redirects=[redirect_inner]
        )

        # Create subshell group
        subshell_node = SubshellGroup(
            statements=CommandList(statements=[cmd]),
            redirects=[redirect_outer]
        )

        # Populate heredoc content
        heredoc_contents = {
            'heredoc_inner': 'Inner data\n',
            'heredoc_outer': 'Outer data\n'
        }
        processor.populate_heredocs(subshell_node, heredoc_contents)

        # Verify heredocs were populated
        assert redirect_inner.heredoc_content == 'Inner data\n'
        assert redirect_outer.heredoc_content == 'Outer data\n'

    def test_brace_group_heredoc(self):
        """Test heredoc population in brace group."""
        processor = HeredocProcessor()

        # Create redirect with heredoc inside brace group
        redirect_inner = Redirect(
            type='<<',
            target='INNER',
            heredoc_quoted=False
        )
        redirect_inner.heredoc_key = 'heredoc_inner'

        # Create redirect for brace group itself
        redirect_outer = Redirect(
            type='<<',
            target='OUTER',
            heredoc_quoted=False
        )
        redirect_outer.heredoc_key = 'heredoc_outer'

        # Create command
        cmd = SimpleCommand(
            words=[Word(parts=[LiteralPart('cat')])],
            redirects=[redirect_inner]
        )

        # Create brace group
        brace_node = BraceGroup(
            statements=CommandList(statements=[cmd]),
            redirects=[redirect_outer]
        )

        # Populate heredoc content
        heredoc_contents = {
            'heredoc_inner': 'Inner data\n',
            'heredoc_outer': 'Outer data\n'
        }
        processor.populate_heredocs(brace_node, heredoc_contents)

        # Verify heredocs were populated
        assert redirect_inner.heredoc_content == 'Inner data\n'
        assert redirect_outer.heredoc_content == 'Outer data\n'

    def test_arithmetic_evaluation_heredoc(self):
        """Test heredoc population in arithmetic evaluation."""
        processor = HeredocProcessor()

        # Create redirect with heredoc
        redirect = Redirect(
            type='<<',
            target='MATH',
            heredoc_quoted=False
        )
        redirect.heredoc_key = 'heredoc_math'

        # Create arithmetic evaluation
        arith_node = ArithmeticEvaluation(
            expression='2 + 2',
            redirects=[redirect],
            background=False
        )

        # Populate heredoc content
        heredoc_contents = {'heredoc_math': 'Math data\n'}
        processor.populate_heredocs(arith_node, heredoc_contents)

        # Verify heredoc was populated
        assert redirect.heredoc_content == 'Math data\n'

    def test_enhanced_test_heredoc(self):
        """Test heredoc population in enhanced test statement."""
        processor = HeredocProcessor()

        # Create redirect with heredoc
        redirect = Redirect(
            type='<<',
            target='TEST',
            heredoc_quoted=False
        )
        redirect.heredoc_key = 'heredoc_test'

        # Create enhanced test statement
        test_node = EnhancedTestStatement(
            expression=BinaryTestExpression(
                left_word=Word(parts=[LiteralPart('$a')]),
                operator='==',
                right_word=Word(parts=[LiteralPart('$b')]),
            ),
            redirects=[redirect]
        )

        # Populate heredoc content
        heredoc_contents = {'heredoc_test': 'Test data\n'}
        processor.populate_heredocs(test_node, heredoc_contents)

        # Verify heredoc was populated
        assert redirect.heredoc_content == 'Test data\n'

    def test_nested_structures_heredoc(self):
        """Test heredoc population in deeply nested structures."""
        processor = HeredocProcessor()

        # Create redirect with heredoc
        redirect = Redirect(
            type='<<',
            target='NESTED',
            heredoc_quoted=False
        )
        redirect.heredoc_key = 'heredoc_nested'

        # Create deeply nested structure
        cmd = SimpleCommand(
            words=[Word(parts=[LiteralPart('echo')])],
            redirects=[redirect]
        )

        pipeline = Pipeline(commands=[cmd])
        and_or = AndOrList(pipelines=[pipeline], operators=[])
        subshell = SubshellGroup(statements=CommandList(statements=[and_or]))
        if_body = CommandList(statements=[subshell])

        if_node = IfConditional(
            condition=CommandList(statements=[]),
            then_part=if_body,
            elif_parts=[],
            else_part=None
        )

        # Populate heredoc content
        heredoc_contents = {'heredoc_nested': 'Nested data\n'}
        processor.populate_heredocs(if_node, heredoc_contents)

        # Verify heredoc was populated even in deeply nested structure
        assert redirect.heredoc_content == 'Nested data\n'

    def test_empty_heredoc_contents(self):
        """Test processor with empty heredoc contents."""
        processor = HeredocProcessor()

        # Create redirect with heredoc
        redirect = Redirect(
            type='<<',
            target='EOF',
            heredoc_quoted=False
        )
        redirect.heredoc_key = 'heredoc_1'

        # Create simple command
        command = SimpleCommand(
            words=[Word(parts=[LiteralPart('cat')])],
            redirects=[redirect]
        )

        # Populate with empty contents
        processor.populate_heredocs(command, {})

        # Verify heredoc_content was not populated
        assert redirect.heredoc_content is None

    def test_missing_heredoc_key(self):
        """Test processor when heredoc key is missing from contents."""
        processor = HeredocProcessor()

        # Create redirect with heredoc
        redirect = Redirect(
            type='<<',
            target='EOF',
            heredoc_quoted=False
        )
        redirect.heredoc_key = 'heredoc_missing'

        # Create simple command
        command = SimpleCommand(
            words=[Word(parts=[LiteralPart('cat')])],
            redirects=[redirect]
        )

        # Populate with contents that don't have the key
        heredoc_contents = {'heredoc_other': 'Other data\n'}
        processor.populate_heredocs(command, heredoc_contents)

        # Verify heredoc_content was not populated
        assert redirect.heredoc_content is None

    def test_convenience_functions(self):
        """Test convenience functions."""
        # Test create_heredoc_processor
        processor = create_heredoc_processor()
        assert isinstance(processor, HeredocProcessor)

        # Test populate_heredocs function
        redirect = Redirect(
            type='<<',
            target='EOF',
            heredoc_quoted=False
        )
        redirect.heredoc_key = 'heredoc_1'

        command = SimpleCommand(
            words=[Word(parts=[LiteralPart('cat')])],
            redirects=[redirect]
        )

        heredoc_contents = {'heredoc_1': 'Convenience data\n'}
        populate_heredocs(command, heredoc_contents)

        # Verify content was populated
        assert redirect.heredoc_content == 'Convenience data\n'


class TestRealHeredocSeam:
    """Drive the REAL seam: tokenize_with_heredocs -> combinator parse -> AST.

    The manual-key tests above pin the processor in isolation; these pin the
    live path (reappraisal #15 L2): the lexer's ``heredoc_key`` must survive
    the combinator's redirection builder, and the lexer's
    ``{'content', 'quoted'}`` map entries must populate both fields.
    """

    @staticmethod
    def _parse(source):
        from psh.lexer import tokenize_with_heredocs
        from psh.parser.combinators.parser import ParserCombinatorShellParser
        tokens, heredoc_map = tokenize_with_heredocs(source)
        return ParserCombinatorShellParser().parse_with_heredocs(tokens, heredoc_map)

    def test_body_populates_through_real_tokens(self):
        ast = self._parse('cat <<EOF\nhello seam\nEOF\n')
        redirect = ast.items[0].pipelines[0].commands[0].redirects[0]
        assert redirect.heredoc_key
        assert redirect.heredoc_content == 'hello seam\n'
        assert redirect.heredoc_quoted is False

    def test_quoted_delimiter_sets_quoted_flag(self):
        ast = self._parse("cat <<'EOF'\nvalue $x\nEOF\n")
        redirect = ast.items[0].pipelines[0].commands[0].redirects[0]
        assert redirect.heredoc_content == 'value $x\n'
        assert redirect.heredoc_quoted is True

    def test_two_heredocs_populate_independently(self):
        ast = self._parse('cat <<A; cat <<B\nfirst\nA\nsecond\nB\n')
        first = ast.items[0].pipelines[0].commands[0].redirects[0]
        second = ast.items[1].pipelines[0].commands[0].redirects[0]
        assert first.heredoc_content == 'first\n'
        assert second.heredoc_content == 'second\n'

    def test_compound_trailing_heredoc_populates(self):
        ast = self._parse('while read x; do echo $x; done <<EOF\nbody\nEOF\n')
        loop = ast.items[0]
        assert loop.redirects[0].heredoc_content == 'body\n'

    def test_execution_uses_active_combinator_parser(self, captured_shell, monkeypatch):
        """Heredoc input must parse with the ACTIVE parser, not silently RD.

        source_processor used to route ANY heredoc-containing input to the
        recursive descent parser even under --parser combinator; spy on the
        combinator entry point to prove the honest routing.
        """
        from psh.parser.combinators.parser import ParserCombinatorShellParser
        calls = []
        original = ParserCombinatorShellParser.parse_with_heredocs

        def spy(self, tokens, heredoc_contents):
            calls.append(True)
            return original(self, tokens, heredoc_contents)

        monkeypatch.setattr(ParserCombinatorShellParser, 'parse_with_heredocs', spy)
        captured_shell.active_parser = 'combinator'
        rc = captured_shell.run_command(
            'read line <<EOF\nreal seam\nEOF\necho "got: $line"')
        assert rc == 0
        assert calls, "heredoc input bypassed the active combinator parser"
        assert captured_shell.get_stdout() == 'got: real seam\n'
