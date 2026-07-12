"""Guard the semantics of the shared conftest fixtures.

``ShellState.variables`` is a *derived* dict rebuilt from the scope manager on
every read, so ``shell.state.variables[name] = ...`` and
``del shell.state.variables[name]`` mutate a throwaway copy and change nothing.
Two fixtures used to do exactly that (finding C5 of the 2026-07-06 tests/docs
appraisal): ``clean_shell`` "cleaned" nothing and ``shell_with_temp_dir`` never
actually moved the shell's ``$PWD``. These tests pin the corrected behavior —
each would fail against the old no-op writes — so the fixtures cannot silently
regress to writing a derived dict again.
"""


def test_clean_shell_actually_removes_ambient_variables(clean_shell, shell):
    """clean_shell must strip the ambient environment, keeping essentials.

    Against the old ``del shell.state.variables[name]`` no-op, clean_shell left
    the full environment in place (``len(clean) == len(full)``) — this test
    would have failed then and passes now.
    """
    clean = set(clean_shell.state.variables)
    full = set(shell.state.variables)

    # Essentials survive the cleaning.
    assert 'PATH' in clean

    # Something was actually removed (the no-op left everything).
    assert len(clean) < len(full), (
        "clean_shell removed nothing — it is writing the derived variables "
        "dict again instead of using the scope-manager API")

    # Nothing non-essential leaked through. Whatever remains beyond the
    # essential set is a readonly special (UID/EUID/PPID) that cannot be unset.
    essential = {'PATH', 'HOME', 'USER', 'SHELL'}
    readonly_specials = {'UID', 'EUID', 'PPID'}
    leaked = clean - essential - readonly_specials
    assert not leaked, f"clean_shell left removable ambient variables: {leaked}"


def test_shell_with_temp_dir_updates_pwd(shell_with_temp_dir, temp_dir):
    """shell_with_temp_dir must move the shell's $PWD to the temp dir.

    This fixture is now a thin alias of ``isolated_shell_with_temp_dir``
    (reappraisal-#19 T12 twin convergence), so this also guards that the aliased
    fixture still lands ``$PWD`` in the temp dir. Against the pre-alias no-op
    write, $PWD stayed at the shell's
    construction-time directory (not the temp dir), so this equality would have
    failed. Compared against the ``temp_dir`` fixture value (the logical path
    the fixture set), not ``os.getcwd()``, which resolves the macOS
    /var -> /private/var symlink.
    """
    shell = shell_with_temp_dir
    assert shell.state.get_variable('PWD') == temp_dir
