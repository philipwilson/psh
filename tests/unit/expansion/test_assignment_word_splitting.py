"""Assignment-shaped argument expansion: splitting, globbing, tilde.

Pins bash 5.2 semantics (every case in this file was probe-verified
against bash 5.2.26):

- Ordinary command arguments that merely LOOK like assignments
  (``printf '%s' foo=$x``) ARE word-split and globbed like any other
  argument.
- Declaration builtins (alias, declare, typeset, export, local,
  readonly) give their assignment-shaped arguments declaration
  semantics: the value is NOT word-split and NOT pathname-expanded.
- Recognition is syntactic: quoting any part of the command word
  (``"export"``, ``\\export``) or of the NAME= prefix
  (``declare "foo"=$x``), naming the builtin through a variable
  (``$d foo=$x``), or prefixing with command/builtin all lose
  declaration semantics in bash 5.2 — the argument splits.
- Words shaped like valid assignments (NAME= / NAME+=) get tilde
  expansion after the first ``=`` and after each ``:`` — in ordinary
  argument position too, not just for declaration builtins.
"""


class TestOrdinaryArgumentsSplit:
    """Assignment-looking args of ordinary commands word-split (bash)."""

    def test_printf_assignment_arg_splits(self, captured_shell):
        captured_shell.run_command('x="a b"; printf "<%s>" foo=$x')
        assert captured_shell.get_stdout() == '<foo=a><b>'

    def test_ifs_colon_splits_ordinary_arg(self, captured_shell):
        captured_shell.run_command('IFS=:; x="a:b"; printf "<%s>" foo=$x')
        assert captured_shell.get_stdout() == '<foo=a><b>'

    def test_dollar_at_in_assignment_arg_splits(self, captured_shell):
        captured_shell.run_command('set -- a "b c"; printf "<%s>" foo=$@')
        assert captured_shell.get_stdout() == '<foo=a><b><c>'

    def test_quoted_assignment_arg_never_splits(self, captured_shell):
        captured_shell.run_command('x="a b"; printf "<%s>" "foo=$x"')
        assert captured_shell.get_stdout() == '<foo=a b>'

    def test_quoted_value_does_not_split(self, captured_shell):
        captured_shell.run_command('x="a b"; printf "<%s>" foo="$x"')
        assert captured_shell.get_stdout() == '<foo=a b>'

    def test_empty_value_yields_single_field(self, captured_shell):
        captured_shell.run_command('e=""; printf "<%s>" foo=$e')
        assert captured_shell.get_stdout() == '<foo=>'

    def test_unset_value_yields_single_field(self, captured_shell):
        captured_shell.run_command('printf "<%s>" foo=$__unset_var__')
        assert captured_shell.get_stdout() == '<foo=>'

    def test_leading_equals_is_not_assignment(self, captured_shell):
        captured_shell.run_command('x="a b"; printf "<%s>" =$x')
        assert captured_shell.get_stdout() == '<=a><b>'

    def test_for_loop_item_assignment_shape_splits(self, captured_shell):
        # for/select items are NOT declaration arguments either
        captured_shell.run_command(
            'x="a b"; for i in foo=$x; do printf "<%s>" "$i"; done')
        assert captured_shell.get_stdout() == '<foo=a><b>'


class TestDeclarationBuiltinsDoNotSplit:
    """declare/typeset/export/local/readonly/alias keep values whole."""

    def test_declare_value_not_split(self, captured_shell):
        captured_shell.run_command('x="a b"; declare foo=$x; printf "<%s>" "$foo"')
        assert captured_shell.get_stdout() == '<a b>'

    def test_typeset_value_not_split(self, captured_shell):
        captured_shell.run_command('x="a b"; typeset foo=$x; printf "<%s>" "$foo"')
        assert captured_shell.get_stdout() == '<a b>'

    def test_export_value_not_split(self, captured_shell):
        captured_shell.run_command('x="a b"; export foo=$x; printf "<%s>" "$foo"')
        assert captured_shell.get_stdout() == '<a b>'

    def test_readonly_value_not_split(self, captured_shell):
        captured_shell.run_command('x="a b"; readonly foo=$x; printf "<%s>" "$foo"')
        assert captured_shell.get_stdout() == '<a b>'

    def test_local_value_not_split(self, captured_shell):
        captured_shell.run_command(
            'x="a b"; f() { local foo=$x; printf "<%s>" "$foo"; }; f')
        assert captured_shell.get_stdout() == '<a b>'

    def test_alias_value_not_split(self, captured_shell):
        captured_shell.run_command('x="ls -l"; alias a=$x; alias a')
        assert "ls -l" in captured_shell.get_stdout()

    def test_declare_ifs_colon_not_split(self, captured_shell):
        captured_shell.run_command(
            'IFS=:; x="a:b"; declare foo=$x; printf "<%s>" "$foo"')
        assert captured_shell.get_stdout() == '<a:b>'

    def test_declare_multiple_assignment_args(self, captured_shell):
        captured_shell.run_command(
            'x="1 2"; declare a=$x b=$x; printf "<%s><%s>" "$a" "$b"')
        assert captured_shell.get_stdout() == '<1 2><1 2>'

    def test_export_append_value_not_split(self, captured_shell):
        captured_shell.run_command('x="a b"; export foo+=$x; printf "<%s>" "$foo"')
        assert captured_shell.get_stdout() == '<a b>'

    def test_declare_array_initializer_still_works(self, captured_shell):
        captured_shell.run_command('declare -A h=([k]=v); printf "<%s>" "${h[k]}"')
        assert captured_shell.get_stdout() == '<v>'

    def test_declare_non_assignment_arg_still_splits(self, captured_shell):
        # Only assignment-SHAPED words get declaration semantics:
        # `declare $x` with x="foo=a b" declares foo=a and b (bash).
        captured_shell.run_command(
            'x="foo=a b"; declare $x; printf "<%s>" "$foo"')
        assert captured_shell.get_stdout() == '<a>'


class TestDeclarationRecognitionIsSyntactic:
    """Quoting/indirection of the command word loses declaration semantics."""

    def test_command_export_splits(self, captured_shell):
        captured_shell.run_command(
            'x="a b"; command export foo=$x; printf "<%s>" "$foo"')
        assert captured_shell.get_stdout() == '<a>'

    def test_builtin_export_splits(self, captured_shell):
        captured_shell.run_command(
            'x="a b"; builtin export foo=$x; printf "<%s>" "$foo"')
        assert captured_shell.get_stdout() == '<a>'

    def test_backslash_export_splits(self, captured_shell):
        captured_shell.run_command(
            'x="a b"; \\export foo=$x; printf "<%s>" "$foo"')
        assert captured_shell.get_stdout() == '<a>'

    def test_quoted_export_splits(self, captured_shell):
        captured_shell.run_command(
            'x="a b"; "export" foo=$x; printf "<%s>" "$foo"')
        assert captured_shell.get_stdout() == '<a>'

    def test_builtin_named_by_variable_splits(self, captured_shell):
        captured_shell.run_command(
            'x="a b"; d=declare; $d foo=$x; printf "<%s>" "$foo"')
        assert captured_shell.get_stdout() == '<a>'

    def test_quoted_name_in_assignment_splits(self, captured_shell):
        # bash: declare "foo"=$x word-splits (quoted name breaks the
        # assignment shape)
        captured_shell.run_command(
            'x="a b"; declare "foo"=$x; printf "<%s>" "$foo"')
        assert captured_shell.get_stdout() == '<a>'

    def test_quoted_name_equals_in_assignment_splits(self, captured_shell):
        captured_shell.run_command(
            'x="a b"; declare "foo="$x; printf "<%s>" "$foo"')
        assert captured_shell.get_stdout() == '<a>'

    def test_invalid_identifier_splits(self, captured_shell):
        # bash: `declare foo-bar=$x` splits first (error names `foo-bar=a')
        captured_shell.run_command('x="a b"; declare foo-bar=$x')
        assert "`foo-bar=a'" in captured_shell.get_stderr()

    def test_eval_export_keeps_declaration_semantics(self):
        # eval re-parses, so export IS the command word there (bash).
        # (subprocess: eval's nested execution bypasses captured_shell)
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'x="a b"; eval export foo=\\$x; printf "<%s>" "$foo"'],
            capture_output=True, text=True)
        assert result.stdout == '<a b>'


class TestDeclarationGlobSuppression:
    """Declaration assignment values are not pathname-expanded (bash)."""

    def test_declare_literal_glob_value_stays(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('touch "foo=match"')
        shell.run_command('declare foo=*; printf "<%s>" "$foo" > out.txt')
        with open('out.txt') as f:
            assert f.read() == '<*>'

    def test_declare_expanded_glob_value_stays(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('touch "foo=match"')
        shell.run_command('x="*"; declare foo=$x; printf "<%s>" "$foo" > out.txt')
        with open('out.txt') as f:
            assert f.read() == '<*>'

    def test_ordinary_assignment_shaped_arg_still_globs(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('touch "foo=match"')
        shell.run_command('printf "<%s>" foo=* > out.txt')
        with open('out.txt') as f:
            assert f.read() == '<foo=match>'


class TestAssignmentArgumentTilde:
    """Tilde after '='/':' in assignment-shaped words (bash, non-POSIX mode)."""

    def test_ordinary_arg_tilde_after_equals(self, captured_shell):
        captured_shell.run_command('HOME=/h; printf "<%s>" P=~/x')
        assert captured_shell.get_stdout() == '<P=/h/x>'

    def test_ordinary_arg_tilde_after_colons(self, captured_shell):
        captured_shell.run_command('HOME=/h; printf "<%s>" a=~:~/y')
        assert captured_shell.get_stdout() == '<a=/h:/h/y>'

    def test_append_form_tilde(self, captured_shell):
        captured_shell.run_command('HOME=/h; printf "<%s>" x+=~/y')
        assert captured_shell.get_stdout() == '<x+=/h/y>'

    def test_invalid_name_no_tilde(self, captured_shell):
        captured_shell.run_command('HOME=/h; printf "<%s>" foo-bar=~/x')
        assert captured_shell.get_stdout() == '<foo-bar=~/x>'

    def test_numeric_name_no_tilde(self, captured_shell):
        captured_shell.run_command('HOME=/h; printf "<%s>" 1a=~/x')
        assert captured_shell.get_stdout() == '<1a=~/x>'

    def test_leading_equals_no_tilde(self, captured_shell):
        captured_shell.run_command('HOME=/h; printf "<%s>" =~/x')
        assert captured_shell.get_stdout() == '<=~/x>'

    def test_tilde_not_after_separator_stays(self, captured_shell):
        captured_shell.run_command('HOME=/h; printf "<%s>" x=a~/y')
        assert captured_shell.get_stdout() == '<x=a~/y>'

    def test_export_tilde_value(self, captured_shell):
        captured_shell.run_command('HOME=/h; export P=~/x; printf "<%s>" "$P"')
        assert captured_shell.get_stdout() == '</h/x>'

    def test_declare_tilde_after_expansion_colon(self, captured_shell):
        captured_shell.run_command(
            'HOME=/h; x=a; declare P=$x:~/y; printf "<%s>" "$P"')
        assert captured_shell.get_stdout() == '<a:/h/y>'

    def test_tilde_after_expansion_no_separator_stays(self, captured_shell):
        captured_shell.run_command('HOME=/h; x=a; printf "<%s>" P=$x~')
        assert captured_shell.get_stdout() == '<P=a~>'

    def test_tilde_prefix_into_quoted_text_stays(self, captured_shell):
        # bash: P=~"x" — quoted char inside the tilde prefix → no expansion
        captured_shell.run_command('HOME=/h; printf "<%s>" P=~"x"')
        assert captured_shell.get_stdout() == '<P=~x>'

    def test_tilde_terminated_by_slash_before_quote_expands(self, captured_shell):
        captured_shell.run_command('HOME=/h; export P=~/"x"; printf "<%s>" "$P"')
        assert captured_shell.get_stdout() == '</h/x>'

    def test_escaped_tilde_stays(self, captured_shell):
        captured_shell.run_command('HOME=/h; printf "<%s>" P=\\~/x')
        assert captured_shell.get_stdout() == '<P=~/x>'

    def test_unknown_user_tilde_stays(self, captured_shell):
        captured_shell.run_command('printf "<%s>" P=~nosuchuser55/x')
        assert captured_shell.get_stdout() == '<P=~nosuchuser55/x>'

    def test_pure_assignment_tilde_after_colon(self, captured_shell):
        captured_shell.run_command('HOME=/h; P=a:~:b; printf "<%s>" "$P"')
        assert captured_shell.get_stdout() == '<a:/h:b>'

    def test_pure_assignment_tilde_into_quoted_stays(self, captured_shell):
        captured_shell.run_command('HOME=/h; P=~"x"; printf "<%s>" "$P"')
        assert captured_shell.get_stdout() == '<~x>'

    def test_array_initializer_element_no_assignment_tilde(self, captured_shell):
        # bash does NOT tilde-expand a=(P=~/x) elements
        captured_shell.run_command('HOME=/h; a=(P=~/x); printf "<%s>" "${a[0]}"')
        assert captured_shell.get_stdout() == '<P=~/x>'


class TestDeclareAppendArguments:
    """NAME+=value arguments of declaration builtins (bash semantics)."""

    def test_declare_append_scalar(self, captured_shell):
        captured_shell.run_command(
            'declare foo=x; declare foo+=y; printf "<%s>" "$foo"')
        assert captured_shell.get_stdout() == '<xy>'

    def test_declare_append_unsplit_value(self, captured_shell):
        captured_shell.run_command(
            'x="a b"; declare foo+=$x; printf "<%s>" "$foo"')
        assert captured_shell.get_stdout() == '<a b>'

    def test_typeset_append(self, captured_shell):
        captured_shell.run_command(
            'typeset foo=x; typeset foo+=y; printf "<%s>" "$foo"')
        assert captured_shell.get_stdout() == '<xy>'

    def test_readonly_append(self, captured_shell):
        captured_shell.run_command('readonly foo+=x; printf "<%s>" "$foo"')
        assert captured_shell.get_stdout() == '<x>'

    def test_local_append(self, captured_shell):
        captured_shell.run_command(
            'f() { local foo=x; local foo+=y; printf "<%s>" "$foo"; }; f')
        assert captured_shell.get_stdout() == '<xy>'

    def test_declare_integer_append_is_arithmetic(self, captured_shell):
        captured_shell.run_command(
            'declare -i n=2; declare n+=3; printf "<%s>" "$n"')
        assert captured_shell.get_stdout() == '<5>'

    def test_plain_append_to_array_updates_element_zero(self, captured_shell):
        # bash: a=(1 2); a+=x → a[0]="1x", array preserved
        captured_shell.run_command('a=(1 2); a+=x; printf "<%s>" "${a[@]}"')
        assert captured_shell.get_stdout() == '<1x><2>'
