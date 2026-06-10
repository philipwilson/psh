"""BASH_REMATCH population from [[ str =~ regex ]]."""



def _out(captured_shell, cmd):
    captured_shell.clear_output()
    assert captured_shell.run_command(cmd) == 0
    return captured_shell.get_stdout()


class TestBashRematch:
    def test_full_match_group0(self, captured_shell):
        assert _out(captured_shell, '[[ foobar =~ o+ ]]; echo "${BASH_REMATCH[0]}"') == "oo\n"

    def test_capture_groups(self, captured_shell):
        out = _out(captured_shell,
                   '[[ abc123 =~ ([a-z]+)([0-9]+) ]]; echo "${BASH_REMATCH[1]} ${BASH_REMATCH[2]}"')
        assert out == "abc 123\n"

    def test_group_count(self, captured_shell):
        assert _out(captured_shell, '[[ a1b2 =~ ([a-z])([0-9]) ]]; echo "${#BASH_REMATCH[@]}"') == "3\n"

    def test_all_elements(self, captured_shell):
        assert _out(captured_shell, '[[ x9 =~ (.)(.) ]]; echo "${BASH_REMATCH[@]}"') == "x9 x 9\n"

    def test_alternation(self, captured_shell):
        assert _out(captured_shell, '[[ dog =~ ^(cat|dog)$ ]]; echo "${BASH_REMATCH[1]}"') == "dog\n"

    def test_variable_regex(self, captured_shell):
        out = _out(captured_shell, 're="([0-9]+)"; [[ x42y =~ $re ]]; echo "${BASH_REMATCH[1]}"')
        assert out == "42\n"

    def test_optional_group_empty(self, captured_shell):
        assert _out(captured_shell, '[[ ab =~ a(x)?b ]]; echo "[${BASH_REMATCH[1]}]"') == "[]\n"

    def test_no_match_clears(self, captured_shell):
        out = _out(captured_shell,
                   '[[ abc =~ ([0-9]+) ]]; echo "n=${#BASH_REMATCH[@]} v=[${BASH_REMATCH[0]}]"')
        assert out == "n=0 v=[]\n"

    def test_match_after_nomatch_updates(self, captured_shell):
        out = _out(captured_shell,
                   '[[ zzz =~ ([0-9]) ]]; [[ q7 =~ ([0-9]) ]]; echo "${BASH_REMATCH[1]}"')
        assert out == "7\n"
