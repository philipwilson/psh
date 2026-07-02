"""
Unit tests for navigation builtins (cd, pwd, pushd, popd, dirs).

Tests cover:
- cd with various arguments
- pwd functionality
- pushd/popd directory stack
- dirs display
- CDPATH handling
- Symbolic link behavior
- Error conditions
"""

import os


class TestCdBuiltin:
    """Test cd builtin functionality."""

    def test_cd_home(self, shell, capsys):
        """Test cd with no arguments goes home."""
        home = os.path.expanduser('~')
        shell.run_command('cd')
        shell.run_command('pwd')
        captured = capsys.readouterr()
        assert captured.out.strip() == home

    def test_cd_absolute_path(self, shell, capsys):
        """Test cd with absolute path."""
        shell.run_command('cd /tmp')
        shell.run_command('pwd')
        captured = capsys.readouterr()
        # On macOS, /tmp is a symlink to /private/tmp
        assert captured.out.strip() in ['/tmp', '/private/tmp']

    def test_cd_relative_path(self, shell, capsys):
        """Test cd with relative path."""
        # Create test directory structure
        os.makedirs('testdir/subdir', exist_ok=True)

        # Get cwd before changing directory
        original_cwd = os.getcwd()

        shell.run_command('cd testdir')
        shell.run_command('pwd')
        captured = capsys.readouterr()
        assert captured.out.strip() == os.path.join(original_cwd, 'testdir')

        shell.run_command('cd subdir')
        shell.run_command('pwd')
        captured = capsys.readouterr()
        assert captured.out.strip() == os.path.join(original_cwd, 'testdir', 'subdir')

        # Clean up
        shell.run_command('cd ../..')
        os.rmdir('testdir/subdir')
        os.rmdir('testdir')

    def test_cd_parent_directory(self, shell, capsys):
        """Test cd .. to parent directory."""
        original = os.getcwd()
        shell.run_command('cd /tmp')
        shell.run_command('cd ..')
        shell.run_command('pwd')
        captured = capsys.readouterr()
        # On macOS, /tmp is in /private
        assert captured.out.strip() in ['/', '/private']

        # Return to original
        shell.run_command(f'cd {original}')

    def test_cd_dash(self, shell, capsys):
        """Test cd - to previous directory."""
        original = os.getcwd()

        shell.run_command('cd /tmp')
        shell.run_command('cd /usr')
        shell.run_command('cd -')
        captured = capsys.readouterr()
        # PSH should print the directory when using cd -
        assert '/tmp' in captured.out or '/private/tmp' in captured.out

        shell.run_command('pwd')
        captured = capsys.readouterr()
        assert captured.out.strip() in ['/tmp', '/private/tmp']

        # Return to original
        shell.run_command(f'cd {original}')

    def test_cd_nonexistent(self, shell, capsys):
        """Test cd to nonexistent directory."""
        exit_code = shell.run_command('cd /nonexistent/directory/path')
        assert exit_code != 0
        captured = capsys.readouterr()
        assert 'No such file or directory' in captured.err or 'not found' in captured.err

    def test_cd_not_directory(self, shell, capsys):
        """Test cd to file (not directory)."""
        # Create a file
        with open('testfile', 'w') as f:
            f.write('test')

        exit_code = shell.run_command('cd testfile')
        assert exit_code != 0
        captured = capsys.readouterr()
        assert 'Not a directory' in captured.err or 'not a directory' in captured.err

        # Clean up
        os.remove('testfile')

    def test_cd_permission_denied(self, shell, capsys):
        """Test cd to directory without permission."""
        # Create directory with no execute permission
        os.mkdir('noperm', 0o600)

        shell.run_command('cd noperm')
        # Might fail or succeed depending on OS

        # Clean up
        os.chmod('noperm', 0o700)
        os.rmdir('noperm')

    def test_cd_with_symlink(self, shell, capsys):
        """Test cd with symbolic links."""
        # Clean up any leftover files first
        if os.path.exists('linkdir'):
            os.unlink('linkdir')
        if os.path.exists('realdir'):
            import shutil
            shutil.rmtree('realdir', ignore_errors=True)

        # Create test structure
        os.makedirs('realdir', exist_ok=True)
        os.symlink('realdir', 'linkdir')

        shell.run_command('cd linkdir')
        shell.run_command('pwd')
        captured = capsys.readouterr()
        # PWD might show logical or physical path
        assert 'linkdir' in captured.out or 'realdir' in captured.out

        # Clean up
        shell.run_command('cd ..')
        if os.path.exists('linkdir'):
            os.unlink('linkdir')
        if os.path.exists('realdir'):
            import shutil
            shutil.rmtree('realdir', ignore_errors=True)

    def test_cd_updates_pwd(self, shell, capsys):
        """Test cd updates PWD environment variable."""
        shell.run_command('cd /tmp')
        shell.run_command('echo $PWD')
        captured = capsys.readouterr()
        assert captured.out.strip() in ['/tmp', '/private/tmp']

    def test_cd_updates_oldpwd(self, shell, capsys):
        """Test cd updates OLDPWD environment variable."""
        # First establish a known state
        shell.run_command('cd /tmp')
        shell.run_command('cd /usr')
        shell.run_command('echo $OLDPWD')
        captured = capsys.readouterr()
        assert captured.out.strip() in ['/tmp', '/private/tmp']


class TestPwdBuiltin:
    """Test pwd builtin functionality."""

    def test_pwd_basic(self, shell, capsys):
        """Test basic pwd functionality."""
        shell.run_command('pwd')
        captured = capsys.readouterr()
        cwd = os.getcwd()
        assert captured.out.strip() == cwd

    def test_pwd_after_cd(self, shell, capsys):
        """Test pwd after changing directory."""
        shell.run_command('cd /tmp')
        shell.run_command('pwd')
        captured = capsys.readouterr()
        assert captured.out.strip() in ['/tmp', '/private/tmp']


class TestPushdPopdDirs:
    """Test pushd, popd, and dirs builtins."""

    def test_popd_basic(self, shell, capsys):
        """Test basic popd functionality."""
        original = os.getcwd()

        shell.run_command('pushd /tmp')
        shell.run_command('popd')
        captured = capsys.readouterr()

        shell.run_command('pwd')
        captured = capsys.readouterr()
        assert captured.out.strip() == original

    def test_pushd_rotate(self, shell, capsys):
        """pushd +N rotates the stack, making another entry the current dir."""
        # Build stack (top -> bottom): /var /usr /tmp
        shell.run_command('cd /tmp')
        shell.run_command('pushd /usr')
        shell.run_command('pushd /var')
        capsys.readouterr()  # discard the stack echoes

        # +1 brings the second entry (/usr) to the top.
        shell.run_command('pushd +1')
        capsys.readouterr()
        shell.run_command('pwd')
        captured = capsys.readouterr()
        assert captured.out.strip() == '/usr'

    def test_dirs_display(self, shell, capsys):
        """Test dirs command display."""
        original = os.getcwd()

        shell.run_command('pushd /tmp')
        shell.run_command('pushd /usr')
        shell.run_command('dirs')
        captured = capsys.readouterr()

        # Should show all directories on stack
        assert '/usr' in captured.out
        assert '/tmp' in captured.out
        # Handle both full path and tilde-abbreviated path
        home = os.path.expanduser('~')
        if original.startswith(home):
            tilde_path = '~' + original[len(home):]
            assert original in captured.out or tilde_path in captured.out
        else:
            assert original in captured.out

    def test_dirs_clear(self, shell, capsys):
        """Test dirs -c to clear stack."""
        shell.run_command('pushd /tmp')
        shell.run_command('pushd /usr')
        # Clear captured output from pushd commands
        capsys.readouterr()

        shell.run_command('dirs -c')
        shell.run_command('dirs')
        captured = capsys.readouterr()

        # Stack should only have current directory
        lines = captured.out.strip().split()
        assert len(lines) == 1

    def test_popd_empty_stack(self, shell, capsys):
        """Test popd with empty stack."""
        shell.run_command('dirs -c')  # Clear stack
        exit_code = shell.run_command('popd')
        assert exit_code != 0
        captured = capsys.readouterr()
        assert 'directory stack empty' in captured.err.lower()


class TestCdPath:
    """Test CDPATH functionality."""

    def test_cdpath_search(self, shell, capsys):
        """Test cd searches CDPATH."""
        # Create test directories
        os.makedirs('searchdir/found', exist_ok=True)
        original = os.getcwd()

        shell.run_command(f'CDPATH={original}/searchdir')
        shell.run_command('cd found')
        shell.run_command('pwd')
        captured = capsys.readouterr()
        assert captured.out.strip().endswith('searchdir/found')

        # Clean up
        shell.run_command(f'cd {original}')
        os.rmdir('searchdir/found')
        os.rmdir('searchdir')

    def test_cdpath_multiple_paths(self, shell, capsys):
        """Test CDPATH with multiple paths."""
        # Create test directories
        os.makedirs('path1/dir1', exist_ok=True)
        os.makedirs('path2/dir2', exist_ok=True)
        original = os.getcwd()

        shell.run_command(f'CDPATH={original}/path1:{original}/path2')

        shell.run_command('cd dir2')
        shell.run_command('pwd')
        captured = capsys.readouterr()
        assert captured.out.strip().endswith('path2/dir2')

        # Clean up
        shell.run_command(f'cd {original}')
        os.rmdir('path1/dir1')
        os.rmdir('path1')
        os.rmdir('path2/dir2')
        os.rmdir('path2')

    def test_cdpath_dot_precedence(self, shell, capsys):
        """Test . in CDPATH gives current dir precedence."""
        # Create test directories
        os.makedirs('localdir', exist_ok=True)
        os.makedirs('searchpath/localdir', exist_ok=True)
        original = os.getcwd()

        # With . first in CDPATH
        shell.run_command(f'CDPATH=.:{original}/searchpath')
        shell.run_command('cd localdir')
        shell.run_command('pwd')
        captured = capsys.readouterr()
        # Should find local dir first
        assert not captured.out.strip().endswith('searchpath/localdir')

        # Clean up
        shell.run_command(f'cd {original}')
        os.rmdir('localdir')
        os.rmdir('searchpath/localdir')
        os.rmdir('searchpath')


class TestNavigationEdgeCases:
    """Test edge cases in navigation."""

    def test_cd_long_path(self, shell, capsys):
        """Test cd with very long path."""
        # Create deep directory structure
        path_parts = ['level' + str(i) for i in range(20)]
        deep_path = os.path.join(*path_parts)
        os.makedirs(deep_path, exist_ok=True)

        shell.run_command(f'cd {deep_path}')
        shell.run_command('pwd')
        captured = capsys.readouterr()
        assert captured.out.strip().endswith(path_parts[-1])

        # Clean up
        shell.run_command('cd ' + '/'.join(['..'] * 20))
        # Remove directories in reverse order
        for i in range(19, -1, -1):
            partial_path = os.path.join(*path_parts[:i+1])
            os.rmdir(partial_path)

    def test_cd_with_spaces(self, shell, capsys):
        """Test cd with directory names containing spaces."""
        dirname = 'dir with spaces'
        # Clean up any leftover directory first
        if os.path.exists(dirname):
            os.rmdir(dirname)
        os.mkdir(dirname)

        shell.run_command(f'cd "{dirname}"')
        shell.run_command('pwd')
        captured = capsys.readouterr()
        assert dirname in captured.out

        # Clean up
        shell.run_command('cd ..')
        os.rmdir(dirname)

    def test_cd_with_special_chars(self, shell, capsys):
        """Test cd with special characters in path."""
        dirname = 'dir$with@special#chars'
        # Clean up any leftover directory first
        if os.path.exists(dirname):
            os.rmdir(dirname)
        os.mkdir(dirname)

        # Need to escape the $ to prevent variable expansion
        shell.run_command(f'cd "dir\\$with@special#chars"')
        shell.run_command('pwd')
        captured = capsys.readouterr()
        assert dirname in captured.out

        # Clean up
        shell.run_command('cd ..')
        os.rmdir(dirname)
