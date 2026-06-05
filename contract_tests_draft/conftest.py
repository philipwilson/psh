import pytest
from contract_tests_draft._helpers import run_psh_cmd, PtyShell


@pytest.fixture
def psh_cmd():
    return run_psh_cmd


@pytest.fixture
def pty_shell():
    shell = PtyShell()
    yield shell
    shell.close()
