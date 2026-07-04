"""Value-operand quote/escape removal for ${x:-w} and friends (r17 H5).

Bash expands the value word of the default/alternate/assign/error
operators with full word semantics — embedded quotes group and strip,
backslash escapes any character, $'...' decodes, and quoted regions of
the operand resist later IFS splitting and globbing. The rules invert
inside double quotes: single quotes become LITERAL characters while
embedded double quotes still group (and toggle the escape rules).

Every expectation below is pinned to bash 5.2 (probe battery in
tmp/probes-r17t1-quoting/, 390/390 rows matching; the pins live on in
tests/behavioral/golden_cases.yaml).

Regression tests for reappraisal #17 finding H5: _expand_operand used to
strip only a quote pair wrapping the ENTIRE operand, leaking embedded
quotes into output, expanding $var inside single quotes, and STORING the
corrupted text for ${x:=...}.
"""


def out(shell, capsys, cmd, rc=0):
    assert shell.run_command(cmd) == rc
    return capsys.readouterr().out


class TestUnquotedContextQuoteRemoval:
    """Unquoted ${x:-...}: one level of quotes is removed anywhere."""

    def test_embedded_double_quotes_strip(self, shell, capsys):
        assert out(shell, capsys, 'echo ${x:-a"b"c}') == "abc\n"

    def test_embedded_single_quotes_strip(self, shell, capsys):
        assert out(shell, capsys, "echo ${x:-a'b'c}") == "abc\n"

    def test_mixed_quotes_strip(self, shell, capsys):
        assert out(shell, capsys, "echo ${x:-a\"b\"'c'd}") == "abcd\n"

    def test_single_quotes_suppress_expansion(self, shell, capsys):
        # The report's headline case: psh used to print a'mid'b.
        assert out(shell, capsys, "y=mid; echo ${x:-a'$y'b}") == "a$yb\n"

    def test_quoted_variable_with_suffix(self, shell, capsys):
        assert out(shell, capsys, 'y=V; echo ${x:-"$y"/bin}') == "V/bin\n"

    def test_backslash_escapes_space(self, shell, capsys):
        assert out(shell, capsys, r'echo ${x:-a\ b}') == "a b\n"

    def test_backslash_escapes_any_char(self, shell, capsys):
        assert out(shell, capsys, r'echo ${x:-a\nb}') == "anb\n"

    def test_backslash_escapes_dollar(self, shell, capsys):
        assert out(shell, capsys, r'y=mid; echo ${x:-a\$y}') == "a$y\n"

    def test_ansi_c_decodes(self, shell, capsys):
        assert out(shell, capsys, r"printf '<%s>\n' ${x:-$'a\tb'}") == "<a\tb>\n"

    def test_whole_quoted_defaults_still_work(self, shell, capsys):
        assert out(shell, capsys, 'echo ${x:-"default"}') == "default\n"
        assert out(shell, capsys, "echo ${x:-'default'}") == "default\n"

    def test_noncolon_forms_diverged_too(self, shell, capsys):
        # Round-2 addendum: ${x-...} and ${x+...} share the walker.
        assert out(shell, capsys, 'echo ${x-a"b"c}') == "abc\n"
        assert out(shell, capsys, "x=SET; echo ${x+a'b'c}") == "abc\n"

    def test_expansion_inside_embedded_dquotes(self, shell, capsys):
        assert out(shell, capsys, 'y=mid; echo ${x:-a"b$y"c}') == "abmidc\n"


class TestAssignStoresCleanValue:
    """${x:=w} must STORE the quote-removed value (was data loss)."""

    def test_assign_strips_embedded_quotes(self, shell, capsys):
        assert out(shell, capsys, 'echo ${x:="a"b}; echo $x') == "ab\nab\n"

    def test_assign_result_has_value_semantics(self, shell, capsys):
        # bash: the := RESULT is the variable's new value — it splits
        # even where the ${x:-...} word would not (probed).
        assert out(shell, capsys,
                   r"printf '<%s>' ${x:=a\ b}; echo; echo [$x]") \
            == "<a><b>\n[a b]\n"

    def test_dash_default_does_not_split_escaped(self, shell, capsys):
        # The contrast: :- keeps the operand's protection.
        assert out(shell, capsys, r"printf '<%s>' ${x:-a\ b}; echo") == "<a b>\n"


class TestOperandSplittingProtection:
    """Quoted operand regions never field-split; unquoted ones do."""

    def test_quoted_default_is_one_field(self, shell, capsys):
        assert out(shell, capsys, "printf '<%s>' ${x:-'a b'}; echo") == "<a b>\n"
        assert out(shell, capsys, 'printf "<%s>" ${x:-"a b"}; echo') == "<a b>\n"

    def test_unquoted_default_splits(self, shell, capsys):
        assert out(shell, capsys, "printf '<%s>' ${x:-a b}; echo") == "<a><b>\n"

    def test_mixed_halves_join(self, shell, capsys):
        assert out(shell, capsys, 'printf "<%s>" ${x:-"a "b}; echo') == "<a b>\n"

    def test_quoted_command_sub_protected(self, shell, capsys):
        assert out(shell, capsys,
                   'printf "<%s>" ${x:-"$(echo p q)"}; echo') == "<p q>\n"

    def test_unquoted_command_sub_splits(self, shell, capsys):
        assert out(shell, capsys,
                   "printf '<%s>' ${x:-$(echo p q)}; echo") == "<p><q>\n"

    def test_empty_quotes_yield_one_empty_field(self, shell, capsys):
        assert out(shell, capsys, "set -- ${x:-''}; echo $#") == "1\n"

    def test_empty_operand_yields_zero_fields(self, shell, capsys):
        assert out(shell, capsys, "set -- ${x:-}; echo $#") == "0\n"

    def test_custom_ifs_respects_quotes(self, shell, capsys):
        assert out(shell, capsys,
                   "IFS=,; printf '<%s>' ${x:-'a,b'}; echo") == "<a,b>\n"

    def test_nested_protection_propagates(self, shell, capsys):
        # bash: set -- ${x:-${z:-'a b'}} -> 1 field.
        assert out(shell, capsys,
                   "set -- ${x:-${z:-'a b'}}; echo $#") == "1\n"

    def test_ansi_c_result_protected_from_ifs(self, shell, capsys):
        # Tab is in default IFS; the decoded $'\t' must not split.
        assert out(shell, capsys,
                   r"set -- ${x:-$'a\tb'}; echo $#") == "1\n"


class TestOperandGlobProtection:
    def test_quoted_star_stays_literal(self, shell_with_temp_dir, capsys):
        shell = shell_with_temp_dir
        shell.run_command("touch g1.x g2.x")
        capsys.readouterr()
        assert out(shell, capsys, "printf '<%s>' ${x:-'*.x'}; echo") == "<*.x>\n"
        assert out(shell, capsys, r"printf '<%s>' ${x:-\*.x}; echo") == "<*.x>\n"

    def test_unquoted_star_globs(self, shell_with_temp_dir, capsys):
        shell = shell_with_temp_dir
        shell.run_command("touch g1.x g2.x")
        capsys.readouterr()
        assert out(shell, capsys,
                   "printf '<%s>' ${x:-*.x}; echo") == "<g1.x><g2.x>\n"


class TestDoubleQuoteContextInversion:
    """Inside "...": single quotes literal, double quotes still group."""

    def test_single_quotes_kept_literal(self, shell, capsys):
        assert out(shell, capsys, 'echo "${x:-\'literal\'}"') == "'literal'\n"

    def test_embedded_dquotes_still_strip(self, shell, capsys):
        assert out(shell, capsys, 'echo "${x:-a"b"c}"') == "abc\n"

    def test_mixed_inside_dquotes(self, shell, capsys):
        assert out(shell, capsys, 'echo "${x:-a"b"\'c\'d}"') == "ab'c'd\n"

    def test_assign_stores_context_dependent_value(self, shell, capsys):
        assert out(shell, capsys,
                   'echo "${x:=\'a b\'}"; echo "[$x]"') == "'a b'\n['a b']\n"

    def test_dquote_escape_rules_apply(self, shell, capsys):
        assert out(shell, capsys, r'echo "${x:-a\ b}"') == "a\\ b\n"
        assert out(shell, capsys, r'echo "${x:-a\"b}"') == 'a"b\n'

    def test_nested_expansion_inherits_context(self, shell, capsys):
        assert out(shell, capsys, 'echo "${x:-${z:-\'q\'}}"') == "'q'\n"

    def test_dquote_segment_in_unquoted_operand(self, shell, capsys):
        # The inner "..." region is a dquote context for ITS nested operand.
        assert out(shell, capsys, "echo ${x:-\"${z:-'q'}\"}") == "'q'\n"

    def test_ansi_c_decodes_in_dquoted_word(self, shell, capsys):
        assert out(shell, capsys, 'echo "${x:-$\'a\\tb\'}"') == "a\tb\n"

    def test_name_scan_crosses_embedded_quotes(self, shell, capsys):
        # bash 3.2-5.2: the $name scan runs across embedded quote marks,
        # so "${x:-a"$y"c}" reads the variable yc (probed).
        assert out(shell, capsys,
                   'y=mid; yc=YC; echo "${x:-a"$y"c}"') == "aYC\n"

    def test_name_scan_unset_crossed_name_vanishes(self, shell, capsys):
        # The crossed name yc is unset here: the whole $y"c reads as the
        # empty ${yc} (bash prints just "ab").
        assert out(shell, capsys, 'y=mid; echo "${x:-a"b$y"c}"') == "ab\n"

    def test_escape_rules_toggle_inside_embedded_quotes(self, shell, capsys):
        # Outside embedded quotes: dquote rules keep \q. Inside them the
        # rules invert: backslash escapes anything (probed).
        assert out(shell, capsys, r'echo "${x:-a\qb}"') == "a\\qb\n"
        assert out(shell, capsys, r'echo "${x:-a"\q"b}"') == "aqb\n"


class TestErrorWordRendering:
    """${x:?word} renders with unquoted-word rules in every context."""

    def test_message_strips_quotes(self, shell, capsys):
        assert shell.run_command('echo ${x:?a"b"c}') != 0
        assert "x: abc" in capsys.readouterr().err

    def test_message_protects_single_quoted_dollar(self, shell, capsys):
        assert shell.run_command("y=mid; echo ${x:?a'$y'b}") != 0
        assert "x: a$yb" in capsys.readouterr().err

    def test_message_unquoted_rules_even_in_dquotes(self, shell, capsys):
        assert shell.run_command('echo "${x:?\'whole\'}"') != 0
        assert "x: whole" in capsys.readouterr().err

    def test_noncolon_message(self, shell, capsys):
        assert shell.run_command(r'echo ${x?a\ b}') != 0
        assert "x: a b" in capsys.readouterr().err


class TestStringContexts:
    """Heredocs and $(( )) are dquote-like; here-strings are word-like.

    The heredoc/here-string rows run psh in a subprocess: they feed an
    external ``cat``, whose fd-level output pytest capsys cannot see.
    """

    @staticmethod
    def _run(script):
        import subprocess
        import sys
        return subprocess.run([sys.executable, '-m', 'psh', '-c', script],
                              capture_output=True, text=True)

    def test_heredoc_keeps_single_quotes(self):
        assert self._run("cat <<EOF\n${x:-'q'}\nEOF").stdout == "'q'\n"

    def test_heredoc_strips_double_quotes(self):
        assert self._run('cat <<EOF\n${x:-a"b"c}\nEOF').stdout == "abc\n"

    def test_heredoc_ansi_c_stays_literal(self):
        # bash never ANSI-C-decodes heredoc text (unlike lexed words).
        assert self._run("cat <<EOF\n${x:-$'a\\tb'}\nEOF").stdout \
            == "$'a\\tb'\n"

    def test_herestring_uses_word_rules(self):
        assert self._run('cat <<< ${x:-a"b"c}').stdout == "abc\n"

    def test_arithmetic_deletes_double_quotes(self, shell, capsys):
        assert out(shell, capsys, 'echo $(( ${u:-"5"} + 1 ))') == "6\n"

    def test_arithmetic_keeps_single_quotes_and_errors(self, shell, capsys):
        # bash: $(( ${u:-'5'} )) keeps the quotes -> arithmetic error.
        assert shell.run_command("echo $(( ${u:-'5'} + 1 ))") != 0
        assert capsys.readouterr().err != ""

    def test_test_command_quoted_rhs_pattern(self, shell, capsys):
        # [[ "q" == "${u:-'q'}" ]] : the pattern keeps 'q' (dq context).
        assert out(shell, capsys,
                   '[[ "q" == "${u:-\'q\'}" ]] && echo yes || echo no') == "no\n"
        assert out(shell, capsys,
                   "[[ q == ${u:-'q'} ]] && echo yes || echo no") == "yes\n"


class TestTildeInOperands:
    def test_leading_tilde_expands(self, shell, capsys):
        home = shell.state.get_variable('HOME')
        assert out(shell, capsys, 'echo ${x:-~}') == f"{home}\n"
        assert out(shell, capsys, 'echo ${x:-~/bin}') == f"{home}/bin\n"

    def test_no_tilde_after_colon_in_operand(self, shell, capsys):
        # Value operands only expand a LEADING tilde (no assignment-value
        # after-':' rule) — probed.
        assert out(shell, capsys, 'echo ${x:-a:~}') == "a:~\n"

    def test_no_tilde_in_dquote_context(self, shell, capsys):
        assert out(shell, capsys, 'echo "${x:-~}"') == "~\n"

    def test_no_tilde_from_expansion_result(self, shell, capsys):
        assert out(shell, capsys, "y='~'; echo ${x:-$y}") == "~\n"

    def test_quoted_tilde_literal(self, shell, capsys):
        assert out(shell, capsys, "echo ${x:-'~'}") == "~\n"


class TestArrayAndPositionalViews:
    """${a[@]:-w} and ${@:-w} share the operand walker."""

    def test_array_view_default_strips_quotes(self, shell, capsys):
        assert out(shell, capsys, "a=(); echo ${a[@]:-'q'}") == "q\n"

    def test_array_view_quoted_default_one_field(self, shell, capsys):
        assert out(shell, capsys,
                   "a=(); set -- ${a[@]:-'a b'}; echo $#") == "1\n"

    def test_array_view_unquoted_default_splits(self, shell, capsys):
        assert out(shell, capsys,
                   "a=(); set -- ${a[@]:-a b}; echo $#") == "2\n"

    def test_positional_view_dquote_context(self, shell, capsys):
        assert out(shell, capsys, 'echo "${@:-\'q\'}"') == "'q'\n"
