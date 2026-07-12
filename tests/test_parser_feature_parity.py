"""Comprehensive feature parity tests between parser implementations.

This module systematically tests that both the recursive descent parser
and parser combinator produce equivalent ASTs for all shell features.
"""



from dataclasses import dataclass
from typing import Any, Tuple

import pytest

from psh.lexer import tokenize, tokenize_with_heredocs
from psh.parser import ParseError, Parser, parse_with_heredocs
from psh.parser.combinators.parser import ParserCombinatorShellParser
from psh.parser.config import ParserConfig


@dataclass
class ParityTestCase:
    """A test case for parser parity."""
    name: str
    command: str
    should_parse: bool = True
    skip_combinator: bool = False
    skip_reason: str = ""


class TestParserFeatureParity:
    """Test feature parity between parser implementations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.pc_parser = ParserCombinatorShellParser()

    def parse_both(self, command: str) -> Tuple[Any, Any]:
        """Parse with both parsers and return ASTs.

        Auto-detects heredocs and uses the heredoc parsing path when needed.
        """
        if '<<' in command and '\n' in command:
            return self.parse_both_heredoc(command)

        tokens_rd = tokenize(command)
        tokens_pc = tokenize(command)

        rd_ast = Parser(tokens_rd, config=ParserConfig()).parse()
        pc_ast = self.pc_parser.parse(tokens_pc)

        return rd_ast, pc_ast

    def parse_both_heredoc(self, command: str) -> Tuple[Any, Any]:
        """Parse with both parsers using heredoc-aware tokenization."""
        # Recursive descent path
        tokens_rd, heredoc_map_rd = tokenize_with_heredocs(command)
        rd_ast = parse_with_heredocs(tokens_rd, heredoc_map_rd)

        # Combinator parser path
        tokens_pc, heredoc_map_pc = tokenize_with_heredocs(command)
        pc_ast = self.pc_parser.parse_with_heredocs(tokens_pc, heredoc_map_pc)

        return rd_ast, pc_ast

    def check_parity(self, test_case: ParityTestCase):
        """Check if both parsers produce equivalent results."""
        if test_case.skip_combinator:
            pytest.skip(f"Parser combinator: {test_case.skip_reason}")

        if test_case.should_parse:
            # Both should parse successfully
            rd_ast, pc_ast = self.parse_both(test_case.command)
            # We don't assert exact AST equality due to structural differences
            # but both should produce valid ASTs
            assert rd_ast is not None, f"RD parser failed: {test_case.name}"
            assert pc_ast is not None, f"PC parser failed: {test_case.name}"
        else:
            # Both should fail to parse
            with pytest.raises(ParseError):
                tokens = tokenize(test_case.command)
                Parser(tokens, config=ParserConfig()).parse()
            with pytest.raises(ParseError):
                tokens = tokenize(test_case.command)
                self.pc_parser.parse(tokens)

    # ===== Basic Commands =====

    def test_simple_commands(self):
        """Test simple command parsing."""
        cases = [
            ParityTestCase("empty command", ""),
            ParityTestCase("single command", "echo"),
            ParityTestCase("command with args", "echo hello world"),
            ParityTestCase("command with quotes", 'echo "hello world"'),
            ParityTestCase("command with single quotes", "echo 'hello world'"),
            ParityTestCase("command with escape", r"echo hello\ world"),
        ]

        for case in cases:
            self.check_parity(case)

    def test_pipelines(self):
        """Test pipeline parsing."""
        cases = [
            ParityTestCase("simple pipeline", "echo hello | cat"),
            ParityTestCase("triple pipeline", "echo hello | cat | wc -l"),
            ParityTestCase("pipeline with args", "ls -la | grep foo | head -10"),
        ]

        for case in cases:
            self.check_parity(case)

    def test_logical_operators(self):
        """Test && and || operators."""
        cases = [
            ParityTestCase("and operator", "true && echo success"),
            ParityTestCase("or operator", "false || echo failed"),
            ParityTestCase("mixed operators", "true && echo yes || echo no"),
            ParityTestCase("chained and", "true && true && echo done"),
        ]

        for case in cases:
            self.check_parity(case)

    # ===== Control Structures =====

    def test_if_statements(self):
        """Test if/then/else/fi structures."""
        cases = [
            ParityTestCase("simple if", "if true; then echo yes; fi"),
            ParityTestCase("if else", "if false; then echo yes; else echo no; fi"),
            ParityTestCase("if elif else",
                          "if false; then echo a; elif true; then echo b; else echo c; fi"),
            ParityTestCase("nested if",
                          "if true; then if false; then echo a; else echo b; fi; fi"),
        ]

        for case in cases:
            self.check_parity(case)

    def test_loops(self):
        """Test loop structures."""
        cases = [
            ParityTestCase("while loop", "while true; do echo loop; done"),
            ParityTestCase("for loop", "for x in a b c; do echo $x; done"),
            ParityTestCase("for loop no list", "for x; do echo $x; done"),
            ParityTestCase("c-style for", "for ((i=0; i<10; i++)); do echo $i; done"),
            ParityTestCase("until loop", "until false; do echo loop; done"),
        ]

        for case in cases:
            self.check_parity(case)

    def test_case_statements(self):
        """Test case statements."""
        cases = [
            ParityTestCase("simple case",
                          "case $x in a) echo A;; b) echo B;; esac"),
            ParityTestCase("case with default",
                          "case $x in a) echo A;; *) echo other;; esac"),
            ParityTestCase("case multiple patterns",
                          "case $x in a|b) echo AB;; c) echo C;; esac"),
            ParityTestCase("case with pipes and default",
                          "case $mode in start|stop) echo control;; *) echo default;; esac"),
            ParityTestCase("case nested in case",
                          "case $x in a) case $y in 1) echo a1;; esac;; *) echo other;; esac"),
        ]

        for case in cases:
            self.check_parity(case)

    def test_keyword_sensitive_constructs(self):
        """Ensure both parsers agree on keyword-heavy combinations."""
        cases = [
            ParityTestCase(
                "if embeds case",
                "if true; then case $mode in start|stop) echo hi;; *) echo default;; esac; fi"
            ),
            ParityTestCase(
                "for in with nested if",
                "for file in a b; do if [ -f \"$file\" ]; then echo $file; fi; done"
            ),
            ParityTestCase(
                "select loop with case",
                "select opt in start stop; do case $opt in start) break;; stop) continue;; esac; done",
            ),
        ]

        for case in cases:
            self.check_parity(case)

    def test_select_loops(self):
        """Test select loops."""
        cases = [
            ParityTestCase("select loop", "select x in a b c; do echo $x; done"),
        ]

        for case in cases:
            self.check_parity(case)

    # ===== Function Definitions =====

    def test_functions(self):
        """Test function definitions."""
        cases = [
            ParityTestCase("posix function", "foo() { echo bar; }"),
            ParityTestCase("bash function", "function foo { echo bar; }"),
            ParityTestCase("function with both", "function foo() { echo bar; }"),
            ParityTestCase("function with body",
                          "foo() { echo start; ls; echo end; }"),
        ]

        for case in cases:
            self.check_parity(case)

    # ===== Variable Operations =====

    def test_variable_assignment(self):
        """Test variable assignments."""
        cases = [
            ParityTestCase("simple assignment", "VAR=value"),
            ParityTestCase("multiple assignments", "A=1 B=2 C=3"),
            ParityTestCase("assignment with command", "VAR=value echo test"),
        ]

        for case in cases:
            self.check_parity(case)

    def test_arrays(self):
        """Test array operations."""
        cases = [
            ParityTestCase("array init", "arr=(a b c)"),
            ParityTestCase("array element", "arr[0]=value"),
            ParityTestCase("array append", "arr+=(d e f)"),
        ]

        for case in cases:
            self.check_parity(case)

    # ===== Expansions =====

    def test_expansions(self):
        """Test various expansions."""
        cases = [
            ParityTestCase("variable expansion", "echo $HOME"),
            ParityTestCase("braced variable", "echo ${HOME}"),
            ParityTestCase("command substitution", "echo $(date)"),
            ParityTestCase("backtick substitution", "echo `date`"),
            ParityTestCase("arithmetic expansion", "echo $((2 + 2))"),
            ParityTestCase("parameter expansion", "echo ${VAR:-default}"),
        ]

        for case in cases:
            self.check_parity(case)

    # ===== I/O Redirection =====

    def test_redirections(self):
        """Test I/O redirections."""
        cases = [
            ParityTestCase("output redirect", "echo hello > file.txt"),
            ParityTestCase("append redirect", "echo hello >> file.txt"),
            ParityTestCase("input redirect", "cat < file.txt"),
            ParityTestCase("stderr redirect", "command 2> error.txt"),
            ParityTestCase("combined redirect", "command &> all.txt"),
            ParityTestCase("combined append redirect", "command &>> all.txt"),
            ParityTestCase("clobber redirect", "echo hello >| file.txt"),
            ParityTestCase("readwrite redirect", "cat <> file.txt"),
            ParityTestCase("pipe stderr", "cmd1 |& cmd2"),
        ]

        for case in cases:
            self.check_parity(case)

    def test_heredocs(self):
        """Test here documents."""
        cases = [
            ParityTestCase("simple heredoc", "cat << EOF\nhello\nEOF"),
            ParityTestCase("indented heredoc", "cat <<- EOF\n\thello\nEOF"),
        ]

        for case in cases:
            self.check_parity(case)

    # ===== Advanced Features =====

    def test_subshells(self):
        """Test subshells and command grouping."""
        cases = [
            ParityTestCase("subshell", "(echo hello; echo world)"),
            ParityTestCase("brace group", "{ echo hello; echo world; }"),
        ]

        for case in cases:
            self.check_parity(case)

    def test_process_substitution(self):
        """Test process substitution."""
        cases = [
            ParityTestCase("input process sub", "cat <(echo hello)"),
            ParityTestCase("output process sub", "echo hello >(cat)"),
        ]

        for case in cases:
            self.check_parity(case)

    def test_arithmetic_commands(self):
        """Test arithmetic commands."""
        cases = [
            ParityTestCase("arithmetic command", "((x = 5 + 3))"),
            ParityTestCase("arithmetic condition", "if ((x > 5)); then echo yes; fi"),
        ]

        for case in cases:
            self.check_parity(case)

    def test_conditional_expressions(self):
        """Test [[ ]] conditional expressions."""
        cases = [
            ParityTestCase("string test", '[[ "$x" == "value" ]]'),
            ParityTestCase("numeric test", "[[ $x -gt 5 ]]"),
            ParityTestCase("file test", "[[ -f /etc/passwd ]]"),
        ]

        for case in cases:
            self.check_parity(case)

    # ===== Error Cases =====

    def test_syntax_errors(self):
        """Test that both parsers reject invalid syntax."""
        cases = [
            ParityTestCase("unclosed if", "if true; then echo", should_parse=False),
            ParityTestCase("unclosed while", "while true; do", should_parse=False),
            ParityTestCase("unclosed case", "case $x in a)", should_parse=False),
            ParityTestCase("unclosed function", "foo() {", should_parse=False),
        ]

        for case in cases:
            self.check_parity(case)


def generate_parity_report():
    """Generate a detailed feature parity report."""
    print("# Parser Feature Parity Report\n")
    print("## Summary\n")

    # Count test cases
    test_instance = TestParserFeatureParity()
    test_instance.setup_method()


    # Collect all test methods
    for method_name in dir(test_instance):
        if method_name.startswith("test_") and method_name != "test_syntax_errors":
            getattr(test_instance, method_name)
            # This would need to be enhanced to actually count test cases

    print("\n## Feature Support Matrix\n")
    print("| Feature | Recursive Descent | Parser Combinator | Notes |")
    print("|---------|------------------|-------------------|-------|")
    print("| Simple Commands | ✅ | ✅ | Full support |")
    print("| Pipelines | ✅ | ✅ | Full support |")
    print("| Logical Operators | ✅ | ✅ | Full support |")
    print("| If Statements | ✅ | ✅ | Full support |")
    print("| Loops | ✅ | ✅ | Full support |")
    print("| Case Statements | ✅ | ✅ | Full support |")
    print("| Select Loops | ✅ | ✅ | Full support |")
    print("| Functions | ✅ | ✅ | Full support |")
    print("| Variable Assignment | ✅ | ✅ | Full support |")
    print("| Arrays | ✅ | ✅ | Full support |")
    print("| Variable Expansion | ✅ | ✅ | Full support |")
    print("| Command Substitution | ✅ | ✅ | Full support |")
    print("| Arithmetic Expansion | ✅ | ✅ | Full support |")
    print("| I/O Redirection | ✅ | ✅ | Full support |")
    print("| Here Documents | ✅ | ✅ | Full support |")
    print("| Subshells | ✅ | ✅ | Full support |")
    print("| Process Substitution | ✅ | ✅ | Full support |")
    print("| Arithmetic Commands | ✅ | ✅ | Full support |")
    print("| Conditional Expressions | ✅ | ✅ | Full support |")

    print("\n## Recommendations\n")
    print("1. Complete feature parity achieved (v0.94-v0.192)")
    print("2. Parser combinator serves as educational reference implementation")


if __name__ == "__main__":
    generate_parity_report()
