"""In-process unit tests for CompletionEngine candidate generation and
word-boundary detection, plus the LineEditor tab-apply path.

All filesystem cases use tmp_path + monkeypatch.chdir, so the tests are
xdist-safe and never touch a terminal.  Tilde-specific escape_path
behavior is covered by tests/unit/test_tab_completion_tilde.py and is
not duplicated here.
"""

import pytest

from psh.interactive.line_editor import LineEditor
from psh.interactive.tab_completion import CompletionEngine


@pytest.fixture
def engine():
    return CompletionEngine()


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """A cwd populated with a known file layout."""
    (tmp_path / "foo.txt").write_text("x")
    (tmp_path / "foobar.txt").write_text("x")
    (tmp_path / "frob").write_text("x")
    (tmp_path / ".hidden").write_text("x")
    (tmp_path / "baz").mkdir()
    (tmp_path / "baz" / "inner.txt").write_text("x")
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestPathCompletions:
    # get_completions returns (word_start, completions); tests unpack and
    # ignore word_start (its own contract is covered by TestGetCompletionsContract).
    def test_partial_filename_multiple_matches(self, engine, workdir):
        _, results = engine.get_completions("cat foo", 7)
        assert sorted(results) == ["foo.txt", "foobar.txt"]

    def test_unique_completion(self, engine, workdir):
        _, results = engine.get_completions("cat foob", 8)
        assert results == ["foobar.txt"]

    def test_directory_gets_trailing_slash(self, engine, workdir):
        _, results = engine.get_completions("ls ba", 5)
        assert results == ["baz/"]

    def test_hidden_files_excluded_with_empty_prefix(self, engine, workdir):
        _, results = engine.get_completions("ls ", 3)
        assert ".hidden" not in results
        assert "foo.txt" in results

    def test_hidden_files_included_with_dot_prefix(self, engine, workdir):
        _, results = engine.get_completions("ls .h", 5)
        assert results == [".hidden"]

    def test_completion_inside_subdirectory_keeps_dir_part(self, engine, workdir):
        _, results = engine.get_completions("cat baz/in", 10)
        assert results == ["baz/inner.txt"]

    def test_nonexistent_directory_yields_nothing(self, engine, workdir):
        assert engine.get_completions("cat nosuch/x", 12)[1] == []

    def test_no_matches_yields_nothing(self, engine, workdir):
        assert engine.get_completions("cat zzz", 7)[1] == []

    def test_command_position_completes_paths_only(self, engine, workdir):
        # Documents current behavior: the engine is purely path-based;
        # there is no builtin/PATH command completion at word 0.
        _, results = engine.get_completions("fo", 2)
        assert sorted(results) == ["foo.txt", "foobar.txt"]


class TestGetCompletionsContract:
    """get_completions returns the word boundary alongside the candidates so
    the caller reuses it (one find_word_start scan per Tab press)."""

    def test_returns_word_start_and_completions(self, engine, workdir):
        result = engine.get_completions("cat foob", 8)
        assert isinstance(result, tuple) and len(result) == 2
        word_start, completions = result
        # "cat foob": the word being completed starts at index 4.
        assert word_start == 4
        assert completions == ["foobar.txt"]

    def test_word_start_matches_find_word_start(self, engine):
        # The returned boundary is exactly find_word_start's answer.
        line, cursor = "echo a; cat fo", 14
        word_start, _ = engine.get_completions(line, cursor)
        assert word_start == engine.find_word_start(line, cursor)


class TestFindWordStart:
    def test_single_word(self, engine):
        assert engine.find_word_start("echo", 4) == 0

    def test_word_after_space(self, engine):
        assert engine.find_word_start("cat foo", 7) == 4

    @pytest.mark.parametrize("sep", [';', '|', '&', '<', '>'])
    def test_shell_operators_break_words(self, engine, sep):
        line = f"a{sep}foo"
        assert engine.find_word_start(line, len(line)) == 2

    def test_double_quoted_word_includes_spaces(self, engine):
        line = 'cat "my file'
        # Word starts just after the opening quote, spanning the space.
        assert engine.find_word_start(line, len(line)) == 5

    def test_single_quoted_word_includes_spaces(self, engine):
        line = "cat 'my file"
        assert engine.find_word_start(line, len(line)) == 5

    def test_closed_quotes_do_not_extend_word(self, engine):
        line = '"a b" foo'
        assert engine.find_word_start(line, len(line)) == 6

    def test_cursor_at_start(self, engine):
        assert engine.find_word_start("echo", 0) == 0


class TestFindCommonPrefix:
    def test_empty_candidates(self, engine):
        assert engine.find_common_prefix([]) == ""

    def test_single_candidate(self, engine):
        assert engine.find_common_prefix(["only"]) == "only"

    def test_common_prefix(self, engine):
        assert engine.find_common_prefix(["foo.txt", "foobar.txt"]) == "foo"

    def test_no_common_prefix(self, engine):
        assert engine.find_common_prefix(["abc", "xyz"]) == ""


class TestEditorTabApply:
    """LineEditor._handle_tab / _apply_completion against real files."""

    def _editor_with(self, text):
        ed = LineEditor(history=[])
        ed.edit_buffer.chars = list(text)
        ed.edit_buffer.cursor = len(text)
        return ed

    def test_unique_completion_applied(self, workdir):
        # bash finishes a UNIQUE non-directory match with a trailing space
        # (R18 M-i5; probe_mi5_trailspace.py), so the cursor is ready for the
        # next word.
        ed = self._editor_with("cat foob")
        ed._handle_tab()
        assert ''.join(ed.edit_buffer.chars) == "cat foobar.txt "
        assert ed.edit_buffer.cursor == len("cat foobar.txt ")

    def test_unique_directory_keeps_slash_without_space(self, workdir):
        # bash: a unique DIRECTORY match keeps its trailing '/' with NO
        # space, so you can keep descending (R18 M-i5).
        ed = self._editor_with("ls ba")
        ed._handle_tab()
        assert ''.join(ed.edit_buffer.chars) == "ls baz/"
        assert ed.edit_buffer.cursor == len("ls baz/")

    def test_multiple_matches_expand_to_common_prefix(self, workdir):
        ed = self._editor_with("cat f")
        ed._handle_tab()  # foo.txt / foobar.txt / frob → common prefix "f"... none beyond
        # "f" is already the common prefix of foo*, frob → falls back to
        # showing candidates; buffer must be unchanged.
        assert ''.join(ed.edit_buffer.chars).startswith("cat f")

    def test_prefix_extension(self, workdir):
        ed = self._editor_with("cat fo")
        ed._handle_tab()  # foo.txt / foobar.txt share "foo"
        assert ''.join(ed.edit_buffer.chars) == "cat foo"
        assert ed.edit_buffer.cursor == len("cat foo")

    def test_completion_with_space_is_escaped(self, workdir):
        # Unique file: escaped AND finished with a trailing space (bash).
        (workdir / "my file.txt").write_text("x")
        ed = self._editor_with("cat my")
        ed._handle_tab()
        assert ''.join(ed.edit_buffer.chars) == "cat my\\ file.txt "

    def test_no_completions_leave_buffer_unchanged(self, workdir):
        ed = self._editor_with("cat zzz")
        ed._handle_tab()
        assert ''.join(ed.edit_buffer.chars) == "cat zzz"
