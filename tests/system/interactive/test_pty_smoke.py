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
import re
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

    def test_ps2_context_from_parser_not_data_words(self, psh):
        """Continuation context comes from the parser's open-construct
        trail, not keyword-shaped data (the old pseudo-parser split the
        buffer on whitespace: this showed 'if while> '). Bash shows '> ';
        psh's richer context must at least be TRUE."""
        psh.send('echo if ; while true\r')
        psh.expect(r'\r\nwhile> ')   # only the while is open
        psh.sendintr()
        psh.expect(PROMPT)

    def test_ps2_context_survives_keyword_data_in_for_list(self, psh):
        """`for x in done ; do` is an open for-body; the old heuristic let
        the data word 'done' pop the context (showed plain '> ')."""
        psh.send('for x in done ; do\r')
        psh.expect(r'\r\nfor> ')
        psh.sendintr()
        psh.expect(PROMPT)

    def test_incomplete_brace_expansion_executes(self, psh):
        """`echo {a,` is a complete command (bash 5.2: prints '{a,').
        The old hand-rolled brace counter hung at PS2 waiting for '}'."""
        psh.send('echo {a_$((3+3)),\r')
        psh.expect(r'\{a_6,')     # sentinel: typed text can't match this
        psh.expect(PROMPT)

    def test_backslash_space_is_escaped_space_not_continuation(self, psh):
        """`echo x\\ y` ends in no continuation; bash executes immediately.
        The old heuristic rstripped before its backslash check, so any
        line ending in 'backslash space' wrongly prompted for more."""
        psh.send('echo bs_$((4+5))\\ \r')
        psh.expect('bs_9')        # executed at once — no PS2 round-trip
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


class TestPtyViMode:
    """Arrow keys in vi editing mode (v0.283.0).

    Escape-sequence parsing used to live only in the emacs key path, so
    in vi insert mode an Up-arrow decomposed into ESC (enter normal
    mode) + '[' (unbound) + 'A' (append-at-end), corrupting the edit
    state. One centralized sequence reader now serves every mode; like
    bash vi-mode, arrows work in both insert and normal mode.
    """

    @pytest.fixture
    def vi(self, psh):
        psh.send('set -o vi\r')
        psh.expect(PROMPT)
        return psh

    def test_vi_insert_up_arrow_recalls_history(self, vi):
        vi.send('echo vi_$((3+3))\r')
        vi.expect('vi_6')
        vi.expect(PROMPT)
        vi.send('\x1b[A')         # up arrow, still in insert mode
        vi.send('\r')
        vi.expect('vi_6')

    def test_vi_insert_up_then_down_restores_empty_line(self, vi):
        vi.send('echo updown_$((2+5))\r')
        vi.expect('updown_7')
        vi.expect(PROMPT)
        vi.send('\x1b[A')         # recall
        vi.send('\x1b[B')         # back down to the (empty) current line
        vi.send('echo fresh_$((1+1))\r')
        vi.expect('fresh_2')
        # the recalled command must NOT have re-run
        assert 'updown_7' not in vi.before

    def test_vi_insert_left_arrow_edits_line(self, vi):
        vi.send('echo ac')
        vi.send('\x1b[D')         # left over 'c'
        time.sleep(0.2)           # keep ESC[D and 'b' as separate events
        vi.send('b')              # insert between a and c (insert mode kept)
        vi.send('\r')
        vi.expect('abc')

    def test_vi_normal_mode_up_arrow_recalls_history(self, vi):
        vi.send('echo norm_$((4+4))\r')
        vi.expect('norm_8')
        vi.expect(PROMPT)
        vi.send('\x1b')           # bare ESC → normal mode
        time.sleep(0.2)           # must not be glued to the arrow sequence
        vi.send('\x1b[A')         # up arrow recalls in normal mode too
        vi.send('\r')
        vi.expect('norm_8')

    def test_vi_normal_mode_left_right_arrows_move_cursor(self, vi):
        vi.send('echo xz')
        vi.send('\x1b')           # normal mode (cursor moves onto 'z')
        time.sleep(0.2)
        vi.send('\x1b[D')         # left onto 'x'
        time.sleep(0.2)
        vi.send('i')              # insert before 'x'
        vi.send('w')
        vi.send('\r')
        vi.expect('wxz')


class TestPtyHistory:
    """History recording (v0.283.0): ONE writer (the source processor),
    multi-line commands stored as a single joined entry like bash cmdhist.
    """

    def test_multiline_command_recorded_joined_once(self, psh):
        psh.send('echo a_$((1+0))\r')
        psh.expect('a_1')
        psh.expect(PROMPT)
        psh.send('for i in 9; do\r')
        psh.expect('> ')
        psh.send('echo loop_$i\r')
        psh.expect('> ')
        psh.send('done\r')
        psh.expect('loop_9')
        psh.expect(PROMPT)
        psh.send('history 5\r')
        psh.expect(PROMPT)
        # history output lines look like "    2  cmd"
        entries = re.findall(r'\d+  (.+?)\r', psh.before)
        # joined one-line form, exactly once (bash-pinned)
        joined = 'for i in 9; do echo loop_$i; done'
        assert entries.count(joined) == 1, entries
        # the individual physical lines must NOT be separate entries
        assert 'done' not in entries, entries
        assert 'echo loop_$i' not in entries, entries
        # and the single-line command appears exactly once (no double write)
        assert entries.count('echo a_$((1+0))') == 1, entries

    def test_multiline_command_up_arrow_recalls_joined(self, psh):
        psh.send('for i in 7; do\r')
        psh.expect('> ')
        psh.send('echo m_$i\r')
        psh.expect('> ')
        psh.send('done\r')
        psh.expect('m_7')
        psh.expect(PROMPT)
        psh.send('\x1b[A')        # one entry: the whole joined command
        psh.send('\r')
        psh.expect('m_7')         # re-runs fully (old code recalled 'done')

    def test_empty_history_up_arrow_recalls_first_command(self, tmp_path):
        """A session that STARTS with an empty history (fresh HOME, no
        .psh_history) must still wire up-arrow to commands recorded
        during the session. Reappraisal #15 K1: ``history or []`` handed
        the editor a PRIVATE list whenever state.history began empty, so
        recall stayed dead all session on every fresh install (the
        sibling recall test above is masked by the shared /tmp history
        file)."""
        env = {
            'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
            'HOME': str(tmp_path), 'TERM': 'xterm', 'PS1': 'PSH$ ',
            'PYTHONUNBUFFERED': '1', 'PYTHONPATH': PSH_ROOT,
        }
        child = pexpect.spawn(
            sys.executable, ['-u', '-m', 'psh', '--norc', '--force-interactive'],
            timeout=10, encoding='utf-8', env=env)
        try:
            child.send('\r')
            child.expect(PROMPT)
            child.send('echo fresh_$((20+3))\r')
            child.expect('fresh_23')
            child.expect(PROMPT)
            child.send('\x1b[A')      # up arrow: recall the only entry
            child.send('\r')
            child.expect('fresh_23')  # re-executed
        finally:
            child.close(force=True)

    def test_quoted_multiline_string_preserves_newline(self, psh):
        # bash keeps newlines that fall inside quotes verbatim in history
        psh.send('echo "one\r')
        psh.expect('> ')
        psh.send('two_$((1+1))"\r')
        psh.expect('two_2')
        psh.expect(PROMPT)
        psh.send('history 2\r')
        psh.expect(PROMPT)
        # stored as ONE entry with the embedded newline intact, not ';'-joined
        assert 'echo "one\r\ntwo_$((1+1))"' in psh.before


class TestPtyJobControl:
    def test_job_notices_go_to_stderr(self, tmp_path):
        """Launch and Done notices stay on the terminal when stdout is a file.

        Bash 5.2 writes both the "[1] PID" launch notice and the
        "[1]+  Done ..." completion notice to the shell's stderr (probed
        with the shell's own fd 1 redirected to a file: the file stays
        free of notices). Pin the same channel for psh: run psh under a
        raw pty with fd 1 pointing at a file — both notices must appear
        on the pty (stderr) and never in the file.
        """
        import pty
        import select

        out_path = tmp_path / 'stdout.txt'
        pid, fd = pty.fork()
        if pid == 0:  # child: psh with its own stdout sent to a file
            f = os.open(str(out_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
            os.dup2(f, 1)
            os.environ['PYTHONPATH'] = PSH_ROOT
            os.environ['PS1'] = 'PSH$ '
            os.execvp(sys.executable, [
                sys.executable, '-u', '-m', 'psh', '--norc',
                '--force-interactive'])

        def drain(seconds):
            data = b''
            end = time.time() + seconds
            while time.time() < end:
                r, _, _ = select.select([fd], [], [], 0.1)
                if r:
                    try:
                        chunk = os.read(fd, 4096)
                    except OSError:
                        break
                    if not chunk:
                        break
                    data += chunk
            return data

        try:
            pty_data = drain(1.0)                      # first prompt
            os.write(fd, b'sleep 0.2 &\r')
            pty_data += drain(0.6)
            os.write(fd, b'sleep 0.4\r')               # outlives the bg job
            pty_data += drain(1.2)
            os.write(fd, b'\r')                        # REPL prints Done notice
            pty_data += drain(0.8)
            os.write(fd, b'exit\r')
            pty_data += drain(0.8)
        finally:
            try:
                os.kill(pid, 9)
            except ProcessLookupError:
                pass
            os.waitpid(pid, 0)
            os.close(fd)

        pty_text = pty_data.decode(errors='replace')
        file_text = out_path.read_text() if out_path.exists() else ''
        # Both notices on the pty (the shell's stderr) ...
        assert re.search(r'\[1\] \d+', pty_text), pty_text
        assert 'Done' in pty_text, pty_text
        # ... and neither in the stdout file.
        assert 'Done' not in file_text, file_text
        assert not re.search(r'\[1\] \d+', file_text), file_text

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

    def test_jobs_lists_stopped_job(self, psh):
        """After Ctrl-Z, the job appears in `jobs` as Stopped (the stopped
        job is tracked in the job table, not silently dropped). The
        sentinel `sleep 31` distinguishes this job's command text from the
        echoed input of any other test command."""
        psh.send('sleep 31\r')
        time.sleep(0.8)
        psh.send('\x1a')           # ctrl-z
        psh.expect('Stopped', timeout=8)
        psh.expect(PROMPT)
        psh.send('jobs\r')
        # The jobs listing names the stopped job and its state.
        psh.expect('Stopped', timeout=8)
        psh.expect('sleep 31')
        psh.expect(PROMPT)
        psh.send('kill %1\r')      # clean up the stopped job
        psh.expect(PROMPT)


class TestPtyPortedLegacy:
    """Behaviors ported from the deleted legacy interactive suites
    (test_line_editing.py, test_simple_commands.py, ...) whose skip
    reasons ("escape sequences not working in PTY", "requires raw
    terminal mode") stopped being true once this smoke framework landed
    (v0.270.0+). Same conventions as above: send(cmd + '\\r'),
    arithmetic sentinels so expected output never appears in the typed
    command, always expect the prompt between commands.
    """

    def test_pipeline_executes(self, psh):
        # tr uppercases the sentinel, so the expected text can't match
        # the echo of the typed command.
        psh.send('echo start_$((30+7)) | tr a-z A-Z\r')
        psh.expect('START_37')
        psh.expect(PROMPT)

    def test_ctrl_r_reverse_search_recalls_command(self, psh):
        psh.send('echo findme_$((8+8))\r')
        psh.expect('findme_16')
        psh.expect(PROMPT)
        psh.send('echo other_$((1+2))\r')
        psh.expect('other_3')
        psh.expect(PROMPT)
        psh.send('\x12')          # ctrl-r enters reverse search
        psh.expect('bck-i-search')
        psh.send('findme')        # incremental match on the older command
        psh.send('\r')            # accept search result into the buffer
        psh.send('\r')            # execute the recalled command
        psh.expect('findme_16')

    def test_ctrl_l_clears_screen_and_keeps_session(self, psh):
        psh.send('echo before_$((2+2))\r')
        psh.expect('before_4')
        psh.expect(PROMPT)
        psh.send('\x0c')          # ctrl-l
        psh.expect(re.escape('\x1b[2J'))   # clear-screen escape emitted
        psh.send('echo after_$((10+1))\r')
        psh.expect('after_11')    # the session is still healthy

    def test_tab_completes_unique_filename(self, psh, tmp_path):
        psh.send(f'cd {tmp_path}\r')
        psh.expect(PROMPT)
        psh.send('echo data_$((50+5)) > uniquefile.txt\r')
        psh.expect(PROMPT)
        psh.send('cat uniq\t')    # completes to uniquefile.txt
        psh.send('\r')
        psh.expect('data_55')     # file content: completion must have worked

    def test_tab_expands_common_prefix(self, psh, tmp_path):
        psh.send(f'cd {tmp_path}\r')
        psh.expect(PROMPT)
        psh.send('echo content_$((40+2)) > testfile1.txt\r')
        psh.expect(PROMPT)
        psh.send('echo other > testfile2.txt\r')
        psh.expect(PROMPT)
        psh.send('cat test\t')    # expands to the common prefix 'testfile'
        psh.send('1.txt\r')       # disambiguate by hand
        psh.expect('content_42')

    @pytest.mark.xfail(strict=True, reason=(
        "psh tab completion is path-only (CompletionEngine completes "
        "filenames; bash also completes command names from PATH/builtins)"))
    def test_tab_completes_command_name(self, psh):
        psh.send('ech\t')         # bash: completes to 'echo'
        psh.send(' cc_$((3*4))\r')
        psh.expect('cc_12', timeout=4)

    @pytest.mark.xfail(strict=True, reason=(
        "psh tab completion is path-only (CompletionEngine completes "
        "filenames; bash also completes $VAR variable names)"))
    def test_tab_completes_variable_name(self, psh):
        psh.send('MYVAR_ALPHA=$((6*7))\r')
        psh.expect(PROMPT)
        psh.send('echo v_$MYVAR_AL\t')   # bash: completes to $MYVAR_ALPHA
        psh.send('\r')
        psh.expect('v_42', timeout=4)
