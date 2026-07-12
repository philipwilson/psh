"""Conformance: an explicit file-descriptor prefix on a heredoc/here-string.

bash accepts `cat 0<<EOF`, `cat 0<<-EOF`, `cat 0<<<word`, and materializes
the body on the prefixed fd (`5<<EOF`, `5<<<word`). psh used to raise a parse
error ("Expected file name") for any fd-prefixed heredoc/here-string because
the lexer attached the fd only to plain redirects (`N>`, `N<`), not to the
heredoc/here-string operators. Fixed by extending the lexer's fd-prefix
recognizer to `<<`/`<<-`/`<<<` and making the io_redirect materialization
honor `redirect.fd` (default 0). See fix/numbered-heredoc-herestring.

The fd-5 cases dup the prefixed fd back onto stdin in the SAME command
(`5<<<word <&5`) so they are observable through `cat`/`read` without a tty.
A bare `cat 5<<<word` is deliberately NOT pinned here: it reads the inherited
stdin (fd 0), which under pytest is not deterministic.
"""


from conformance_framework import ConformanceTest


class TestNumberedHeredocHerestring(ConformanceTest):
    """An fd prefix on <<, <<-, <<< parses and materializes like bash."""

    # --- fd 0 prefix is identical to no prefix ---

    def test_fd0_heredoc(self):
        self.assert_identical_behavior('cat 0<<EOF\nbody\nEOF')

    def test_fd0_heredoc_matches_plain(self):
        # 0<< and bare << behave identically.
        self.assert_identical_behavior('cat 0<<EOF\nbody\nEOF')
        self.assert_identical_behavior('cat <<EOF\nbody\nEOF')

    def test_fd0_heredoc_strip(self):
        self.assert_identical_behavior('cat 0<<-EOF\n\t\tindented\n\tEOF')

    def test_fd0_herestring(self):
        self.assert_identical_behavior('cat 0<<<word')

    # --- explicit non-stdin fd, made observable via <&N ---

    def test_fd5_herestring_dup_to_stdin(self):
        self.assert_identical_behavior('cat 5<<<word <&5')

    def test_fd5_heredoc_dup_to_stdin(self):
        self.assert_identical_behavior('cat 5<<EOF <&5\nhello fd5\nEOF')

    def test_fd5_heredoc_strip_dup_to_stdin(self):
        self.assert_identical_behavior('cat 5<<-EOF <&5\n\tstripped\n\tEOF')

    def test_multidigit_fd_heredoc(self):
        self.assert_identical_behavior('cat 10<<EOF <&10\nbigfd\nEOF')

    def test_exec_fd5_herestring_then_read(self):
        # exec materializes on fd 5 permanently; a later read consumes it.
        self.assert_identical_behavior(
            'exec 5<<<fromfd5\nread line <&5\necho "got: $line"')

    # --- semantics preserved with the prefix present ---

    def test_fd0_heredoc_expansion(self):
        self.assert_identical_behavior('x=VAL; cat 0<<EOF\n$x\nEOF')

    def test_fd0_heredoc_quoted_delimiter_no_expansion(self):
        self.assert_identical_behavior("x=VAL; cat 0<<'EOF'\n$x\nEOF")

    def test_fd0_heredoc_in_pipeline(self):
        self.assert_identical_behavior('cat 0<<EOF | tr a-z A-Z\nhello\nEOF')

    def test_multiple_fd0_heredocs(self):
        self.assert_identical_behavior(
            'cat 0<<A\nfirst\nA\ncat 0<<B\nsecond\nB')

    # --- read builtin honors the fd prefix ---

    def test_read_builtin_fd0_herestring(self):
        self.assert_identical_behavior('read line 0<<<hello; echo "[$line]"')

    def test_read_builtin_fd5_herestring_dup(self):
        self.assert_identical_behavior(
            'read line 5<<<viafd5 <&5; echo "[$line]"')
