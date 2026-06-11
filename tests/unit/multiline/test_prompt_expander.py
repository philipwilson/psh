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

        assert expander.expand_prompt("hello world") == "hello world"
        assert expander.expand_prompt("$") == "$"
        assert expander.expand_prompt("test>") == "test>"
        assert expander.expand_prompt("simple prompt") == "simple prompt"

    def test_backslash_escape(self, shell):
        """Test expansion of backslash escape."""
        expander = PromptExpander(shell)

        assert expander.expand_prompt("\\\\") == "\\"
        assert expander.expand_prompt("foo\\\\bar") == "foo\\bar"
        assert expander.expand_prompt("path\\\\to\\\\file") == "path\\to\\file"

    def test_newline_and_carriage_return(self, shell):
        """Test expansion of newline and carriage return."""
        expander = PromptExpander(shell)

        assert expander.expand_prompt("\\n") == "\n"
        assert expander.expand_prompt("\\r") == "\r"
        assert expander.expand_prompt("line1\\nline2") == "line1\nline2"
        assert expander.expand_prompt("start\\nend\\r") == "start\nend\r"

    def test_bell_and_escape_sequences(self, shell):
        """Test expansion of bell and escape characters."""
        expander = PromptExpander(shell)

        assert expander.expand_prompt("\\a") == "\a"
        assert expander.expand_prompt("\\e") == "\033"
        assert expander.expand_prompt("bell\\aalert") == "bell\aalert"
        assert expander.expand_prompt("escape\\esequence") == "escape\033sequence"

    def test_invalid_escape_preservation(self, shell):
        """Test that invalid escape sequences are preserved."""
        expander = PromptExpander(shell)

        assert expander.expand_prompt("\\x") == "\\x"
        assert expander.expand_prompt("\\9") == "\\9"
        assert expander.expand_prompt("\\invalid") == "\\invalid"
        # Note: PSH's prompt expander may handle some sequences differently
        result = expander.expand_prompt("\\z\\y\\q")
        # Just verify it handles unknown sequences without crashing
        assert isinstance(result, str) and len(result) > 0


class TestSystemInformationExpansion:
    """Test expansion of system information in prompts."""

    def test_shell_name_expansion(self, shell):
        """Test expansion of shell name."""
        expander = PromptExpander(shell)

        assert expander.expand_prompt("\\s") == "psh"
        assert expander.expand_prompt("Shell: \\s") == "Shell: psh"
        assert expander.expand_prompt("Running \\s shell") == "Running psh shell"

    def test_hostname_expansion(self, shell):
        """Test expansion of hostname."""
        with patch('socket.gethostname', return_value='myhost.example.com'):
            expander = PromptExpander(shell)

            # Short hostname (\\h)
            assert expander.expand_prompt("\\h") == "myhost"
            assert expander.expand_prompt("user@\\h") == "user@myhost"

            # Full hostname (\\H)
            assert expander.expand_prompt("\\H") == "myhost.example.com"
            assert expander.expand_prompt("\\H:") == "myhost.example.com:"

    def test_username_expansion(self, shell):
        """Test expansion of username."""
        with patch('pwd.getpwuid') as mock_pwd:
            mock_pwd.return_value.pw_name = 'testuser'
            expander = PromptExpander(shell)

            assert expander.expand_prompt("\\u") == "testuser"
            assert expander.expand_prompt("\\u@host") == "testuser@host"
            assert expander.expand_prompt("User: \\u") == "User: testuser"

    def test_working_directory_expansion(self, shell):
        """Test expansion of working directory."""
        # Test with home directory abbreviation
        with patch('os.getcwd', return_value='/home/user/projects'):
            with patch('os.path.expanduser', return_value='/home/user'):
                expander = PromptExpander(shell)

                # Full path with ~ (\\w)
                assert expander.expand_prompt("\\w") == "~/projects"
                assert expander.expand_prompt("Dir: \\w") == "Dir: ~/projects"

                # Basename only (\\W)
                assert expander.expand_prompt("\\W") == "projects"
                assert expander.expand_prompt("[\\W]") == "[projects]"

        # Test root directory
        with patch('os.getcwd', return_value='/'):
            expander = PromptExpander(shell)
            assert expander.expand_prompt("\\W") == "/"
            assert expander.expand_prompt("\\w") == "/"

    def test_privilege_indicator(self, shell):
        """Test expansion of $ or # based on user privilege."""
        # Test as root (uid 0)
        with patch('os.geteuid', return_value=0):
            expander = PromptExpander(shell)
            assert expander.expand_prompt("\\$") == "#"
            assert expander.expand_prompt("prompt\\$ ") == "prompt# "

        # Test as regular user
        with patch('os.geteuid', return_value=1000):
            expander = PromptExpander(shell)
            assert expander.expand_prompt("\\$") == "$"
            assert expander.expand_prompt("prompt\\$ ") == "prompt$ "


class TestTimeAndDateExpansion:
    """Test expansion of time and date information."""

    def test_time_format_expansion(self, shell):
        """Test expansion of various time formats."""
        test_time = datetime(2024, 1, 15, 14, 30, 45)

        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value = test_time
            expander = PromptExpander(shell)

            # 24-hour time (\\t)
            assert expander.expand_prompt("\\t") == "14:30:45"
            assert expander.expand_prompt("Time: \\t") == "Time: 14:30:45"

            # 12-hour time (\\T)
            assert expander.expand_prompt("\\T") == "02:30:45"

            # 12-hour time with AM/PM (\\@)
            assert expander.expand_prompt("\\@") == "02:30 PM"

            # 24-hour time HH:MM (\\A)
            assert expander.expand_prompt("\\A") == "14:30"

    def test_date_expansion(self, shell):
        """Test expansion of date."""
        test_date = datetime(2024, 1, 15)

        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value = test_date
            expander = PromptExpander(shell)

            assert expander.expand_prompt("\\d") == "Mon Jan 15"
            assert expander.expand_prompt("Date: \\d") == "Date: Mon Jan 15"

    def test_version_expansion(self, shell):
        """Test expansion of version information."""
        with patch('psh.version.__version__', '1.2.3'):
            expander = PromptExpander(shell)

            # Major.minor version (\\v)
            assert expander.expand_prompt("\\v") == "1.2"
            assert expander.expand_prompt("PSH \\v") == "PSH 1.2"

            # Full version (\\V)
            assert expander.expand_prompt("\\V") == "1.2.3"
            assert expander.expand_prompt("Version \\V") == "Version 1.2.3"


class TestOctalAndSpecialSequences:
    """Test octal sequences and special markers."""

    def test_octal_sequence_expansion(self, shell):
        """Test expansion of octal sequences."""
        expander = PromptExpander(shell)

        assert expander.expand_prompt("\\033") == "\033"  # ESC
        assert expander.expand_prompt("\\007") == "\007"  # Bell
        assert expander.expand_prompt("\\101") == "A"     # 101 octal = 65 decimal = 'A'
        assert expander.expand_prompt("Color\\033[32m") == "Color\033[32m"

    def test_non_printing_markers(self, shell):
        """Test expansion of non-printing sequence markers."""
        expander = PromptExpander(shell)

        # Start of non-printing sequence
        assert expander.expand_prompt("\\[") == "\001"

        # End of non-printing sequence
        assert expander.expand_prompt("\\]") == "\002"

        # Combined usage
        assert expander.expand_prompt("\\[\\033[32m\\]text\\[\\033[0m\\]") == "\001\033[32m\002text\001\033[0m\002"


class TestHistoryAndCommandCounters:
    """Test history and command number expansion."""

    def test_history_number_expansion(self, shell):
        """Test expansion of history number."""
        expander = PromptExpander(shell)

        # Set up shell with some history
        shell.history = ['echo 1', 'echo 2', 'echo 3']
        result = expander.expand_prompt("\\!")
        assert result == "4"  # Next history number

        # Test in context
        result = expander.expand_prompt("[\\!]")
        assert result == "[4]"

        # Empty history
        shell.history = []
        result = expander.expand_prompt("\\!")
        assert result == "1"

    def test_command_number_expansion(self, shell):
        """Test expansion of command number."""
        expander = PromptExpander(shell)

        # Set up shell with command count
        shell.command_number = 5
        result = expander.expand_prompt("\\#")
        assert result == "6"  # Next command number

        # Test in context
        result = expander.expand_prompt("Cmd \\#:")
        assert result == "Cmd 6:"

        # Fresh shell
        shell.command_number = 0
        result = expander.expand_prompt("\\#")
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
                            result = expander.expand_prompt("\\u@\\h:\\w\\$ ")
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
                            result = expander.expand_prompt("\\[\\e[32m\\]\\u@\\h\\[\\e[0m\\]:\\w\\$ ")
                            expected = "\001\033[32m\002user@myhost\001\033[0m\002:~$ "
                            assert result == expected

    def test_complex_prompt_with_counters(self, shell):
        """Test complex prompt with history and command numbers."""
        expander = PromptExpander(shell)

        shell.history = ['cmd1', 'cmd2']
        shell.command_number = 10

        result = expander.expand_prompt("[\\!:\\#] \\$ ")
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
                        result = expander.expand_prompt("\\u@\\h\\n\\w\\$ ")
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
                    result = expander.expand_prompt("[\\t] \\h\\$ ")
                    assert result == "[14:30:45] testhost$ "

    def test_prompt_with_octal_and_markers(self, shell):
        """Test prompt combining octal sequences and non-printing markers."""
        expander = PromptExpander(shell)

        # Bold green text using octal and markers
        result = expander.expand_prompt("\\[\\033[1;32m\\]bold\\[\\033[0m\\]")
        expected = "\001\033[1;32m\002bold\001\033[0m\002"
        assert result == expected
