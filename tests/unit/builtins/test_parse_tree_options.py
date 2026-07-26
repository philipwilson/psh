"""The `parse-tree` debug builtin tokenizes with the live shell options.

Regression guard: it used to tokenize without shell options, so its displayed
AST ignored extglob/posix — `shopt -s extglob; parse-tree '@(a|b)'` printed a
parse error instead of the extglob AST the executor would build.
"""


def test_parse_tree_respects_extglob(captured_shell):
    captured_shell.run_command("shopt -s extglob")
    rc = captured_shell.run_command("parse-tree '@(a|b)'")
    assert rc == 0
    out = captured_shell.get_stdout()
    assert "Program" in out
    # No tokenizer parse error leaked to stderr.
    assert "parse error" not in captured_shell.get_stderr()


def test_parse_tree_respects_extglob_in_nested_substitution(captured_shell):
    # remediation R3-6b: the nested $() body must re-lex with the SAME extglob
    # budget as the outer command. At base, parse-tree threaded shell options
    # into tokenize() but built the parser WITHOUT lexer_options, so
    # `$(echo @(a|b))` re-lexed WITHOUT extglob and rejected (the HIGH-5 defect
    # class inside this builtin). Routing through the one entry threads it. Red
    # at base: base printed a parse error near `(`.
    captured_shell.run_command("shopt -s extglob")
    rc = captured_shell.run_command("parse-tree 'echo $(echo @(a|b))'")
    assert rc == 0
    assert "Program" in captured_shell.get_stdout()
    assert "parse error" not in captured_shell.get_stderr()


def test_parse_tree_extglob_off_rejects(captured_shell):
    # With extglob OFF (default), `@(a|b)` is a syntax error — same as the
    # executor. This is the discriminator proving the option is actually read.
    rc = captured_shell.run_command("parse-tree '@(a|b)'")
    assert rc != 0
    assert "parse error" in captured_shell.get_stderr()


def test_parse_tree_plain_command_unaffected(captured_shell):
    rc = captured_shell.run_command("parse-tree 'echo hi'")
    assert rc == 0
    assert "Program" in captured_shell.get_stdout()
