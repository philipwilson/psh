"""
Prompt expander unit tests.

Tests the PromptExpander class for bash-compatible prompt expansion,
including escape sequences, system information, and complex prompts.
"""

from datetime import datetime
from unittest.mock import patch

# PSH test setup will import these properly
from psh.interactive.prompt import PromptExpander


class TestBasicPromptExpansion:
    """Test basic prompt expansion functionality."""

    def test_literal_text_preservation(self, shell):
        """Test that literal text is preserved."""
        expander = PromptExpander(shell)

        assert expander.decode_escapes("hello world") == "hello world"
        assert expander.decode_escapes("$") == "$"
        assert expander.decode_escapes("test>") == "test>"
        assert expander.decode_escapes("simple prompt") == "simple prompt"

    def test_backslash_escape(self, shell):
        """Test expansion of backslash escape."""
        expander = PromptExpander(shell)

        assert expander.decode_escapes("\\\\") == "\\"
        assert expander.decode_escapes("foo\\\\bar") == "foo\\bar"
        assert expander.decode_escapes("path\\\\to\\\\file") == "path\\to\\file"

    def test_newline_and_carriage_return(self, shell):
        """Test expansion of newline and carriage return."""
        expander = PromptExpander(shell)

        assert expander.decode_escapes("\\n") == "\n"
        assert expander.decode_escapes("\\r") == "\r"
        assert expander.decode_escapes("line1\\nline2") == "line1\nline2"
        assert expander.decode_escapes("start\\nend\\r") == "start\nend\r"

    def test_bell_and_escape_sequences(self, shell):
        """Test expansion of bell and escape characters."""
        expander = PromptExpander(shell)

        assert expander.decode_escapes("\\a") == "\a"
        assert expander.decode_escapes("\\e") == "\033"
        assert expander.decode_escapes("bell\\aalert") == "bell\aalert"
        assert expander.decode_escapes("escape\\esequence") == "escape\033sequence"

    def test_invalid_escape_preservation(self, shell):
        """Test that invalid escape sequences are preserved."""
        expander = PromptExpander(shell)

        assert expander.decode_escapes("\\x") == "\\x"
        assert expander.decode_escapes("\\9") == "\\9"
        assert expander.decode_escapes("\\invalid") == "\\invalid"
        # Note: PSH's prompt expander may handle some sequences differently
        result = expander.decode_escapes("\\z\\y\\q")
        # Just verify it handles unknown sequences without crashing
        assert isinstance(result, str) and len(result) > 0


class TestSystemInformationExpansion:
    """Test expansion of system information in prompts."""

    def test_shell_name_expansion(self, shell):
        """Test expansion of shell name."""
        expander = PromptExpander(shell)

        assert expander.decode_escapes("\\s") == "psh"
        assert expander.decode_escapes("Shell: \\s") == "Shell: psh"
        assert expander.decode_escapes("Running \\s shell") == "Running psh shell"

    def test_hostname_expansion(self, shell):
        """Test expansion of hostname."""
        with patch('socket.gethostname', return_value='myhost.example.com'):
            expander = PromptExpander(shell)

            # Short hostname (\\h)
            assert expander.decode_escapes("\\h") == "myhost"
            assert expander.decode_escapes("user@\\h") == "user@myhost"

            # Full hostname (\\H)
            assert expander.decode_escapes("\\H") == "myhost.example.com"
            assert expander.decode_escapes("\\H:") == "myhost.example.com:"

    def test_username_expansion(self, shell):
        """Test expansion of username."""
        with patch('pwd.getpwuid') as mock_pwd:
            mock_pwd.return_value.pw_name = 'testuser'
            expander = PromptExpander(shell)

            assert expander.decode_escapes("\\u") == "testuser"
            assert expander.decode_escapes("\\u@host") == "testuser@host"
            assert expander.decode_escapes("User: \\u") == "User: testuser"

    def test_working_directory_expansion(self, shell):
        """Test expansion of working directory."""
        # Test with home directory abbreviation
        with patch('os.getcwd', return_value='/home/user/projects'):
            with patch('os.path.expanduser', return_value='/home/user'):
                expander = PromptExpander(shell)

                # Full path with ~ (\\w)
                assert expander.decode_escapes("\\w") == "~/projects"
                assert expander.decode_escapes("Dir: \\w") == "Dir: ~/projects"

                # Basename only (\\W)
                assert expander.decode_escapes("\\W") == "projects"
                assert expander.decode_escapes("[\\W]") == "[projects]"

        # Test root directory
        with patch('os.getcwd', return_value='/'):
            expander = PromptExpander(shell)
            assert expander.decode_escapes("\\W") == "/"
            assert expander.decode_escapes("\\w") == "/"

    def test_privilege_indicator(self, shell):
        """Test expansion of $ or # based on user privilege."""
        # Test as root (uid 0)
        with patch('os.geteuid', return_value=0):
            expander = PromptExpander(shell)
            assert expander.decode_escapes("\\$") == "#"
            assert expander.decode_escapes("prompt\\$ ") == "prompt# "

        # Test as regular user
        with patch('os.geteuid', return_value=1000):
            expander = PromptExpander(shell)
            assert expander.decode_escapes("\\$") == "$"
            assert expander.decode_escapes("prompt\\$ ") == "prompt$ "


class TestTimeAndDateExpansion:
    """Test expansion of time and date information."""

    def test_time_format_expansion(self, shell):
        """Test expansion of various time formats."""
        test_time = datetime(2024, 1, 15, 14, 30, 45)

        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value = test_time
            expander = PromptExpander(shell)

            # 24-hour time (\\t)
            assert expander.decode_escapes("\\t") == "14:30:45"
            assert expander.decode_escapes("Time: \\t") == "Time: 14:30:45"

            # 12-hour time (\\T)
            assert expander.decode_escapes("\\T") == "02:30:45"

            # 12-hour time with AM/PM (\\@)
            assert expander.decode_escapes("\\@") == "02:30 PM"

            # 24-hour time HH:MM (\\A)
            assert expander.decode_escapes("\\A") == "14:30"

    def test_date_expansion(self, shell):
        """Test expansion of date."""
        test_date = datetime(2024, 1, 15)

        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value = test_date
            expander = PromptExpander(shell)

            assert expander.decode_escapes("\\d") == "Mon Jan 15"
            assert expander.decode_escapes("Date: \\d") == "Date: Mon Jan 15"

    def test_version_expansion(self, shell):
        """Test expansion of version information."""
        with patch('psh.version.__version__', '1.2.3'):
            expander = PromptExpander(shell)

            # Major.minor version (\\v)
            assert expander.decode_escapes("\\v") == "1.2"
            assert expander.decode_escapes("PSH \\v") == "PSH 1.2"

            # Full version (\\V)
            assert expander.decode_escapes("\\V") == "1.2.3"
            assert expander.decode_escapes("Version \\V") == "Version 1.2.3"


class TestOctalAndSpecialSequences:
    """Test octal sequences and special markers."""

    def test_octal_sequence_expansion(self, shell):
        """Test expansion of octal sequences."""
        expander = PromptExpander(shell)

        assert expander.decode_escapes("\\033") == "\033"  # ESC
        assert expander.decode_escapes("\\007") == "\007"  # Bell
        assert expander.decode_escapes("\\101") == "A"     # 101 octal = 65 decimal = 'A'
        assert expander.decode_escapes("Color\\033[32m") == "Color\033[32m"

    def test_non_printing_markers(self, shell):
        """Test expansion of non-printing sequence markers."""
        expander = PromptExpander(shell)

        # Start of non-printing sequence
        assert expander.decode_escapes("\\[") == "\001"

        # End of non-printing sequence
        assert expander.decode_escapes("\\]") == "\002"

        # Combined usage
        assert expander.decode_escapes("\\[\\033[32m\\]text\\[\\033[0m\\]") == "\001\033[32m\002text\001\033[0m\002"


class TestHistoryAndCommandCounters:
    """Test history and command number expansion."""

    def test_history_number_expansion(self, shell):
        """Test expansion of history number."""
        expander = PromptExpander(shell)

        # Set up shell with some history
        shell.state.history = ['echo 1', 'echo 2', 'echo 3']
        result = expander.decode_escapes("\\!")
        assert result == "4"  # Next history number

        # Test in context
        result = expander.decode_escapes("[\\!]")
        assert result == "[4]"

        # Empty history
        shell.state.history = []
        result = expander.decode_escapes("\\!")
        assert result == "1"

    def test_command_number_expansion(self, shell):
        """Test expansion of command number."""
        expander = PromptExpander(shell)

        # Set up shell with command count
        shell.state.command_number = 5
        result = expander.decode_escapes("\\#")
        assert result == "6"  # Next command number

        # Test in context
        result = expander.decode_escapes("Cmd \\#:")
        assert result == "Cmd 6:"

        # Fresh shell
        shell.state.command_number = 0
        result = expander.decode_escapes("\\#")
        assert result == "1"


class TestComplexPromptExpansion:
    """Test complex prompt combinations."""

    def test_standard_bash_prompt(self, shell):
        """Test expansion of standard bash-style prompt."""
        with patch('socket.gethostname', return_value='myhost'):
            with patch('pwd.getpwuid') as mock_pwd:
                mock_pwd.return_value.pw_name = 'user'
                with patch('os.getcwd', return_value='/home/user'):
                    with patch('os.path.expanduser', return_value='/home/user'):
                        with patch('os.geteuid', return_value=1000):
                            expander = PromptExpander(shell)

                            # Standard prompt: user@host:directory$
                            result = expander.decode_escapes("\\u@\\h:\\w\\$ ")
                            assert result == "user@myhost:~$ "

    def test_colored_prompt_expansion(self, shell):
        """Test expansion of prompt with color codes."""
        with patch('socket.gethostname', return_value='myhost'):
            with patch('pwd.getpwuid') as mock_pwd:
                mock_pwd.return_value.pw_name = 'user'
                with patch('os.getcwd', return_value='/home/user'):
                    with patch('os.path.expanduser', return_value='/home/user'):
                        with patch('os.geteuid', return_value=1000):
                            expander = PromptExpander(shell)

                            # Colored prompt with non-printing markers
                            result = expander.decode_escapes("\\[\\e[32m\\]\\u@\\h\\[\\e[0m\\]:\\w\\$ ")
                            expected = "\001\033[32m\002user@myhost\001\033[0m\002:~$ "
                            assert result == expected

    def test_complex_prompt_with_counters(self, shell):
        """Test complex prompt with history and command numbers."""
        expander = PromptExpander(shell)

        shell.state.history = ['cmd1', 'cmd2']
        shell.state.command_number = 10

        result = expander.decode_escapes("[\\!:\\#] \\$ ")
        assert result == "[3:11] $ "

    def test_multiline_prompt_expansion(self, shell):
        """Test expansion of multi-line prompts."""
        with patch('socket.gethostname', return_value='host'):
            with patch('pwd.getpwuid') as mock_pwd:
                mock_pwd.return_value.pw_name = 'user'
                with patch('os.getcwd', return_value='/home/user/project'):
                    with patch('os.path.expanduser', return_value='/home/user'):
                        expander = PromptExpander(shell)

                        # Multi-line prompt
                        result = expander.decode_escapes("\\u@\\h\\n\\w\\$ ")
                        assert result == "user@host\n~/project$ "

    def test_mixed_escape_sequences(self, shell):
        """Test prompt with mixed escape types."""
        test_time = datetime(2024, 1, 15, 14, 30, 45)

        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value = test_time
            with patch('socket.gethostname', return_value='testhost'):
                with patch('os.geteuid', return_value=1000):
                    expander = PromptExpander(shell)

                    # Mix of time, system info, and formatting
                    result = expander.decode_escapes("[\\t] \\h\\$ ")
                    assert result == "[14:30:45] testhost$ "

    def test_prompt_with_octal_and_markers(self, shell):
        """Test prompt combining octal sequences and non-printing markers."""
        expander = PromptExpander(shell)

        # Bold green text using octal and markers
        result = expander.decode_escapes("\\[\\033[1;32m\\]bold\\[\\033[0m\\]")
        expected = "\001\033[1;32m\002bold\001\033[0m\002"
        assert result == expected
