"""
Unit tests for directory stack builtins (pushd, popd, dirs).

Tests cover:
- Basic pushd/popd functionality
- Directory stack rotation
- dirs command options
- Stack manipulation with indices
- Error conditions
- Integration with cd command
"""

import os


def tilde_abbrev(path):
    """Expected dirs/pushd display form of a path: bash abbreviates a
    $HOME prefix to ``~`` (exact match or HOME + separator, so siblings
    like /home/userfoo are untouched). Computed here independently so the
    tests hold wherever the checkout lives (under $HOME on CI, elsewhere
    locally)."""
    home = os.path.expanduser('~')
    if path == home:
        return '~'
    if path.startswith(home + os.sep):
        return '~' + path[len(home):]
    return path


class TestPushdBuiltin:
    """Test pushd builtin functionality."""

    def test_pushd_basic(self, shell, capsys):
        """Test basic pushd functionality."""
        original = os.getcwd()

        # Create test directory
        test_dir = "test_pushd"
        os.makedirs(test_dir, exist_ok=True)

        try:
            # Push directory onto stack
            exit_code = shell.run_command(f'pushd {test_dir}')
            assert exit_code == 0

            captured = capsys.readouterr()
            # Should show the stack after push
            assert test_dir in captured.out
            # Original directory is shown with $HOME abbreviated to ~
            assert tilde_abbrev(original) in captured.out

            # Verify we're in the new directory
            shell.run_command('pwd')
            captured = capsys.readouterr()
            assert captured.out.strip().endswith(test_dir)

        finally:
            # Clean up
            shell.run_command(f'cd {original}')
            if os.path.exists(test_dir):
                os.rmdir(test_dir)

    def test_pushd_absolute_path(self, shell, capsys):
        """Test pushd with absolute path."""
        original = os.getcwd()

        exit_code = shell.run_command('pushd /tmp')
        assert exit_code == 0

        captured = capsys.readouterr()
        # /tmp resolves to /private/tmp on macOS; either may itself be
        # displayed tilde-abbreviated if it falls under $HOME.
        assert any(tilde_abbrev(p) in captured.out for p in ('/tmp', '/private/tmp'))
        # Original directory is shown with $HOME abbreviated to ~
        assert tilde_abbrev(original) in captured.out

        # Verify current directory
        shell.run_command('pwd')
        captured = capsys.readouterr()
        assert captured.out.strip() in ['/tmp', '/private/tmp']

        # Return to original
        shell.run_command(f'cd {original}')

    def test_pushd_relative_path(self, shell, capsys):
        """Test pushd with relative path."""
        original = os.getcwd()

        # Create nested test directories
        test_path = "level1/level2"
        os.makedirs(test_path, exist_ok=True)

        try:
            exit_code = shell.run_command('pushd level1/level2')
            assert exit_code == 0

            # Verify we're in the right place
            shell.run_command('pwd')
            captured = capsys.readouterr()
            assert captured.out.strip().endswith('level1/level2')

        finally:
            # Clean up
            shell.run_command(f'cd {original}')
            import shutil
            if os.path.exists('level1'):
                shutil.rmtree('level1')

    def test_pushd_no_args_swap(self, shell, capsys):
        """Test pushd with no arguments swaps top two directories."""
        original = os.getcwd()

        # Create test directory
        test_dir = "test_swap"
        os.makedirs(test_dir, exist_ok=True)

        try:
            # Push directory to build stack
            shell.run_command(f'pushd {test_dir}')
            shell.run_command('pushd /tmp')

            # Now pushd with no args should swap
            exit_code = shell.run_command('pushd')
            assert exit_code == 0

            # Should be back in test_dir
            shell.run_command('pwd')
            captured = capsys.readouterr()
            assert captured.out.strip().endswith(test_dir)

        finally:
            # Clean up
            shell.run_command(f'cd {original}')
            if os.path.exists(test_dir):
                os.rmdir(test_dir)

    def test_pushd_rotate_stack(self, shell, capsys):
        """Test pushd +N and -N for stack rotation."""
        original = os.getcwd()

        # Create test directories
        dirs = ["dir1", "dir2", "dir3"]
        for d in dirs:
            os.makedirs(d, exist_ok=True)

        try:
            # Build stack: original -> dir1 -> dir2 -> dir3
            for d in dirs:
                abs_path = os.path.join(original, d)
                shell.run_command(f'pushd {abs_path}')

            # Test +1 rotation (move 2nd entry to top)
            exit_code = shell.run_command('pushd +1')
            assert exit_code == 0

            # Should now be in dir2
            shell.run_command('pwd')
            captured = capsys.readouterr()
            assert captured.out.strip().endswith('dir2')

            # Test -1 rotation (move last entry to top)
            exit_code = shell.run_command('pushd -1')
            assert exit_code == 0

        finally:
            # Clean up
            shell.run_command(f'cd {original}')
            for d in dirs:
                if os.path.exists(d):
                    os.rmdir(d)

    def test_pushd_nonexistent_directory(self, shell, capsys):
        """Test pushd with nonexistent directory."""
        exit_code = shell.run_command('pushd /nonexistent/directory')
        assert exit_code != 0

        captured = capsys.readouterr()
        assert 'No such file' in captured.err or 'not found' in captured.err

    def test_pushd_not_directory(self, shell, capsys):
        """Test pushd with file instead of directory."""
        # Create a file
        with open('testfile', 'w') as f:
            f.write('test')

        try:
            exit_code = shell.run_command('pushd testfile')
            assert exit_code != 0

            captured = capsys.readouterr()
            assert 'Not a directory' in captured.err or 'not a directory' in captured.err

        finally:
            os.remove('testfile')

    def test_pushd_permission_denied(self, shell, capsys):
        """Test pushd with permission denied."""
        # Create directory with no execute permission
        test_dir = 'noperm'
        os.mkdir(test_dir, 0o600)

        try:
            shell.run_command(f'pushd {test_dir}')
            # May succeed or fail depending on system

        finally:
            # Clean up
            os.chmod(test_dir, 0o700)
            os.rmdir(test_dir)


class TestPopdBuiltin:
    """Test popd builtin functionality."""

    def test_popd_basic(self, shell, capsys):
        """Test basic popd functionality."""
        original = os.getcwd()

        # Create test directory and push it
        test_dir = "test_popd"
        os.makedirs(test_dir, exist_ok=True)

        try:
            shell.run_command(f'pushd {test_dir}')

            # Pop back to original
            exit_code = shell.run_command('popd')
            assert exit_code == 0

            # Clear capture buffer before pwd
            capsys.readouterr()

            # Should be back in original directory
            shell.run_command('pwd')
            captured = capsys.readouterr()
            assert captured.out.strip() == original

        finally:
            # Clean up
            shell.run_command(f'cd {original}')
            if os.path.exists(test_dir):
                os.rmdir(test_dir)

    def test_popd_multiple_stack(self, shell, capsys):
        """Test popd with multiple directories on stack."""
        original = os.getcwd()

        # Create test directories
        dirs = ["pop1", "pop2", "pop3"]
        for d in dirs:
            os.makedirs(d, exist_ok=True)

        try:
            # Build stack
            for d in dirs:
                abs_path = os.path.join(original, d)
                shell.run_command(f'pushd {abs_path}')

            # Pop once - should be in pop2
            shell.run_command('popd')
            shell.run_command('pwd')
            captured = capsys.readouterr()
            assert captured.out.strip().endswith('pop2')

            # Pop again - should be in pop1
            shell.run_command('popd')
            shell.run_command('pwd')
            captured = capsys.readouterr()
            assert captured.out.strip().endswith('pop1')

            # Pop final - should be back to original
            shell.run_command('popd')

            # Clear capture buffer before final pwd
            capsys.readouterr()

            shell.run_command('pwd')
            captured = capsys.readouterr()
            assert captured.out.strip() == original

        finally:
            # Clean up
            shell.run_command(f'cd {original}')
            for d in dirs:
                if os.path.exists(d):
                    os.rmdir(d)

    def test_popd_with_index(self, shell, capsys):
        """Test popd +N to remove specific entry."""
        original = os.getcwd()

        # Create test directories
        dirs = ["idx1", "idx2", "idx3"]
        for d in dirs:
            os.makedirs(d, exist_ok=True)

        try:
            # Build stack
            for d in dirs:
                abs_path = os.path.join(original, d)
                shell.run_command(f'pushd {abs_path}')

            # Remove entry at index 1 (should remove idx2)
            exit_code = shell.run_command('popd +1')
            assert exit_code == 0

            # Current directory should not change (still idx3)
            shell.run_command('pwd')
            captured = capsys.readouterr()
            assert captured.out.strip().endswith('idx3')

            # But idx2 should be removed from stack
            shell.run_command('dirs')
            captured = capsys.readouterr()
            assert 'idx2' not in captured.out

        finally:
            # Clean up
            shell.run_command(f'cd {original}')
            for d in dirs:
                if os.path.exists(d):
                    os.rmdir(d)

    def test_popd_empty_stack(self, shell, capsys):
        """Test popd with empty stack."""
        # Clear any existing stack
        shell.run_command('dirs -c')

        exit_code = shell.run_command('popd')
        assert exit_code != 0

        captured = capsys.readouterr()
        assert 'directory stack empty' in captured.err.lower() or 'stack empty' in captured.err.lower()

    def test_popd_invalid_index(self, shell, capsys):
        """Test popd with invalid index."""
        # Build small stack
        test_dir = "test_invalid"
        os.makedirs(test_dir, exist_ok=True)

        try:
            shell.run_command(f'pushd {test_dir}')

            # Try to pop invalid index
            exit_code = shell.run_command('popd +99')
            assert exit_code != 0

            captured = capsys.readouterr()
            assert 'invalid' in captured.err.lower() or 'out of range' in captured.err.lower()

        finally:
            # Clean up
            original = os.getcwd()
            shell.run_command(f'cd {original}')
            if os.path.exists(test_dir):
                os.rmdir(test_dir)


class TestDirsBuiltin:
    """Test dirs builtin functionality."""

    def test_dirs_basic(self, shell, capsys):
        """Test basic dirs functionality."""
        original = os.getcwd()

        # Initially should show just current directory
        shell.run_command('dirs')
        captured = capsys.readouterr()
        # Directory is shown with $HOME abbreviated to ~
        assert tilde_abbrev(original) in captured.out

    def test_dirs_with_stack(self, shell, capsys):
        """Test dirs with directories on stack."""
        original = os.getcwd()

        # Create test directories
        dirs = ["stack1", "stack2"]
        for d in dirs:
            os.makedirs(d, exist_ok=True)

        try:
            # Build stack
            for d in dirs:
                abs_path = os.path.join(original, d)
                shell.run_command(f'pushd {abs_path}')

            # Show stack
            shell.run_command('dirs')
            captured = capsys.readouterr()

            # Should show all directories
            assert 'stack2' in captured.out  # current (top of stack)
            assert 'stack1' in captured.out
            # Original directory is shown with $HOME abbreviated to ~
            assert tilde_abbrev(original) in captured.out  # bottom of stack

        finally:
            # Clean up
            shell.run_command(f'cd {original}')
            for d in dirs:
                if os.path.exists(d):
                    os.rmdir(d)

    def test_dirs_vertical_format(self, shell, capsys):
        """Test dirs -v for vertical format with indices."""
        original = os.getcwd()

        # Create test directory
        test_dir = "test_vertical"
        os.makedirs(test_dir, exist_ok=True)

        try:
            shell.run_command(f'pushd {test_dir}')

            # Show in vertical format
            exit_code = shell.run_command('dirs -v')
            assert exit_code == 0

            captured = capsys.readouterr()
            # Should show indices
            assert '0' in captured.out  # Current directory index
            assert '1' in captured.out  # Previous directory index

        finally:
            # Clean up
            shell.run_command(f'cd {original}')
            if os.path.exists(test_dir):
                os.rmdir(test_dir)

    def test_dirs_long_format(self, shell, capsys):
        """dirs -l prints full paths, never abbreviating home to '~'."""
        original = os.getcwd()
        try:
            shell.run_command('cd ~')
            shell.run_command('pushd /tmp')
            capsys.readouterr()

            shell.run_command('dirs -l')
            captured = capsys.readouterr()
            # Long format must not abbreviate the home directory with a tilde.
            assert '~' not in captured.out
        finally:
            shell.run_command(f'cd {original}')

    def test_dirs_clear_stack(self, shell, capsys):
        """Test dirs -c to clear stack."""
        original = os.getcwd()

        # Create and push test directory
        test_dir = "test_clear"
        os.makedirs(test_dir, exist_ok=True)

        try:
            shell.run_command(f'pushd {test_dir}')

            # Verify stack has multiple entries
            shell.run_command('dirs')
            captured = capsys.readouterr()
            lines = captured.out.strip().split()
            assert len(lines) >= 2

            # Clear stack
            exit_code = shell.run_command('dirs -c')
            assert exit_code == 0

            # Stack should now have only current directory
            shell.run_command('dirs')
            captured = capsys.readouterr()
            lines = captured.out.strip().split()
            assert len(lines) == 1

        finally:
            # Clean up
            shell.run_command(f'cd {original}')
            if os.path.exists(test_dir):
                os.rmdir(test_dir)

    def test_dirs_plus_index(self, shell, capsys):
        """Test dirs +N to show Nth entry from left."""
        original = os.getcwd()

        # Build stack with multiple directories
        dirs = ["plus1", "plus2", "plus3"]
        for d in dirs:
            os.makedirs(d, exist_ok=True)

        try:
            for d in dirs:
                abs_path = os.path.join(original, d)
                shell.run_command(f'pushd {abs_path}')

            # Clear capture buffer after pushd commands
            capsys.readouterr()

            # Show entry at index 1
            exit_code = shell.run_command('dirs +1')
            assert exit_code == 0

            captured = capsys.readouterr()
            # Should show only one directory
            lines = captured.out.strip().split()
            assert len(lines) == 1

        finally:
            # Clean up
            shell.run_command(f'cd {original}')
            for d in dirs:
                if os.path.exists(d):
                    os.rmdir(d)

    def test_dirs_minus_index(self, shell, capsys):
        """Test dirs -N to show Nth entry from right."""
        original = os.getcwd()

        # Build stack with multiple directories
        dirs = ["minus1", "minus2"]
        for d in dirs:
            os.makedirs(d, exist_ok=True)

        try:
            for d in dirs:
                abs_path = os.path.join(original, d)
                shell.run_command(f'pushd {abs_path}')

            # Clear capture buffer after pushd commands
            capsys.readouterr()

            # Bash-verified (bash 5.2): -N counts from the RIGHT, 0-based.
            # Stack is [minus2, minus1, original], so -0 is the bottom
            # (original) and -1 is the entry above it (minus1).
            exit_code = shell.run_command('dirs -1')
            assert exit_code == 0

            captured = capsys.readouterr()
            lines = captured.out.strip().split()
            assert len(lines) == 1
            assert captured.out.strip().endswith('minus1')

            # -0 shows the bottom of the stack (the original directory),
            # with $HOME abbreviated to ~
            exit_code = shell.run_command('dirs -0')
            assert exit_code == 0
            captured = capsys.readouterr()
            assert captured.out.strip() == tilde_abbrev(original)

        finally:
            # Clean up
            shell.run_command(f'cd {original}')
            for d in dirs:
                if os.path.exists(d):
                    os.rmdir(d)

    def test_dirs_p_one_per_line(self, shell, capsys):
        """dirs -p lists one directory per line without indices (bash-verified)."""
        original = os.getcwd()
        os.makedirs("perline", exist_ok=True)

        try:
            shell.run_command(f'pushd {os.path.join(original, "perline")}')
            capsys.readouterr()

            exit_code = shell.run_command('dirs -p')
            assert exit_code == 0

            captured = capsys.readouterr()
            lines = captured.out.strip().split('\n')
            assert len(lines) == 2
            assert lines[0].endswith('perline')
            assert lines[1] == tilde_abbrev(original)
            # No index column (that's -v)
            assert not lines[0].startswith(' 0')

        finally:
            shell.run_command(f'cd {original}')
            if os.path.exists("perline"):
                os.rmdir("perline")

    def test_popd_minus_index_counts_from_right(self, shell, capsys):
        """popd -N removes the Nth entry from the right, 0-based (bash-verified).

        With stack [c, b, original], `popd -1` removes b (bash 5.2 counts
        -0 as the bottom), leaving [c, original].
        """
        original = os.getcwd()
        for d in ("popm_b", "popm_c"):
            os.makedirs(d, exist_ok=True)

        try:
            shell.run_command(f'pushd {os.path.join(original, "popm_b")}')
            shell.run_command(f'pushd {os.path.join(original, "popm_c")}')
            capsys.readouterr()

            exit_code = shell.run_command('popd -1')
            assert exit_code == 0

            shell.run_command('dirs')
            captured = capsys.readouterr()
            last_line = captured.out.strip().split('\n')[-1]
            entries = last_line.split()
            assert len(entries) == 2
            assert entries[0].endswith('popm_c')
            assert entries[1] == tilde_abbrev(original)

        finally:
            shell.run_command(f'cd {original}')
            for d in ("popm_b", "popm_c"):
                if os.path.exists(d):
                    os.rmdir(d)

    def test_dirs_invalid_index(self, shell, capsys):
        """Test dirs with invalid index."""
        exit_code = shell.run_command('dirs +99')
        assert exit_code != 0

        captured = capsys.readouterr()
        assert 'invalid' in captured.err.lower() or 'out of range' in captured.err.lower()


class TestDirectoryStackIntegration:
    """Test integration between directory stack commands."""

    def test_pushd_popd_round_trip(self, shell, capsys):
        """Test pushd followed by popd returns to original."""
        original = os.getcwd()

        # Create test directories
        dirs = ["trip1", "trip2", "trip3"]
        for d in dirs:
            os.makedirs(d, exist_ok=True)

        try:
            # Push multiple directories
            for d in dirs:
                abs_path = os.path.join(original, d)
                shell.run_command(f'pushd {abs_path}')

            # Pop them all back
            for _ in dirs:
                shell.run_command('popd')

            # Clear capture buffer after popd commands
            capsys.readouterr()

            # Should be back to original
            shell.run_command('pwd')
            captured = capsys.readouterr()
            assert captured.out.strip() == original

        finally:
            # Clean up
            shell.run_command(f'cd {original}')
            for d in dirs:
                if os.path.exists(d):
                    os.rmdir(d)

    def test_cd_preserves_stack(self, shell, capsys):
        """cd keeps the DEEP stack entries but the top tracks the cwd.

        bash's dirs always shows the current directory as entry 0 (probe
        r19-T3: `pushd /var; cd /; dirs` -> `/ /tmp`): a plain cd replaces
        the top of the stack, while the entries below it are preserved. psh
        used to show the stale pushd target at the top instead.
        """
        original = os.getcwd()

        # Create test directories
        test_dir1 = "preserve1"
        test_dir2 = "preserve2"
        os.makedirs(test_dir1, exist_ok=True)
        os.makedirs(test_dir2, exist_ok=True)

        try:
            # Build stack with pushd
            abs_path1 = os.path.join(original, test_dir1)
            shell.run_command(f'pushd {abs_path1}')

            # cd elsewhere: the stack's top must now track the new cwd
            abs_path2 = os.path.join(original, test_dir2)
            shell.run_command(f'cd {abs_path2}')

            # Clear capture buffer after pushd and cd commands
            capsys.readouterr()

            # Top tracks the cwd (bash); deeper entries preserved
            shell.run_command('dirs')
            captured = capsys.readouterr()
            assert test_dir2 in captured.out
            assert test_dir1 not in captured.out
            # Original directory is shown with $HOME abbreviated to ~
            assert tilde_abbrev(original) in captured.out

            # Clear capture buffer before pwd
            capsys.readouterr()

            # But current directory should be test_dir2
            shell.run_command('pwd')
            captured = capsys.readouterr()
            assert captured.out.strip().endswith(test_dir2)

        finally:
            # Clean up
            shell.run_command(f'cd {original}')
            for d in [test_dir1, test_dir2]:
                if os.path.exists(d):
                    os.rmdir(d)

    def test_stack_persistence_across_commands(self, shell, capsys):
        """Test stack persists across different commands."""
        original = os.getcwd()

        # Create test directory
        test_dir = "persist_test"
        os.makedirs(test_dir, exist_ok=True)

        try:
            # Build stack
            abs_path = os.path.join(original, test_dir)
            shell.run_command(f'pushd {abs_path}')

            # Run some other commands
            shell.run_command('echo "test"')
            shell.run_command('pwd')

            # Clear capture buffer after all commands
            capsys.readouterr()

            # Stack should still be intact
            shell.run_command('dirs')
            captured = capsys.readouterr()
            assert test_dir in captured.out
            # Original directory is shown with $HOME abbreviated to ~
            assert tilde_abbrev(original) in captured.out

            # Should still be able to pop
            shell.run_command('popd')

            # Clear capture buffer before final pwd
            capsys.readouterr()

            shell.run_command('pwd')
            captured = capsys.readouterr()
            assert captured.out.strip() == original

        finally:
            # Clean up
            shell.run_command(f'cd {original}')
            if os.path.exists(test_dir):
                os.rmdir(test_dir)


class TestFormatDirectoryForDisplay:
    """The shared ~ abbreviation helper (pushd/popd/dirs)."""

    def test_home_itself_becomes_tilde(self):
        from psh.builtins.directory_stack import format_directory_for_display
        home = os.path.expanduser('~')
        assert format_directory_for_display(home) == '~'

    def test_subdir_of_home_abbreviated(self):
        from psh.builtins.directory_stack import format_directory_for_display
        home = os.path.expanduser('~')
        assert format_directory_for_display(home + os.sep + 'proj') == '~' + os.sep + 'proj'

    def test_sibling_of_home_not_mangled(self):
        # Regression: the old pushd/popd copies used startswith(home), which
        # turned a sibling like /home/userfoo into ~foo.
        from psh.builtins.directory_stack import format_directory_for_display
        home = os.path.expanduser('~')
        sibling = home + 'foo'
        assert format_directory_for_display(sibling) == sibling

    def test_no_tilde_returns_path_verbatim(self):
        from psh.builtins.directory_stack import format_directory_for_display
        home = os.path.expanduser('~')
        assert format_directory_for_display(home, no_tilde=True) == home


class TestDirectoryStackEdgeCases:
    """Test edge cases and error conditions."""

    def test_very_deep_stack(self, shell, capsys):
        """Test with many directories on stack."""
        original = os.getcwd()

        # Create many test directories
        dirs = [f"deep{i}" for i in range(10)]
        for d in dirs:
            os.makedirs(d, exist_ok=True)

        try:
            # Push all directories
            for d in dirs:
                abs_path = os.path.join(original, d)
                shell.run_command(f'pushd {abs_path}')

            # Clear capture buffer after pushd commands
            capsys.readouterr()

            # Verify stack depth
            shell.run_command('dirs')
            captured = capsys.readouterr()
            lines = captured.out.strip().split()
            assert len(lines) == len(dirs) + 1  # +1 for original

            # Pop all back
            for _ in dirs:
                shell.run_command('popd')

            # Clear capture buffer before final pwd
            capsys.readouterr()

            # Should be back to original
            shell.run_command('pwd')
            captured = capsys.readouterr()
            assert captured.out.strip() == original

        finally:
            # Clean up
            shell.run_command(f'cd {original}')
            for d in dirs:
                if os.path.exists(d):
                    os.rmdir(d)

    def test_stack_with_symlinks(self, shell, capsys):
        """Test directory stack with symbolic links."""
        original = os.getcwd()

        # Create real directory and symlink
        real_dir = "real_target"
        link_dir = "symlink_dir"
        os.makedirs(real_dir, exist_ok=True)

        try:
            os.symlink(real_dir, link_dir)

            # Push symlink
            shell.run_command(f'pushd {link_dir}')

            # Verify stack shows symlink path
            shell.run_command('dirs')
            capsys.readouterr()
            # May show symlink or real path depending on implementation

            shell.run_command('popd')

        finally:
            # Clean up
            shell.run_command(f'cd {original}')
            if os.path.exists(link_dir):
                os.unlink(link_dir)
            if os.path.exists(real_dir):
                os.rmdir(real_dir)

    def test_stack_with_special_characters(self, shell, capsys):
        """Test directory stack with special characters in names."""
        original = os.getcwd()

        # Create directory with special characters
        special_dir = "dir with spaces & symbols!"
        os.makedirs(special_dir, exist_ok=True)

        try:
            # Push directory with special name
            shell.run_command(f'pushd "{special_dir}"')

            # Verify it works
            shell.run_command('pwd')
            captured = capsys.readouterr()
            assert special_dir in captured.out

            # Verify stack display
            shell.run_command('dirs')
            captured = capsys.readouterr()
            assert special_dir in captured.out

            shell.run_command('popd')

        finally:
            # Clean up
            shell.run_command(f'cd {original}')
            if os.path.exists(special_dir):
                os.rmdir(special_dir)
