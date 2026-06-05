from contract_tests_draft._helpers import wait_brief


def test_foreground_sigint_propagates(pty_shell):
    pty_shell.sendline("sleep 5")
    wait_brief()
    pty_shell.send_ctrl("c")
    pty_shell.expect_prompt()
    out = pty_shell.cmd("echo $?")
    assert "130" in out


def test_background_job_does_not_block(pty_shell):
    out = pty_shell.cmd("sleep 1 &")
    assert "[" in out and "]" in out
    out = pty_shell.cmd("echo done")
    assert "done" in out


def test_fg_restores_terminal_control(pty_shell):
    pty_shell.cmd("sleep 5 &")
    pty_shell.sendline("fg")
    wait_brief()
    pty_shell.send_ctrl("c")
    pty_shell.expect_prompt()
    out = pty_shell.cmd("echo $?")
    assert "130" in out


def test_jobs_reports_stopped(pty_shell):
    pty_shell.sendline("sleep 5")
    wait_brief()
    pty_shell.send_ctrl("z")
    pty_shell.expect_prompt()
    out = pty_shell.cmd("jobs")
    assert "Stopped" in out
