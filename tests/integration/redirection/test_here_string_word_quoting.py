r"""Regression pins for the here-string (<<<) target Word (appraisal #15, G1).

The here-string target used to be a flattened string plus one quote char,
re-expanded with `expand_string_variables`, which lost per-part quote
boundaries: `foo$v"dq"` flattened to `foo$vdq` and expanded a variable
named `vdq`; `a\ b` kept its backslash. It now carries a Word
(Redirect.target_word) expanded like an assignment value (all expansions,
value-tilde, quote removal, NO word splitting, NO globbing). Expected values
verified against bash 5.2. Uses external `cat` + file redirection so output
is captured at the fd level.
"""

import os


def _read(shell, name):
    with open(os.path.join(shell.state.variables['PWD'], name)) as f:
        return f.read()


class TestHereStringWordQuoting:
    def test_composite_unquoted_var_then_dquoted(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('v="a b"; cat <<< foo$v"dq" > out.txt')
        assert _read(shell, "out.txt") == "fooa bdq\n"

    def test_composite_var_single_double(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command("v=\"a b\"; cat <<< foo$v'lit'\"dq$v\" > out.txt")
        assert _read(shell, "out.txt") == "fooa blitdqa b\n"

    def test_backslash_space_removed(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command("cat <<< a\\ b > out.txt")
        assert _read(shell, "out.txt") == "a b\n"

    def test_single_quoted_literal(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command("v=hi; cat <<< '$v' > out.txt")
        assert _read(shell, "out.txt") == "$v\n"

    def test_double_quoted_expands(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('v=hi; cat <<< "$v" > out.txt')
        assert _read(shell, "out.txt") == "hi\n"

    def test_composite_quoted_var_quoted(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('v=X; cat <<< "pre"$v"post" > out.txt')
        assert _read(shell, "out.txt") == "preXpost\n"

    def test_var_with_spaces_not_split(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('v="a b"; cat <<< $v > out.txt')
        assert _read(shell, "out.txt") == "a b\n"

    def test_glob_not_expanded(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command("cat <<< '*' > out.txt")
        assert _read(shell, "out.txt") == "*\n"

    def test_tilde_expands_leading(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command("cat <<< ~ > out.txt")
        home = shell.state.get_variable('HOME')
        assert _read(shell, "out.txt") == f"{home}\n"

    def test_tilde_after_colon(self, isolated_shell_with_temp_dir):
        # here-string tilde is value-tilde (unlike a case subject): after ':' too.
        shell = isolated_shell_with_temp_dir
        shell.run_command("cat <<< a:~ > out.txt")
        home = shell.state.get_variable('HOME')
        assert _read(shell, "out.txt") == f"a:{home}\n"
