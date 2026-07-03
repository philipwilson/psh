"""The ``expand_aliases`` shopt option gates alias expansion (reappraisal #16).

Before this fix the option was registered but never read, so ``shopt -u
expand_aliases`` was a no-op and aliases always expanded. The option is now
honored by ``Shell.expand_aliases`` — the single lex->parse-boundary gate.

Policy (pinned to bash 5.2.26 and to test-suite reality): psh keeps the option
ON by default in every mode (bash defaults it OFF non-interactively; keeping it
ON preserves the many `-c`/script tests that rely on aliases), but ``shopt -u``
now disables expansion for subsequently-parsed commands, matching bash's gate.
Because psh expands over the whole logical command at once, a same-line
``shopt -u`` does not disable a same-line use (documented parse-time divergence).
"""

import subprocess
import sys

import pytest

from psh.shell import Shell


def test_default_on_expands_across_reads():
    shell = Shell(norc=True)
    shell.run_command('alias ll="echo ALIASED"')
    assert shell.run_command('ll') == 0


def test_shopt_u_disables_for_later_reads():
    shell = Shell(norc=True)
    shell.run_command('shopt -u expand_aliases')
    shell.run_command('alias ll="echo ALIASED"')
    # Expansion off: `ll` is not a command -> command not found (bash gate).
    assert shell.run_command('ll') == 127


def test_shopt_s_reenables():
    shell = Shell(norc=True)
    shell.run_command('shopt -u expand_aliases')
    shell.run_command('alias ll="echo ALIASED"')
    assert shell.run_command('ll') == 127
    shell.run_command('shopt -s expand_aliases')
    assert shell.run_command('ll') == 0


def test_option_registered_default_true():
    shell = Shell(norc=True)
    assert shell.state.options.get('expand_aliases') is True


@pytest.mark.serial
def test_script_shopt_u_disables_subsequent_line(tmp_path):
    # In a script (command-by-command reads), `shopt -u` on line 1 disables
    # expansion of the alias used on line 3 (bash requires the option ON).
    script = tmp_path / "s.sh"
    script.write_text('shopt -u expand_aliases\nalias ll="echo A"\nll\n')
    result = subprocess.run(
        [sys.executable, '-m', 'psh', str(script)],
        capture_output=True, text=True)
    assert result.returncode == 127
    assert 'A' not in result.stdout
    assert 'not found' in result.stderr
