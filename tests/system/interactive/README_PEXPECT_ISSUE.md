# pexpect + PSH: working conventions

> **Historical note (resolved 2026-06-10, v0.270.0).** This file used to
> document a belief that "pexpect prompt matching fails under pytest" —
> the basis for two blanket-xfail PTY suites. That premise no longer
> holds: `test_pty_smoke.py` drives the full interactive surface (prompt,
> execution, line editing, history, background job control) under pytest
> and passes deterministically. The real causes of the old failures are
> listed below.

## What actually made PTY tests fail

1. **Enter is CR, not LF.** The line editor runs the terminal in raw
   mode, where the Enter key produces `\r`. pexpect's `sendline()`
   appends `\n`, which is *not* accept-line — the command is echoed but
   never executed. Use `send(cmd + '\r')`.

2. **The DSR query.** After printing the prompt, the line editor sends
   `ESC[6n` (cursor position request) and briefly waits for the
   terminal's reply. Tests must never match the prompt with patterns
   that can collide with this escape sequence, and shouldn't be
   surprised to see it in `before`/`buffer`.

3. **Matching the echo instead of the output.** `expect('hello')` after
   typing `echo hello` matches the *echoed input*. Use sentinels whose
   expected output never appears in the typed text — e.g.
   `echo one_$((1+1))` then `expect('one_2')`.

4. **Racing the prompt.** Always `expect(PROMPT)` before sending the
   next command; sending early interleaves typed characters with the
   line editor's redraw output.

## Spawning

```python
pexpect.spawn(sys.executable,
              ['-u', '-m', 'psh', '--norc', '--force-interactive'],
              encoding='utf-8',
              env={..., 'PS1': 'PSH$ ', 'TERM': 'xterm',
                   'PYTHONUNBUFFERED': '1'})
child.send('\r')          # PSH shows the first prompt after a newline
child.expect('PSH\\$ ')
```

## Known genuine gaps (specific xfails in test_pty_smoke.py)

- SIGINT (`sendintr()`) and SIGTSTP (ctrl-z) delivered to a *running
  foreground job* do not stop/interrupt it under a pexpect PTY — the
  prompt never returns. This is a real terminal-control gap (foreground
  process-group handling), tracked as the target of the architecture
  review's is_pytest-removal phase.
