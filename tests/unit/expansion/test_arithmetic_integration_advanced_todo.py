"""Advanced arithmetic expansion integration tests.

Originally a skipped "roadmap" module ("NOT YET WORKING"), but most of these
features are now implemented. As of the 2026-06-06 audit the class-level skip
was removed and each case verified against bash:

  - Passing now (enabled): arithmetic in parameter-expansion substring
    offset/length, pattern removal, process substitution, case patterns,
    deeply-nested command/arithmetic substitution, and deep arithmetic nesting.
  - Genuine remaining gaps (xfail): brace *list* expansion with arithmetic
    items, arithmetic in fd-duplication targets, and graceful recovery from an
    arithmetic error inside an array index.
  - One case had a wrong expectation: bash does NOT expand a brace *range*
    whose endpoints are `$((...))` (brace expansion precedes arithmetic), so
    the expected output is the literal `{5..8}`, which psh already matches.
"""


class TestArithmeticIntegrationAdvanced:
    """Advanced arithmetic integration tests (verified against bash)."""

    # Parameter expansion with arithmetic (NOT WORKING YET)

    def test_arithmetic_in_parameter_expansion_substring(self, shell, capsys):
        """Test arithmetic in parameter expansion substring operations.

        FAILS: Parameter expansion with arithmetic ${str:$((expr)):$((expr))} not supported yet.
        Expected: Should support arithmetic expressions in substring offset and length.
        """
        shell.run_command('str="hello world"')

        # Test ${str:$((2+1)):$((2*2))} - substring from position 3, length 4
        result = shell.run_command('echo "${str:$((2+1)):$((2*2))}"')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "lo w"  # str[3:7] = "lo w"

    def test_arithmetic_in_parameter_expansion_offset_length(self, shell, capsys):
        """Test arithmetic for both offset and length in parameter expansion.

        FAILS: Complex parameter expansion with nested arithmetic not supported.
        Expected: Should evaluate arithmetic in both offset and length positions.
        """
        shell.run_command('text="abcdefghijk"')
        shell.run_command('start=2')
        shell.run_command('len=3')

        # Test ${text:$((start*2)):$((len+1))}
        result = shell.run_command('echo "${text:$((start*2)):$((len+1))}"')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "efgh"  # text[4:8] = "efgh"

    def test_arithmetic_in_parameter_expansion_pattern_matching(self, shell, capsys):
        """Test arithmetic in parameter expansion pattern operations.

        FAILS: Pattern matching with arithmetic expressions not supported.
        Expected: Should support dynamic pattern generation using arithmetic.
        """
        shell.run_command('filename="document.txt.backup"')
        shell.run_command('n=3')

        # Test complex pattern with arithmetic - this is quite advanced
        result = shell.run_command('echo "${filename%.*}"')  # Simpler version for now
        assert result == 0
        capsys.readouterr()
        # This test needs more sophisticated pattern support

    # Process substitution integration (NOT WORKING YET)

    def test_arithmetic_with_process_substitution(self, shell, capsys):
        """Test arithmetic in process substitution contexts.

        FAILS: Process substitution not implemented yet.
        Expected: Should support <(command) and >(command) with arithmetic.
        """
        # Test diff <(echo $((5+3))) <(echo 8)
        result = shell.run_command('diff <(echo $((5+3))) <(echo 8) >/dev/null; echo $?')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "0"  # Should be identical

    # Brace expansion with arithmetic (NOT WORKING YET)

    def test_arithmetic_with_brace_expansion(self, shell, capsys):
        """Test arithmetic with brace expansion.

        bash expands `{$((1)),$((2)),$((3))}` to `1 2 3` (brace list split, then
        arithmetic); psh now does too (token-level brace expansion carries the
        $((...)) items through as opaque units).
        """
        # Test echo {$((1)),$((2)),$((3))}
        result = shell.run_command('echo {$((1)),$((2)),$((3))}')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "1 2 3"

    def test_arithmetic_in_brace_expansion_ranges(self, shell, capsys):
        """Brace *range* endpoints are not arithmetic-expanded (matches bash).

        Brace expansion runs before arithmetic, so `{$((start))..$((end))}` has
        non-integer endpoints at brace-expansion time and is left intact; the
        arithmetic then yields the literal `{5..8}`. bash behaves identically —
        the original "5 6 7 8" expectation was incorrect.
        """
        shell.run_command('start=5')
        shell.run_command('end=8')

        # Test echo {$((start))..$((end))}
        result = shell.run_command('echo {$((start))..$((end))}')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "{5..8}"

    # Complex redirection with arithmetic (PARTIALLY WORKING)

    def test_arithmetic_in_file_descriptor_redirection(self):
        """Test arithmetic in file descriptor specifications.

        `>&$((1+1))` resolves the dup target at runtime (the lexer emits a
        bare `>&` operator, the parser keeps the expansion as the target, and
        FileRedirector.resolve_dynamic_dup expands it to an fd number).

        Runs psh in a SUBPROCESS: the fd dance (`2>&1 >&$((1+1))`) binds the
        builtin's stream to a fresh dup of the target fd's open description
        (not an alias of the `sys.stdout` object), so the output only shows at
        the fd level — `capsys`, which swaps the Python stream objects, cannot
        observe it. Expectation verified against bash 5.2: "hello" reaches
        stdout, exit 0.
        """
        import subprocess
        import sys
        cmd = 'echo "hello" 2>&1 >&$((1+1)) 2>/dev/null || echo "redirect test"'
        psh = subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                             capture_output=True, text=True)
        assert psh.returncode == 0
        assert psh.stdout == 'hello\n'

    # Case statement pattern arithmetic (NOT WORKING YET)

    def test_arithmetic_in_case_patterns(self, shell, capsys):
        """Test arithmetic expansion in case statement patterns.

        FAILS: Case patterns with arithmetic evaluation not supported.
        Expected: Should evaluate arithmetic in case patterns dynamically.
        """
        shell.run_command('value=15')

        # Test case with arithmetic in pattern matching
        result = shell.run_command('''
        value=15
        case $value in
            $((10+5))) echo "matched fifteen" ;;
            $((20-5))) echo "also fifteen" ;;
            *) echo "no match" ;;
        esac
        ''')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "matched fifteen"

    # Advanced nested expansion combinations (COMPLEX)

    def test_ultra_complex_nested_expansions(self, shell, capsys):
        """Test extremely complex nested expansion combinations.

        FAILS: Multiple levels of nesting with different expansion types.
        Expected: Should handle arbitrary nesting depth and combinations.
        """
        shell.run_command('arr=(10 20 30)')
        shell.run_command('indices=(0 1 2)')
        shell.run_command('calc() { echo $(($1 * $2)); }')

        # Test $(calc ${arr[${indices[$((0))]}]} $(($(echo 3) + 1)))
        # This is intentionally very complex
        result = shell.run_command('echo $(calc ${arr[${indices[$((0))]}]} $(($(echo 3) + 1)))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "40"  # calc(arr[indices[0]], 4) = calc(10, 4) = 40

    # Error recovery in complex contexts (NEEDS WORK)

    def test_arithmetic_error_recovery_in_complex_context(self, shell, capsys):
        """Test error recovery with arithmetic in complex nested contexts.

        A division-by-zero inside an array index DISCARDS the rest of that
        line (bash: the ``||`` tail never runs) without corrupting parser
        state: the next command runs normally. One run_command call per
        input line, mirroring how a script/stdin feeds the shell (a single
        multi-line run_command string is one buffer, i.e. one "line").
        """
        shell.run_command('arr=(1 2 3)')
        shell.run_command('echo "before"')
        result = shell.run_command(
            'echo "${arr[$(( 1 / 0 ))]}" 2>/dev/null || echo "error handled"')
        assert result == 1   # discard-line: the || tail is killed (bash)
        result = shell.run_command('echo "after"')
        assert result == 0
        captured = capsys.readouterr()
        lines = captured.out.strip().split('\n')
        assert "before" in lines
        assert "after" in lines
        assert "error handled" not in lines
        assert "ivision by zero" in captured.err

    # Performance stress tests (MAY TIMEOUT)

    def test_extreme_nesting_performance(self, shell, capsys):
        """Test performance with extremely nested arithmetic expressions.

        MAY TIMEOUT: Very deep nesting may cause performance issues.
        Expected: Should handle reasonable nesting depth efficiently.
        """
        # Create an extremely deep expression (may cause timeout)
        expr = "1"
        for _ in range(50):  # This might be too deep
            expr = f"({expr} + 1)"

        result = shell.run_command(f'echo $(({expr}))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "51"  # 1 + 50 = 51


# Additional notes for future development:

"""
IMPLEMENTATION PRIORITIES FOR FUTURE DEVELOPMENT:

HIGH PRIORITY:
1. Parameter expansion with arithmetic in offset/length positions
   - ${var:$((expr)):$((expr))} syntax
   - Critical for advanced shell scripting

2. Brace expansion integration
   - {$((expr1)),$((expr2))} syntax
   - Range expansion {$((start))..$((end))}

MEDIUM PRIORITY:
3. Case pattern arithmetic evaluation
   - Dynamic pattern generation using arithmetic
   - Important for complex case statements

4. Advanced error recovery
   - Better error handling in nested contexts
   - Graceful degradation without parser corruption

LOW PRIORITY:
5. Process substitution integration
   - <(command) and >(command) with arithmetic
   - Less commonly used feature

6. Extreme nesting optimization
   - Performance improvements for very deep nesting
   - Stack overflow prevention

IMPLEMENTATION NOTES:
- Parameter expansion is the most critical missing piece
- Most command substitution integration already works well
- Array integration is excellent and comprehensive
- Control structure integration is solid
- Error handling is generally good but could be more robust in edge cases

TESTING STRATEGY:
- Keep these advanced tests as skip markers
- Gradually enable them as features are implemented
- Use them as acceptance criteria for new features
- Update expected behaviors as implementation evolves
"""
