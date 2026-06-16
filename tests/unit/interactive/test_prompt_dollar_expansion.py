"""PS1/PS2 undergo $-expansion after escape decoding, with escape output
protected (reappraisal #13 MED). Tests the PromptManager directly, including
the `\\[`/`\\]` readline markers that bash's `${var@P}` omits.
"""

from psh.shell import Shell


def _pm(shell):
    return shell.interactive_manager.prompt_manager


def test_command_substitution_in_prompt():
    sh = Shell(norc=True)
    assert _pm(sh).expand_prompt('[$(echo HI)]$ ') == '[HI]$ '


def test_variable_expansion_in_prompt():
    sh = Shell(norc=True)
    sh.state.set_variable('FOO', 'bar')
    assert _pm(sh).expand_prompt('<$FOO>') == '<bar>'


def test_backslash_dollar_not_expanded():
    # \$ decodes to a literal $; the following (echo X) must stay literal.
    sh = Shell(norc=True)
    assert _pm(sh).expand_prompt('\\$(echo X)') == '$(echo X)'


def test_escape_value_not_reinterpreted():
    # A variable's value containing a prompt-escape is NOT re-decoded.
    sh = Shell(norc=True)
    sh.state.set_variable('V', '\\w')
    assert _pm(sh).expand_prompt('$V') == '\\w'


def test_nonprinting_markers_preserved():
    # \[ and \] become readline non-printing markers (\001/\002); the embedded
    # $(...) still expands.
    sh = Shell(norc=True)
    out = _pm(sh).expand_prompt('\\[\\e[0m\\]$(echo p)')
    assert out == '\001\033[0m\002p'


def test_arithmetic_in_prompt():
    sh = Shell(norc=True)
    assert _pm(sh).expand_prompt('$((3*3))') == '9'


def test_no_dollar_is_unchanged():
    sh = Shell(norc=True)
    assert _pm(sh).expand_prompt('plain> ') == 'plain> '
