"""Test tab completion handling of tilde expansion."""

from psh.interactive.tab_completion import CompletionEngine


class TestTildeCompletion:
    """Test that tab completion handles tilde correctly."""

    def test_escape_path_preserves_leading_tilde(self):
        """Test that leading tilde is not escaped."""
        engine = CompletionEngine()

        # Leading tilde should not be escaped
        assert engine.escape_path("~/Documents") == "~/Documents"
        assert engine.escape_path("~/src/psh") == "~/src/psh"
        assert engine.escape_path("~") == "~"
        assert engine.escape_path("~/") == "~/"

    def test_escape_path_with_spaces_and_tilde(self):
        """Test that spaces are escaped but leading tilde is preserved."""
        engine = CompletionEngine()

        # Spaces should be escaped, but not the leading tilde
        assert engine.escape_path("~/My Documents") == "~/My\\ Documents"
        assert engine.escape_path("~/dir with spaces/file.txt") == "~/dir\\ with\\ spaces/file.txt"

    def test_escape_path_tilde_not_at_start(self):
        """Test that tilde not at the start is treated normally."""
        engine = CompletionEngine()

        # Tilde in the middle has no special meaning, so no escaping needed
        assert engine.escape_path("/home/user/~notahome") == "/home/user/~notahome"
        assert engine.escape_path("file~backup.txt") == "file~backup.txt"
        assert engine.escape_path("some~dir/file") == "some~dir/file"

    def test_escape_path_other_special_chars(self):
        """Test that other special characters are still escaped."""
        engine = CompletionEngine()

        # Other special characters should still be escaped
        assert engine.escape_path("~/file$name") == "~/file\\$name"
        assert engine.escape_path("~/dir(with)parens") == "~/dir\\(with\\)parens"
        assert engine.escape_path("~/file name.txt") == "~/file\\ name.txt"
        assert engine.escape_path('~/file"with"quotes') == '~/file\\"with\\"quotes'
