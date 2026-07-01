"""`type <function>` prints the function body, like `command -V` (reappraisal
#13). psh previously stopped at "NAME is a function" (a literal TODO).

The body is checked for content + consistency with `command -V`. The text is
FormatterVisitor's canonical `name() {` style (R15 D3) — not bash's brace
placement, but it re-parses to the same function.
"""


def test_type_prints_function_body(captured_shell):
    captured_shell.run_command('myfn() { echo hello; }')
    captured_shell.clear_output()
    assert captured_shell.run_command('type myfn') == 0
    out = captured_shell.get_stdout()
    assert 'myfn is a function' in out
    assert 'echo hello' in out          # the body, not just the header
    assert 'myfn() {' in out


def test_type_matches_command_dash_v(captured_shell):
    captured_shell.run_command('myfn() { echo hello; }')
    captured_shell.clear_output()
    captured_shell.run_command('type myfn')
    type_out = captured_shell.get_stdout()
    captured_shell.clear_output()
    captured_shell.run_command('command -V myfn')
    cmd_out = captured_shell.get_stdout()
    assert type_out == cmd_out


def test_type_t_function_unchanged(captured_shell):
    captured_shell.run_command('myfn() { :; }')
    captured_shell.clear_output()
    assert captured_shell.run_command('type -t myfn') == 0
    assert captured_shell.get_stdout() == 'function\n'
