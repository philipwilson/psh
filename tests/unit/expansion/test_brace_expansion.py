"""
Unit tests for brace expansion in PSH.

Tests cover:
- Simple list expansion {a,b,c}
- Numeric range expansion {1..10}
- Character range expansion {a..z}
- Nested brace expansion
- Prefix/suffix with brace expansion
- Empty brace handling
- Escaping braces
- Complex combinations
"""



class TestSimpleBraceExpansion:
    """Test simple brace expansion with lists."""

    def test_simple_list(self, shell, capsys):
        """Test basic list expansion."""
        shell.run_command('echo {a,b,c}')
        captured = capsys.readouterr()
        assert captured.out.strip() == "a b c"

    def test_single_item(self, shell, capsys):
        """Test single item (no expansion)."""
        shell.run_command('echo {a}')
        captured = capsys.readouterr()
        # Single item with no comma or range — stays literal
        assert captured.out.strip() == "{a}"

    def test_empty_item(self, shell, capsys):
        """Test empty items in list."""
        shell.run_command('echo {a,,c}')
        captured = capsys.readouterr()
        # Bash does not preserve empty items in echo output
        assert captured.out.strip() == "a c"

    def test_numeric_list(self, shell, capsys):
        """Test numeric list expansion."""
        shell.run_command('echo {1,2,3}')
        captured = capsys.readouterr()
        assert captured.out.strip() == "1 2 3"

    def test_mixed_list(self, shell, capsys):
        """Test mixed alphanumeric list."""
        shell.run_command('echo {a,1,b,2}')
        captured = capsys.readouterr()
        assert captured.out.strip() == "a 1 b 2"

    def test_spaces_in_list(self, shell, capsys):
        """Test handling of spaces in list."""
        shell.run_command('echo {a, b, c}')
        captured = capsys.readouterr()
        # Spaces might be preserved or trimmed
        assert "a" in captured.out and "b" in captured.out and "c" in captured.out


class TestRangeBraceExpansion:
    """Test brace expansion with ranges."""

    def test_numeric_range_ascending(self, shell, capsys):
        """Test ascending numeric range."""
        shell.run_command('echo {1..5}')
        captured = capsys.readouterr()
        assert captured.out.strip() == "1 2 3 4 5"

    def test_numeric_range_descending(self, shell, capsys):
        """Test descending numeric range."""
        shell.run_command('echo {5..1}')
        captured = capsys.readouterr()
        assert captured.out.strip() == "5 4 3 2 1"

    def test_numeric_range_with_step(self, shell, capsys):
        """Test numeric range with step."""
        shell.run_command('echo {1..10..2}')
        captured = capsys.readouterr()
        assert captured.out.strip() == "1 3 5 7 9"

        shell.run_command('echo {10..1..2}')
        captured = capsys.readouterr()
        assert captured.out.strip() == "10 8 6 4 2"

    def test_zero_padded_range(self, shell, capsys):
        """Test zero-padded numeric range."""
        shell.run_command('echo {01..05}')
        captured = capsys.readouterr()
        assert captured.out.strip() == "01 02 03 04 05"

        shell.run_command('echo {001..010}')
        captured = capsys.readouterr()
        # Should preserve zero padding
        assert "001" in captured.out and "010" in captured.out

    def test_negative_range(self, shell, capsys):
        """Test range with negative numbers."""
        shell.run_command('echo {-2..2}')
        captured = capsys.readouterr()
        assert captured.out.strip() == "-2 -1 0 1 2"

    def test_character_range(self, shell, capsys):
        """Test character range expansion."""
        shell.run_command('echo {a..e}')
        captured = capsys.readouterr()
        assert captured.out.strip() == "a b c d e"

        shell.run_command('echo {z..x}')
        captured = capsys.readouterr()
        assert captured.out.strip() == "z y x"

    def test_uppercase_range(self, shell, capsys):
        """Test uppercase character range."""
        shell.run_command('echo {A..D}')
        captured = capsys.readouterr()
        assert captured.out.strip() == "A B C D"


class TestPrefixSuffixExpansion:
    """Test brace expansion with prefixes and suffixes."""

    def test_prefix(self, shell, capsys):
        """Test brace expansion with prefix."""
        shell.run_command('echo pre{a,b,c}')
        captured = capsys.readouterr()
        assert captured.out.strip() == "prea preb prec"

    def test_suffix(self, shell, capsys):
        """Test brace expansion with suffix."""
        shell.run_command('echo {a,b,c}post')
        captured = capsys.readouterr()
        assert captured.out.strip() == "apost bpost cpost"

    def test_prefix_and_suffix(self, shell, capsys):
        """Test brace expansion with both prefix and suffix."""
        shell.run_command('echo pre{a,b,c}post')
        captured = capsys.readouterr()
        assert captured.out.strip() == "preapost prebpost precpost"

    def test_multiple_prefixes(self, shell, capsys):
        """Test multiple brace expansions."""
        shell.run_command('echo {a,b}{1,2}')
        captured = capsys.readouterr()
        assert captured.out.strip() == "a1 a2 b1 b2"

    def test_file_extension_pattern(self, shell, capsys):
        """Test common file extension pattern."""
        shell.run_command('echo file.{txt,log,bak}')
        captured = capsys.readouterr()
        assert captured.out.strip() == "file.txt file.log file.bak"

    def test_path_pattern(self, shell, capsys):
        """Test path-like pattern."""
        shell.run_command('echo /usr/{bin,lib,share}')
        captured = capsys.readouterr()
        assert captured.out.strip() == "/usr/bin /usr/lib /usr/share"


class TestNestedBraceExpansion:
    """Test nested brace expansion."""

    def test_nested_lists(self, shell, capsys):
        """Test nested list expansion."""
        shell.run_command('echo {a,{b,c},d}')
        captured = capsys.readouterr()
        assert captured.out.strip() == "a b c d"

    def test_nested_with_prefix(self, shell, capsys):
        """Test nested expansion with prefixes."""
        shell.run_command('echo {a,b{1,2},c}')
        captured = capsys.readouterr()
        assert captured.out.strip() == "a b1 b2 c"

    def test_deeply_nested(self, shell, capsys):
        """Test deeply nested expansion."""
        shell.run_command('echo {{a,b},{c,d}}')
        captured = capsys.readouterr()
        assert captured.out.strip() == "a b c d"

    def test_nested_ranges(self, shell, capsys):
        """Test nested range expansion."""
        shell.run_command('echo {{1..3},{a..c}}')
        captured = capsys.readouterr()
        assert captured.out.strip() == "1 2 3 a b c"


class TestComplexBracePatterns:
    """Test complex brace expansion patterns."""

    def test_multiple_expansions(self, shell, capsys):
        """Test multiple brace expansions in one command."""
        shell.run_command('echo {a,b} {1,2}')
        captured = capsys.readouterr()
        # Note: This is different from {a,b}{1,2}
        assert captured.out.strip() == "a b 1 2"

    def test_cartesian_product(self, shell, capsys):
        """Test cartesian product of expansions."""
        shell.run_command('echo {a,b}{1,2}{x,y}')
        captured = capsys.readouterr()
        expected = "a1x a1y a2x a2y b1x b1y b2x b2y"
        assert captured.out.strip() == expected

    def test_mixed_types(self, shell, capsys):
        """Test mixing list and range expansions."""
        shell.run_command('echo {a,b,1..3}')
        captured = capsys.readouterr()
        # Bash does not expand ranges within comma lists
        assert captured.out.strip() == "a b 1..3"

    def test_empty_expansion(self, shell, capsys):
        """Test empty brace expansion."""
        shell.run_command('echo a{,}b')
        captured = capsys.readouterr()
        assert captured.out.strip() == "ab ab"

        shell.run_command('echo {,a,b}')
        captured = capsys.readouterr()
        # PSH doesn't preserve empty items
        assert captured.out.strip() == "a b"


class TestBraceExpansionEscaping:
    """Test escaping and quoting with brace expansion."""

    def test_escaped_braces(self, shell, capsys):
        """Test escaped braces."""
        shell.run_command('echo \\{a,b,c\\}')
        captured = capsys.readouterr()
        assert captured.out.strip() == "{a,b,c}"

    def test_quoted_braces(self, shell, capsys):
        """Test quoted braces."""
        shell.run_command('echo "{a,b,c}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "{a,b,c}"

        shell.run_command("echo '{a,b,c}'")
        captured = capsys.readouterr()
        assert captured.out.strip() == "{a,b,c}"

    def test_partial_quoting(self, shell, capsys):
        """Test partial quoting."""
        shell.run_command('echo {"a,b",c}')
        captured = capsys.readouterr()
        # The quoted part should not expand
        assert "a,b" in captured.out and "c" in captured.out

    def test_special_chars_in_expansion(self, shell, capsys):
        """Test special characters in expansion.

        Brace expansion now happens at the token level (not as string
        preprocessing), so {$,#,@} expands word-wise and '#' is not turned
        into a comment.
        """
        shell.run_command('echo {$,#,@}')
        captured = capsys.readouterr()
        assert captured.out.strip() == "$ # @"


class TestBraceExpansionInContext:
    """Test brace expansion in various contexts."""

    def test_in_for_loop(self, shell, capsys):
        """Test brace expansion in for loop."""
        cmd = '''
        for i in {1..3}; do
            echo "Item: $i"
        done
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert "Item: 1" in captured.out
        assert "Item: 2" in captured.out
        assert "Item: 3" in captured.out

    def test_with_command_substitution(self, shell, capsys):
        """Test brace expansion with command substitution."""
        shell.run_command('echo $(echo {a,b,c})')
        captured = capsys.readouterr()
        assert captured.out.strip() == "a b c"

    def test_in_variable_assignment(self, shell, capsys):
        """Brace expansion does NOT occur in a scalar assignment (like bash)."""
        shell.run_command('FILES={a,b,c}')
        capsys.readouterr()
        shell.run_command('echo "$FILES"')
        captured = capsys.readouterr()
        assert captured.out.strip() == '{a,b,c}'
        # Might be literal "{a,b,c}" or expanded

    def test_with_glob_pattern(self, shell, capsys):
        """Test brace expansion with glob patterns."""
        # Create test files
        shell.run_command('touch test1.txt test2.txt test1.log test2.log')
        shell.run_command('echo test{1,2}.{txt,log}')
        captured = capsys.readouterr()
        assert "test1.txt" in captured.out
        assert "test2.log" in captured.out
        # Clean up
        shell.run_command('rm -f test*.txt test*.log')


class TestBraceExpansionEdgeCases:
    """Test edge cases in brace expansion."""

    def test_invalid_range(self, shell, capsys):
        """Test invalid range syntax."""
        shell.run_command('echo {a..1}')
        captured = capsys.readouterr()
        # Should not expand (mixing letters and numbers)
        assert captured.out.strip() == "{a..1}"

    def test_single_dot_range(self, shell, capsys):
        """Test single dot (not a range)."""
        shell.run_command('echo {a.b}')
        captured = capsys.readouterr()
        assert captured.out.strip() == "{a.b}"

    def test_unclosed_brace(self, shell, capsys):
        """Test unclosed brace."""
        shell.run_command('echo {a,b,c')
        captured = capsys.readouterr()
        assert captured.out.strip() == "{a,b,c"

    def test_empty_braces(self, shell, capsys):
        """Test empty braces."""
        shell.run_command('echo {}')
        captured = capsys.readouterr()
        assert captured.out.strip() == "{}"

    def test_very_long_expansion(self):
        """Test very long expansion.

        Uses subprocess because the pipeline forks child processes
        whose output isn't captured by in-process fixtures.
        """
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c', 'echo {1..100} | wc -w'],
            capture_output=True, text=True
        )
        assert result.stdout.strip() == "100"


class TestBraceExpansionWithExpansions:
    """Brace *list* items may contain $((..)), $(..), or $var.

    Brace expansion is textual and runs before parameter/command/arithmetic
    expansion, so the items are split first and expanded afterwards. The
    expansion parts are carried through the Word-stage brace expander as
    opaque placeholders (see WordBraceExpander).
    """

    def test_list_of_arithmetic_items(self, shell, capsys):
        shell.run_command('echo {$((1)),$((2)),$((3))}')
        assert capsys.readouterr().out.strip() == "1 2 3"

    def test_list_of_command_subs(self, shell, capsys):
        shell.run_command('echo {$(echo p),$(echo q)}')
        assert capsys.readouterr().out.strip() == "p q"

    def test_list_of_variable_items(self, shell, capsys):
        shell.run_command('a=X; b=Y; echo {$a,$b}')
        assert capsys.readouterr().out.strip() == "X Y"

    def test_arithmetic_items_with_prefix_suffix(self, shell, capsys):
        shell.run_command('echo pre{$((1)),$((2))}post')
        assert capsys.readouterr().out.strip() == "pre1post pre2post"

    def test_arithmetic_items_cross_product(self, shell, capsys):
        shell.run_command('echo {$((1)),$((2))}{x,y}')
        assert capsys.readouterr().out.strip() == "1x 1y 2x 2y"

    def test_mixed_literal_and_arithmetic_items(self, shell, capsys):
        shell.run_command('echo {$((1)),b}')
        assert capsys.readouterr().out.strip() == "1 b"

    def test_quoted_braces_not_expanded(self, shell, capsys):
        shell.run_command('echo "{$((1)),$((2))}"')
        # Quoted: braces are literal; only the arithmetic expands.
        assert capsys.readouterr().out.strip() == "{1,2}"

    def test_range_with_variable_endpoints_stays_literal(self, shell, capsys):
        # Brace expansion precedes arithmetic, so $-endpoints are not integers
        # at brace time; bash leaves this literal too.
        shell.run_command('s=1; e=3; echo {$s..$e}')
        assert capsys.readouterr().out.strip() == "{1..3}"

    def test_variable_name_fusion_reforms_names(self, shell, capsys):
        # Brace expansion precedes parameter expansion: `$x{1,2}` becomes the
        # parameters $x1/$x2, NOT $x with suffixes (bash-verified).
        shell.run_command('x=foo; x1=A; x2=B; echo $x{1,2}')
        assert capsys.readouterr().out.strip() == "A B"

    def test_variable_name_fusion_unset_names_empty(self, shell, capsys):
        shell.run_command('x=foo; echo $x{1,2}')
        assert capsys.readouterr().out.strip() == ""

    def test_no_fusion_for_special_or_positional(self, shell, capsys):
        # `$?`/`$1` are delimited parameters; adjacent chars stay literal.
        shell.run_command('false; echo $?{a,b}')
        assert capsys.readouterr().out.strip() == "1a 1b"
        shell.run_command('set -- P; echo $1{a,b}')
        assert capsys.readouterr().out.strip() == "Pa Pb"

    def test_quoted_char_blocks_fusion(self, shell, capsys):
        # A quote boundary ends the name, exactly as in bash.
        shell.run_command('v=V; echo $v"1"{2,3}')
        assert capsys.readouterr().out.strip() == "V12 V13"


class TestBraceExpansionQuotedAdjacency:
    """Quoted expansions adjacent to braces keep their expansion metadata.

    `"$f"{1,2}` rewrites the token stream, but the rebuilt STRING tokens must
    still carry the `$f` expansion part (reappraisal #15 B1) — all cases
    bash-verified (tmp/brace_truth_table.sh).
    """

    def test_quoted_variable_with_brace_suffix(self, shell, capsys):
        shell.run_command('f=F; echo "$f"{1,2}')
        assert capsys.readouterr().out.strip() == "F1 F2"

    def test_quoted_variable_inside_brace_item(self, shell, capsys):
        shell.run_command('f=F; echo {1,"$f"2}')
        assert capsys.readouterr().out.strip() == "1 F2"

    def test_multi_part_quoted_string(self, shell, capsys):
        shell.run_command('f=F; echo "${f}bar"{1,2}')
        assert capsys.readouterr().out.strip() == "Fbar1 Fbar2"

    def test_quoted_command_sub(self, shell, capsys):
        shell.run_command('echo "$(echo x)"{1,2}')
        assert capsys.readouterr().out.strip() == "x1 x2"

    def test_quoted_arithmetic(self, shell, capsys):
        shell.run_command('echo "$((1+1))"{a,b}')
        assert capsys.readouterr().out.strip() == "2a 2b"

    def test_nested_braces_with_quoted_var(self, shell, capsys):
        shell.run_command('f=F; echo {a,{b,c}}"$f"')
        assert capsys.readouterr().out.strip() == "aF bF cF"

    def test_single_quoted_dollar_stays_literal(self, shell, capsys):
        shell.run_command("f=F; echo '$f'{1,2}")
        assert capsys.readouterr().out.strip() == "$f1 $f2"

    def test_quoted_value_not_field_split(self, shell, capsys):
        shell.run_command('f="a b"; printf "<%s>" "$f"{1,2}')
        assert capsys.readouterr().out.strip() == "<a b1><a b2>"

    def test_quoted_value_not_globbed(self, shell, capsys):
        shell.run_command('f="*"; printf "<%s>" "$f"{1,2}')
        assert capsys.readouterr().out.strip() == "<*1><*2>"

    def test_empty_alternative_keeps_expansion(self, shell, capsys):
        shell.run_command('f=F; printf "<%s>" "$f"{,}')
        assert capsys.readouterr().out.strip() == "<F><F>"

    def test_quoted_at_distributes(self, shell, capsys):
        shell.run_command('set -- p q; printf "<%s>" "$@"{1,2}')
        assert capsys.readouterr().out.strip() == "<p><q1><p><q2>"

    def test_quoted_var_with_range(self, shell, capsys):
        shell.run_command('f=F; echo "$f"{1..3}')
        assert capsys.readouterr().out.strip() == "F1 F2 F3"

    def test_quoted_empty_string_item_survives(self, shell, capsys):
        shell.run_command('printf "<%s>" {a,""}')
        assert capsys.readouterr().out.strip() == "<a><>"

    def test_assignment_word_still_suppressed(self, shell, capsys):
        shell.run_command('f=F; x="$f"{1,2}; echo "$x"')
        assert capsys.readouterr().out.strip() == "F{1,2}"

    def test_in_eval(self, shell, capsys):
        shell.run_command("f=F; eval 'echo \"$f\"{1,2}'")
        assert capsys.readouterr().out.strip() == "F1 F2"

    def test_in_command_substitution(self, shell, capsys):
        shell.run_command('f=F; echo $(echo "$f"{1,2})')
        assert capsys.readouterr().out.strip() == "F1 F2"

    def test_in_function(self, shell, capsys):
        shell.run_command('f=F; g() { echo "$f"{1,2}; }; g')
        assert capsys.readouterr().out.strip() == "F1 F2"


class TestBraceExpansionDelimitedAdjacency:
    """Brace-delimited expansions participate in brace adjacency.

    `${v}`, `${a[0]}`, `${v:-d}`, backticks, and process subs are delimited —
    they can never fuse with adjacent text, so `${v}{1,2}` must expand
    (reappraisal #15 B2) — all cases bash-verified.
    """

    def test_braced_variable_with_brace_suffix(self, shell, capsys):
        shell.run_command('v=V; echo ${v}{1,2}')
        assert capsys.readouterr().out.strip() == "V1 V2"

    def test_array_element_with_brace_suffix(self, shell, capsys):
        shell.run_command('a=(1 2); echo ${a[0]}{x,y}')
        assert capsys.readouterr().out.strip() == "1x 1y"

    def test_unquoted_braced_var_inside_item(self, shell, capsys):
        shell.run_command('f=F; echo {a,${f}}b')
        assert capsys.readouterr().out.strip() == "ab Fb"

    def test_operator_form_with_brace_suffix(self, shell, capsys):
        shell.run_command('v=V; echo ${v:-D}{1,2}')
        assert capsys.readouterr().out.strip() == "V1 V2"
        shell.run_command('echo ${unset_zz:-D}{1,2}')
        assert capsys.readouterr().out.strip() == "D1 D2"

    def test_backtick_with_brace_suffix(self, shell, capsys):
        shell.run_command('echo `echo x`{1,2}')
        assert capsys.readouterr().out.strip() == "x1 x2"


class TestCharRangeBackslash:
    """Cross-case char ranges that span the backslash (ASCII 92).

    bash emits an *empty but kept* word at the backslash position (it does NOT
    output a literal `\\`), and unlike an empty list item it is not dropped.
    Verified against bash: `echo {Z..a}` -> `Z [  ] ^ _ ` a` (note the empty
    word between `[` and `]`).
    """

    def test_z_to_a_drops_backslash_keeps_empty_word(self, shell, capsys):
        shell.run_command('set -- {Z..a}; echo "$#"')
        # 8 words: Z [ <empty> ] ^ _ ` a
        assert capsys.readouterr().out.strip() == "8"

    def test_z_to_a_backslash_position_is_empty(self, shell, capsys):
        # Element at the backslash position is empty, not a literal backslash.
        shell.run_command('a=({Z..a}); printf "[%s]" "${a[2]}"')
        assert capsys.readouterr().out.strip() == "[]"

    def test_a_to_z_full_span_has_no_backslash(self, shell, capsys):
        shell.run_command('a=({A..z}); echo "${a[*]}" | tr -d " "')
        out = capsys.readouterr().out.strip()
        assert '\\' not in out

    def test_reverse_range_also_drops_backslash(self, shell, capsys):
        shell.run_command('a=({a..Z}); printf "[%s]" "${a[5]}"')
        # a ` _ ^ ] <empty> [ Z  -> index 5 is the backslash position
        assert capsys.readouterr().out.strip() == "[]"

    def test_range_with_step_skips_backslash(self, shell, capsys):
        # {Z..a..2}: Z(90) \(92 -> empty) ^(94) `(96)
        shell.run_command('set -- {Z..a..2}; echo "$#"')
        assert capsys.readouterr().out.strip() == "4"

    def test_backslash_in_composite_contributes_nothing(self, shell, capsys):
        # x{Z..a}y: the backslash position fuses to "xy" (non-empty, kept).
        shell.run_command('a=(x{Z..a}y); printf "[%s]" "${a[2]}"')
        assert capsys.readouterr().out.strip() == "[xy]"


class TestStrayBraceNeighbors:
    """Stray/unmatched braces around a valid group are literal text and do not
    prevent expanding the valid group (bash: `}{a,b}{` -> `}a{ }b{`)."""

    def test_stray_braces_both_sides(self, shell, capsys):
        shell.run_command('echo }{a,b}{')
        assert capsys.readouterr().out.strip() == "}a{ }b{"

    def test_stray_close_then_group(self, shell, capsys):
        shell.run_command('echo a}{b,c}d')
        assert capsys.readouterr().out.strip() == "a}bd a}cd"

    def test_leading_stray_close(self, shell, capsys):
        shell.run_command('echo }{a,b}')
        assert capsys.readouterr().out.strip() == "}a }b"

    def test_trailing_stray_open(self, shell, capsys):
        shell.run_command('echo {a,b}{')
        assert capsys.readouterr().out.strip() == "a{ b{"

    def test_leading_stray_open(self, shell, capsys):
        shell.run_command('echo {{a,b}')
        assert capsys.readouterr().out.strip() == "{a {b"

    def test_nested_group_with_stray_neighbors(self, shell, capsys):
        shell.run_command('echo }{a,{b,c}}{')
        assert capsys.readouterr().out.strip() == "}a{ }b{ }c{"

    def test_no_group_stays_literal(self, shell, capsys):
        # Genuinely no valid group: unchanged.
        shell.run_command('echo {a,b')
        assert capsys.readouterr().out.strip() == "{a,b"
        shell.run_command('echo a,b}')
        assert capsys.readouterr().out.strip() == "a,b}"
        shell.run_command('echo a}b')
        assert capsys.readouterr().out.strip() == "a}b"

    def test_valid_group_unaffected(self, shell, capsys):
        shell.run_command('echo x{a,b}y')
        assert capsys.readouterr().out.strip() == "xay xby"

    def test_param_expansion_not_treated_as_brace(self, shell, capsys):
        # ${HOME}/{a,b}: ${...} is skipped; only the trailing group expands.
        shell.run_command('HOME=/h; echo ${HOME}/{a,b}')
        assert capsys.readouterr().out.strip() == "/h/a /h/b"


class TestNoBraceExpansionInsideDoubleBrackets:
    """Bash performs NO brace expansion inside [[ ... ]] (reappraisal #17 H4).

    Regex intervals ([[ x =~ [0-9]{1,3} ]]) and brace-shaped patterns
    (a{b,c}) must stay literal; expanding them used to split the word into
    two tokens and hard-break the ]] parse ("Expected DOUBLE_RBRACKET").
    Outside the [[ ]] region — including elsewhere on the same line —
    expansion must still happen.
    """

    def test_regex_interval_idiom(self, shell, capsys):
        # The headline idiom: an ERE interval count.
        rc = shell.run_command('[[ 192 =~ ^[0-9]{1,3}$ ]] && echo ok')
        assert rc == 0
        assert capsys.readouterr().out.strip() == "ok"

    def test_regex_interval_non_match(self, shell, capsys):
        rc = shell.run_command('[[ 1924 =~ ^[0-9]{1,3}$ ]] || echo no')
        assert rc == 0
        assert capsys.readouterr().out.strip() == "no"

    def test_regex_exact_count(self, shell, capsys):
        rc = shell.run_command('[[ aab =~ ^a{2}b$ ]] && echo two')
        assert rc == 0
        assert capsys.readouterr().out.strip() == "two"

    def test_equals_pattern_braces_literal(self, shell, capsys):
        # Pattern a{b,c} is LITERAL inside [[ ]]; it does not match "ab".
        rc = shell.run_command('[[ ab == a{b,c} ]]; echo rc=$?')
        assert rc == 0
        assert capsys.readouterr().out.strip() == "rc=1"

    def test_equals_literal_brace_match(self, shell, capsys):
        rc = shell.run_command('[[ "a{b,c}" == a{b,c} ]] && echo litmatch')
        assert rc == 0
        assert capsys.readouterr().out.strip() == "litmatch"

    def test_range_braces_literal_in_pattern(self, shell, capsys):
        rc = shell.run_command('[[ a2 == a{1..3} ]]; echo rc=$?')
        assert rc == 0
        assert capsys.readouterr().out.strip() == "rc=1"

    def test_lhs_braces_literal(self, shell, capsys):
        rc = shell.run_command('[[ a{1,2} == "a{1,2}" ]] && echo lhs')
        assert rc == 0
        assert capsys.readouterr().out.strip() == "lhs"

    def test_expansion_still_works_outside_on_same_line(self, shell, capsys):
        rc = shell.run_command('echo a{1,2}; [[ x == x ]] && echo b{3,4}')
        assert rc == 0
        assert capsys.readouterr().out == "a1 a2\nb3 b4\n"

    def test_expansion_after_double_bracket_no_space(self, shell, capsys):
        rc = shell.run_command('[[ x == x ]]&&echo t{1,2}')
        assert rc == 0
        assert capsys.readouterr().out.strip() == "t1 t2"

    def test_multiple_regions_one_line(self, shell, capsys):
        rc = shell.run_command(
            '[[ a =~ a{1,2} ]]; echo rc=$?; [[ b == b ]] && echo two; '
            'echo c{5,6}')
        assert rc == 0
        assert capsys.readouterr().out == "rc=0\ntwo\nc5 c6\n"

    def test_inside_if_condition(self, shell, capsys):
        rc = shell.run_command('if [[ 5 =~ ^[0-9]{1,3}$ ]]; then echo yes; fi')
        assert rc == 0
        assert capsys.readouterr().out.strip() == "yes"

    def test_inside_while_condition(self, shell, capsys):
        rc = shell.run_command(
            'i=0; while [[ $i =~ ^[0-9]{1}$ ]]; do i=$((i+10)); done; '
            'echo i=$i')
        assert rc == 0
        assert capsys.readouterr().out.strip() == "i=10"

    def test_inside_case_body(self, shell, capsys):
        rc = shell.run_command(
            'case x in x) [[ 5 =~ ^[0-9]{1,3}$ ]] && echo incase;; esac')
        assert rc == 0
        assert capsys.readouterr().out.strip() == "incase"

    def test_inside_function_body(self, shell, capsys):
        rc = shell.run_command('f() { [[ 42 =~ ^[0-9]{2}$ ]] && echo fn; }; f')
        assert rc == 0
        assert capsys.readouterr().out.strip() == "fn"

    def test_negated_regex(self, shell, capsys):
        rc = shell.run_command('[[ ! 192 =~ ^[a-z]{1,3}$ ]] && echo neg')
        assert rc == 0
        assert capsys.readouterr().out.strip() == "neg"

    def test_double_rbracket_word_outside_region(self, shell, capsys):
        # ]] in non-command position is an ordinary word; braces around it
        # still expand (the expander must not think a region closed/opened).
        rc = shell.run_command('echo x{1,2} ]] y{3,4}')
        assert rc == 0
        assert capsys.readouterr().out.strip() == "x1 x2 ]] y3 y4"

    def test_assignment_control_unchanged(self, shell, capsys):
        # Command-prefix assignment suppression must still work after the
        # region logic (zone reopens after ]]).
        rc = shell.run_command('[[ x == x ]] && v={1,2}; echo "$v"')
        assert rc == 0
        assert capsys.readouterr().out.strip() == "{1,2}"

    def test_token_stream_keeps_interval_word_intact(self):
        # Token-level pin: {1,3} must NOT split ^[0-9]{1,3}$ into two words.
        from psh.lexer import tokenize
        from psh.lexer.token_types import TokenType
        tokens = tokenize('[[ 192 =~ ^[0-9]{1,3}$ ]]')
        types_values = [(t.type, t.value) for t in tokens
                        if t.type != TokenType.EOF]
        assert types_values == [
            (TokenType.DOUBLE_LBRACKET, '[['),
            (TokenType.WORD, '192'),
            (TokenType.REGEX_MATCH, '=~'),
            (TokenType.WORD, '^[0-9]{1,3}$'),
            (TokenType.DOUBLE_RBRACKET, ']]'),
        ]

    def test_token_stream_keeps_brace_word_after_region(self):
        # Brace expansion moved to the Word stage (v0.678): tokenization never
        # expands braces, so `a{1,2}` stays ONE WORD in the token stream both
        # inside and after a [[ ]] region. That the group DOES expand once the
        # region has closed is verified behaviorally by
        # test_expansion_still_works_outside_on_same_line.
        from psh.lexer import tokenize
        from psh.lexer.token_types import TokenType
        tokens = tokenize('[[ x == a{1,2} ]]; echo a{1,2}')
        words = [t.value for t in tokens if t.type == TokenType.WORD]
        assert words == ['x', 'a{1,2}', 'echo', 'a{1,2}']

    def test_unbalanced_double_lbracket_no_crash(self, shell, capsys):
        # Error input: parse error downstream, but no internal crash and
        # no bogus expansion-driven message.
        rc = shell.run_command('[[ a == a{1,2}')
        assert rc != 0

    def test_combinator_parser_regex_interval(self):
        # The fix is at the shared token level; prove the combinator parser
        # benefits too (subprocess: --parser is a startup flag).
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '--parser', 'combinator', '-c',
             '[[ 192 =~ ^[0-9]{1,3}$ ]] && echo ok'],
            capture_output=True, text=True)
        assert result.returncode == 0
        assert result.stdout.strip() == "ok"

    def test_combinator_parser_pattern_braces_literal(self):
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '--parser', 'combinator', '-c',
             '[[ ab == a{b,c} ]]; echo rc=$?'],
            capture_output=True, text=True)
        assert result.returncode == 0
        assert result.stdout.strip() == "rc=1"
