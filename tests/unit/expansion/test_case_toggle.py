"""Unit tests for the ${x~}/${x~~} case-toggle parameter-expansion operators.

`~` toggles the case of the first character; `~~` toggles every character.
An optional glob pattern gates which characters are considered (siblings of
the ^/^^ upper and ,/,, lower case-mods). Pinned against bash 5.2.
"""


class TestScalarToggle:
    """${x~} first char, ${x~~} all chars."""

    def _run(self, captured_shell, cmd):
        captured_shell.clear_output()
        captured_shell.run_command(cmd)
        return captured_shell.get_stdout().rstrip("\n")

    def test_toggle_first_lower_to_upper(self, captured_shell):
        assert self._run(captured_shell, 'x=hello; echo "${x~}"') == "Hello"

    def test_toggle_first_upper_to_lower(self, captured_shell):
        assert self._run(captured_shell, 'x=HELLO; echo "${x~}"') == "hELLO"

    def test_toggle_all(self, captured_shell):
        assert self._run(captured_shell, 'x=HeLLo123; echo "${x~~}"') == "hEllO123"

    def test_toggle_all_lower_to_upper(self, captured_shell):
        assert self._run(captured_shell, 'x=hello; echo "${x~~}"') == "HELLO"

    def test_toggle_first_nonletter_unchanged(self, captured_shell):
        # First char is a digit: toggling it is a no-op, rest untouched.
        assert self._run(captured_shell, 'x=123abc; echo "${x~}"') == "123abc"

    def test_toggle_empty(self, captured_shell):
        assert self._run(captured_shell, 'x=; echo "${x~}"') == ""

    def test_toggle_all_empty(self, captured_shell):
        assert self._run(captured_shell, 'x=; echo "${x~~}"') == ""

    def test_toggle_unset(self, captured_shell):
        assert self._run(captured_shell, 'unset u; echo "[${u~~}]"') == "[]"


class TestToggleWithPattern:
    """A pattern gates which characters are considered for toggling."""

    def _run(self, captured_shell, cmd):
        captured_shell.clear_output()
        captured_shell.run_command(cmd)
        return captured_shell.get_stdout().rstrip("\n")

    def test_toggle_first_matching_pattern(self, captured_shell):
        assert self._run(captured_shell, 'x=hello; echo "${x~h}"') == "Hello"

    def test_toggle_first_nonmatching_pattern_noop(self, captured_shell):
        # First char 'h' does not match 'l' → unchanged.
        assert self._run(captured_shell, 'x=hello; echo "${x~l}"') == "hello"

    def test_toggle_first_char_class(self, captured_shell):
        assert self._run(captured_shell, 'x=hello; echo "${x~[hx]}"') == "Hello"

    def test_toggle_all_matching_class(self, captured_shell):
        assert self._run(captured_shell, 'x=hello; echo "${x~~l}"') == "heLLo"

    def test_toggle_all_range(self, captured_shell):
        assert self._run(captured_shell, 'x=abcABC; echo "${x~~[a-c]}"') == "ABCABC"

    def test_toggle_all_range_upper(self, captured_shell):
        assert self._run(captured_shell, 'x=abcABC; echo "${x~~[A-C]}"') == "abcabc"

    def test_toggle_all_wildcard(self, captured_shell):
        # ? matches any single char → toggle everything.
        assert self._run(captured_shell, 'x=Hello; echo "${x~~?}"') == "hELLO"


class TestArrayToggle:
    """Case-toggle applies per element for ${arr[@]~~} / ${arr[*]~~}."""

    def test_array_at_toggle_first(self, shell):
        shell.run_command('a=(foo BAR bAz)')
        shell.run_command('r="${a[@]~}"')
        assert shell.state.get_variable('r') == "Foo bAR BAz"

    def test_array_at_toggle_all(self, shell):
        shell.run_command('a=(foo BAR bAz)')
        shell.run_command('r="${a[@]~~}"')
        assert shell.state.get_variable('r') == "FOO bar BaZ"

    def test_array_star_toggle_all(self, shell):
        shell.run_command('a=(foo BAR bAz)')
        shell.run_command('r="${a[*]~~}"')
        assert shell.state.get_variable('r') == "FOO bar BaZ"

    def test_array_toggle_all_pattern(self, shell):
        shell.run_command('a=(abc ABC)')
        shell.run_command('r="${a[@]~~[a-c]}"')
        assert shell.state.get_variable('r') == "ABC ABC"

    def test_array_element_toggle_first(self, shell):
        shell.run_command('a=(hello WORLD)')
        shell.run_command('r="${a[0]~}"')
        assert shell.state.get_variable('r') == "Hello"

    def test_array_element_toggle_all(self, shell):
        shell.run_command('a=(hello WORLD)')
        shell.run_command('r="${a[1]~~}"')
        assert shell.state.get_variable('r') == "world"

    def test_assoc_element_toggle_all(self, shell):
        shell.run_command('declare -A m=([k]=Val)')
        shell.run_command('r="${m[k]~~}"')
        assert shell.state.get_variable('r') == "vAL"
