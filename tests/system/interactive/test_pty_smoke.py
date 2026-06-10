"""PTY interactive smoke tests (v0.270.0).

A small, PASSING pexpect suite covering the interactive surface: prompt,
execution, line editing, history, and job control. This replaces the old
blanket-xfail PTY suites (test_pty_line_editing.py, test_pty_job_control.py),
whose "pexpect doesn't work under pytest" premise no longer holds.

Conventions that make these reliable:
- send(cmd + '\\r'): the line editor runs in raw mode, where Enter is CR.
  pexpect's sendline() sends LF, which is NOT accept-line.
- Arithmetic sentinels (echo x_$((1+1)) → x_2): the expected output text
  never appears in the typed command, so matching can't hit the echo.
- Always expect the next prompt before sending the next command.

Two foreground-signal interactions genuinely fail under a pexpect PTY and
carry specific xfails — they are the target of the terminal-control work
(review Tier 3, shared ProcessLauncher / is_pytest removal phase).
"""

import os
import sys
import time
from pathlib import Path

import pexpect
import pytest

PROMPT = 'PSH\\$ '
PSH_ROOT = str(Path(__file__).parent.parent.parent.parent)


def spawn_psh(timeout=10):
    env = {
        'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
        'HOME': '/tmp',
        'TERM': 'xterm',
        'PS1': 'PSH$ ',
        'PYTHONUNBUFFERED': '1',
        'PYTHONPATH': PSH_ROOT,
    }
    child = pexpect.spawn(
        sys.executable, ['-u', '-m', 'psh', '--norc', '--force-interactive'],
        timeout=timeout, encoding='utf-8', env=env)
    # PSH shows the first prompt after an initial newline in PTY mode
    child.send('\r')
    child.expect(PROMPT)
    return child


@pytest.fixture
def psh():
    child = spawn_psh()
    yield child
    child.close(force=True)


class TestPtyBasics:
    def test_prompt_on_startup(self, psh):
        # spawn_psh already matched the prompt; just verify liveness
        assert psh.isalive()

    def test_command_execution(self, psh):
        psh.send('echo one_$((1+1))\r')
        psh.expect('one_2')
        psh.expect(PROMPT)

    def test_state_persists_between_commands(self, psh):
        psh.send('x=5\r')
        psh.expect(PROMPT)
        psh.send('echo val_$x\r')
        psh.expect('val_5')
        psh.expect(PROMPT)

    def test_exit_produces_eof(self, psh):
        psh.send('exit\r')
        psh.expect(pexpect.EOF)

    def test_ctrl_d_at_empty_prompt_exits(self, psh):
        psh.sendeof()
        psh.expect(pexpect.EOF)

    def test_ctrl_c_at_prompt_clears_line(self, psh):
        psh.send('garbage_never_run')
        psh.sendintr()
        psh.expect(PROMPT)
        psh.send('echo clean_$((2+2))\r')
        psh.expect('clean_4')
        # the interrupted text must not have executed
        assert 'garbage_never_run: command not found' not in psh.before


class TestPtyLineEditing:
    def test_backspace(self, psh):
        psh.send('echo abcX')
        psh.send('\x7f')          # backspace removes X
        psh.send('\r')
        psh.expect('abc\r?\n')

    def test_left_arrow_insert(self, psh):
        psh.send('echo ac')
        psh.send('\x1b[D')        # left
        psh.send('b')             # insert between a and c
        psh.send('\r')
        psh.expect('abc')

    def test_ctrl_a_and_ctrl_k(self, psh):
        psh.send('echo old_junk')
        psh.send('\x01')          # ctrl-a → line start
        psh.send('\x0b')          # ctrl-k → kill to end
        psh.send('echo head_$((6+6))\r')
        psh.expect('head_12')

    def test_ctrl_u_clears_line(self, psh):
        psh.send('never executed text')
        psh.send('\x15')          # ctrl-u
        psh.send('echo clean_$((5+5))\r')
        psh.expect('clean_10')

    def test_ctrl_w_deletes_word(self, psh):
        psh.send('echo keep_$((7+7)) deleteme')
        psh.send('\x17')          # ctrl-w removes 'deleteme'
        psh.send('\r')
        psh.expect('keep_14\r?\n')

    def test_history_up_arrow_recall(self, psh):
        psh.send('echo recall_$((9+9))\r')
        psh.expect('recall_18')
        psh.expect(PROMPT)
        psh.send('\x1b[A')        # up arrow recalls the command
        psh.send('\r')
        psh.expect('recall_18')

    def test_ps2_continuation(self, psh):
        psh.send("echo 'one\r")
        psh.expect('> ')          # PS2
        psh.send("two'\r")
        psh.expect('two')
        psh.expect(PROMPT)

    def test_long_line_executes_correctly(self, psh):
        # Longer than the 80-column PTY: execution must still see the
        # full line even though wrapped-line redraw is imperfect.
        arg = 'z' * 150
        psh.send(f'echo {arg} | wc -c\r')
        psh.expect('151')         # 150 chars + newline
        psh.expect(PROMPT)


class TestPtyWrappedLines:
    """Editing lines longer than the terminal width (v0.273.0).

    The editor's old per-operation backspace arithmetic corrupted the
    display once a line wrapped; rendering is now a centralized
    wrap-aware repaint. These run in a 40-column PTY so every scenario
    actually wraps.
    """

    @pytest.fixture
    def narrow(self):
        env = {
            'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
            'HOME': '/tmp', 'TERM': 'xterm', 'PS1': 'PSH$ ',
            'PYTHONUNBUFFERED': '1', 'PYTHONPATH': PSH_ROOT,
        }
        child = pexpect.spawn(
            sys.executable, ['-u', '-m', 'psh', '--norc', '--force-interactive'],
            timeout=10, encoding='utf-8', env=env, dimensions=(24, 40))
        child.send('\r')
        child.expect(PROMPT)
        yield child
        child.close(force=True)

    def test_mid_edit_on_wrapped_line(self, narrow):
        arg = 'x' * 50                      # spans two rows at 40 cols
        narrow.send(f'echo {arg}END')
        time.sleep(0.2)
        narrow.send('\x1b[D' * 3)           # left over 'END'
        time.sleep(0.2)
        narrow.send('_MID_')
        narrow.send('\r')
        narrow.expect('x{50}_MID_END')

    def test_backspace_across_wrap_boundary(self, narrow):
        narrow.send('echo ' + 'y' * 40)
        time.sleep(0.2)
        narrow.send('\x7f' * 39)            # erase back across the wrap
        narrow.send('Z\r')
        narrow.expect('yZ\r?\n')

    def test_kill_line_on_wrapped_line(self, narrow):
        narrow.send('echo ' + 'z' * 60)
        time.sleep(0.2)
        narrow.send('\x01\x0b')             # ctrl-a, ctrl-k
        narrow.send('echo wrap_$((7*3))\r')
        narrow.expect('wrap_21')

    def test_history_recall_of_wrapped_line(self, narrow):
        narrow.send('echo ' + 'h' * 45 + '_$((2+3))\r')
        narrow.expect('h{45}_5')
        narrow.expect(PROMPT)
        narrow.send('\x1b[A')               # recall the wrapped command
        narrow.send('\r')
        narrow.expect('h{45}_5')

    def test_colored_marked_prompt_cursor_math(self, narrow):
        # \[ \] markers (\x01/\x02) are zero-width: editing must stay
        # correct under a colored prompt
        narrow.send("PS1='\\[\\e[32m\\]C\\[\\e[0m\\]$ '\r")
        time.sleep(0.3)
        narrow.send('echo back')
        narrow.send('\x7f' * 4)             # erase 'back'
        narrow.send('m_$((5+6))\r')
        narrow.expect('m_11')


class TestPtyJobControl:
    def test_background_job_notice_and_jobs(self, psh):
        psh.send('sleep 0.5 &\r')
        psh.expect(r'\[1\]')      # job notice with id
        psh.expect(PROMPT)
        psh.send('jobs\r')
        psh.expect('sleep')
        psh.expect(PROMPT)
        psh.send('wait\r')
        psh.expect(PROMPT)

    def test_wait_reaps_background_job(self, psh):
        psh.send('sleep 0.3 &\r')
        psh.expect(PROMPT)
        psh.send('wait\r')
        psh.expect(PROMPT)
        psh.send('echo w_$?\r')
        psh.expect('w_0')

    def test_fg_waits_for_background_job(self, psh):
        psh.send('sleep 0.6 &\r')
        psh.expect(PROMPT)
        psh.send('fg\r')
        psh.expect(PROMPT, timeout=10)   # returns once sleep finishes
        psh.send('echo back_$((4+4))\r')
        psh.expect('back_8')

    def test_disown_removes_job(self, psh):
        psh.send('sleep 5 &\r')
        psh.expect(PROMPT)
        psh.send('disown\r')
        psh.expect(PROMPT)
        psh.send('jobs\r')
        psh.expect(PROMPT)
        assert 'sleep' not in psh.before

    def test_ctrl_c_interrupts_foreground_job(self, psh):
        # v0.271.0: fixed — TCSADRAIN-class tcsetattr calls blocked on an
        # undrained pty, wedging the shell before/after foreground jobs.
        psh.send('sleep 30\r')
        time.sleep(0.8)
        psh.sendintr()
        psh.expect(PROMPT, timeout=8)
        psh.send('echo rc_$?\r')
        psh.expect('rc_130')

    def test_ctrl_z_stops_foreground_job(self, psh):
        psh.send('sleep 30\r')
        time.sleep(0.8)
        psh.send('\x1a')
        psh.expect('Stopped', timeout=8)
        psh.expect(PROMPT)
        psh.send('kill %1\r')
        psh.expect(PROMPT)

    def test_fg_resumes_stopped_job(self, psh):
        psh.send('sleep 30\r')
        time.sleep(0.8)
        psh.send('\x1a')          # ctrl-z
        psh.expect('Stopped', timeout=8)
        psh.expect(PROMPT)
        psh.send('fg\r')
        time.sleep(0.5)
        psh.sendintr()             # interrupt the resumed job
        psh.expect(PROMPT, timeout=8)
