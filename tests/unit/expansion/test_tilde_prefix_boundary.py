"""The tilde-prefix boundary rule (reappraisal #17 F2/F3).

bash delimits a leading tilde-prefix at the first unquoted '/' OR ':'
(TildeExpander.prefix_end) and expands it only when every character of
the tilde word (~ up to the first unquoted '/', or the whole word) is an
unquoted literal:

- F2 (under-expansion, fixed): ``echo ~:x`` expands to ``$HOME:x``; the
  same for ``~user:`` and dirstack ``~+:`` prefixes.
- F3 (over-expansion, fixed): a prefix running into a quoted part or an
  expansion stays literal (``echo ~"x"`` → ``~x``, ``echo ~$USER`` →
  ``~<user>``), as does one containing a backslash escape (``~\\:x``).

Operand contexts (${u:-~:y}, ${v#~:}, ${w/q/~:z}) consume the whole
tilde word verbatim on success — bash's tilde_find_word semantics.
All expectations bash-5.2-verified (tmp/probes-r17t2-startilde/).

Known documented divergence (deliberate): for a WORD like ``~:$X`` bash
5.2 expands the tilde and pastes the remaining parts verbatim ($X stays
unexpanded); psh keeps the tilde literal and expands $X normally.
"""


class TestColonTerminatesPrefix:
    """F2: ':' ends the tilde-prefix in leading-word position."""

    def test_home_colon(self, captured_shell):
        captured_shell.run_command('HOME=/h; echo ~:x')
        assert captured_shell.get_stdout() == "/h:x\n"

    def test_home_colon_tilde(self, captured_shell):
        # The post-':' tilde stays literal in a non-assignment word.
        captured_shell.run_command('HOME=/h; echo ~:~')
        assert captured_shell.get_stdout() == "/h:~\n"

    def test_trailing_colon(self, captured_shell):
        captured_shell.run_command('HOME=/h; echo ~:')
        assert captured_shell.get_stdout() == "/h:\n"

    def test_user_colon(self, captured_shell):
        import os
        import pwd
        user = pwd.getpwuid(os.getuid())
        captured_shell.run_command(f'echo ~{user.pw_name}:x')
        assert captured_shell.get_stdout() == f"{user.pw_dir}:x\n"

    def test_unknown_user_colon_stays_literal(self, captured_shell):
        captured_shell.run_command('echo ~nosuchuserxyz:x')
        assert captured_shell.get_stdout() == "~nosuchuserxyz:x\n"

    def test_dirstack_pwd_colon(self, captured_shell):
        captured_shell.run_command('cd /tmp; echo ~+:x')
        assert captured_shell.get_stdout() == "/tmp:x\n"

    def test_non_leading_tilde_after_colon_literal(self, captured_shell):
        captured_shell.run_command('echo a:~:b')
        assert captured_shell.get_stdout() == "a:~:b\n"

    def test_double_quoted_no_expansion(self, captured_shell):
        captured_shell.run_command('echo "~:x"')
        assert captured_shell.get_stdout() == "~:x\n"


class TestPrefixIntoQuotedOrExpansionStaysLiteral:
    """F3: the tilde word must be wholly unquoted literal."""

    def test_quoted_suffix(self, captured_shell):
        captured_shell.run_command('echo ~"x"')
        assert captured_shell.get_stdout() == "~x\n"

    def test_empty_quotes(self, captured_shell):
        captured_shell.run_command('echo ~""')
        assert captured_shell.get_stdout() == "~\n"

    def test_single_quoted_suffix(self, captured_shell):
        captured_shell.run_command("echo ~'x'")
        assert captured_shell.get_stdout() == "~x\n"

    def test_quoted_valid_username(self, captured_shell):
        captured_shell.run_command('echo ~"root"')
        assert captured_shell.get_stdout() == "~root\n"

    def test_expansion_suffix(self, captured_shell):
        captured_shell.run_command('X=u; echo ~$X')
        assert captured_shell.get_stdout() == "~u\n"

    def test_expansion_suffix_with_path(self, captured_shell):
        captured_shell.run_command('X=u; echo ~$X/p')
        assert captured_shell.get_stdout() == "~u/p\n"

    def test_dirstack_quoted_suffix(self, captured_shell):
        captured_shell.run_command('cd /tmp; echo ~+"x"')
        assert captured_shell.get_stdout() == "~+x\n"

    def test_colon_bounded_then_quoted_suppressed(self, captured_shell):
        # No '/' in the literal + parts follow → whole tilde word is not
        # unquoted literal → no expansion (bash: ~:"x" → ~:x).
        captured_shell.run_command('echo ~:"x"')
        assert captured_shell.get_stdout() == "~:x\n"

    def test_slash_bounded_then_quoted_expands(self, captured_shell):
        # A '/' bounds the tilde word inside the literal, so following
        # parts are irrelevant.
        captured_shell.run_command('HOME=/h; echo ~/"x" ~/x"y"')
        assert captured_shell.get_stdout() == "/h/x /h/xy\n"

    def test_colon_then_slash_before_quoted_expands(self, captured_shell):
        captured_shell.run_command('HOME=/h; echo ~:x/"q"')
        assert captured_shell.get_stdout() == "/h:x/q\n"

    def test_escaped_colon_literal(self, captured_shell):
        captured_shell.run_command(r'echo ~\:x')
        assert captured_shell.get_stdout() == "~:x\n"

    def test_escaped_slash_literal(self, captured_shell):
        captured_shell.run_command(r'echo ~\/x')
        assert captured_shell.get_stdout() == "~/x\n"

    def test_escape_in_username_literal(self, captured_shell):
        captured_shell.run_command(r'echo ~ro\ot')
        assert captured_shell.get_stdout() == "~root\n"

    def test_escaped_tilde_never_expands(self, captured_shell):
        captured_shell.run_command(r'echo \~x \~')
        assert captured_shell.get_stdout() == "~x ~\n"

    def test_escape_after_slash_still_expands(self, captured_shell):
        captured_shell.run_command(r'HOME=/h; echo ~/a\ b')
        assert captured_shell.get_stdout() == "/h/a b\n"


class TestAssignmentValueControls:
    """The assignment-value path (colon-split first) must be unchanged."""

    def test_both_sides_of_colon(self, captured_shell):
        captured_shell.run_command('HOME=/h; a=~:~; echo "$a"')
        assert captured_shell.get_stdout() == "/h:/h\n"

    def test_path_like_value(self, captured_shell):
        captured_shell.run_command('HOME=/h; a=~/x:~/y; echo "$a"')
        assert captured_shell.get_stdout() == "/h/x:/h/y\n"

    def test_mid_value_segment(self, captured_shell):
        captured_shell.run_command('HOME=/h; a=x:~:y; echo "$a"')
        assert captured_shell.get_stdout() == "x:/h:y\n"

    def test_value_prefix_into_quoted_stays_literal(self, captured_shell):
        captured_shell.run_command('a=~"x"; echo "$a"')
        assert captured_shell.get_stdout() == "~x\n"

    def test_value_slash_bounded_before_quoted_expands(self, captured_shell):
        captured_shell.run_command('HOME=/h; a=~/"x"; echo "$a"')
        assert captured_shell.get_stdout() == "/h/x\n"

    def test_declaration_builtin_value(self, captured_shell):
        captured_shell.run_command('HOME=/h; declare b=~:~; echo "$b"')
        assert captured_shell.get_stdout() == "/h:/h\n"

    def test_assignment_shaped_argument(self, captured_shell):
        captured_shell.run_command('HOME=/h; echo x=~:~')
        assert captured_shell.get_stdout() == "x=/h:/h\n"


class TestOperandTildeWord:
    """Operand contexts: the tilde word (to the first '/') expands as a
    unit and its remainder is consumed verbatim (bash tilde_find_word)."""

    def test_value_operand_colon(self, captured_shell):
        captured_shell.run_command('HOME=/h; echo ${u:-~:y}')
        assert captured_shell.get_stdout() == "/h:y\n"

    def test_value_operand_slash(self, captured_shell):
        captured_shell.run_command('HOME=/h; echo ${u:-~/y}')
        assert captured_shell.get_stdout() == "/h/y\n"

    def test_value_operand_rest_verbatim(self, captured_shell):
        # bash 5.2: the tilde word runs to the first '/', and on success
        # its remainder — including $X — is literal and protected.
        captured_shell.run_command(
            'HOME=/h; X=hello; set --; printf "[%s]" ${u:-~:$X}; echo')
        assert captured_shell.get_stdout() == "[/h:$X]\n"

    def test_value_operand_rest_unsplit(self, captured_shell):
        captured_shell.run_command(
            'HOME=/h; set --; printf "[%s]" ${u:-~:a b}; echo')
        assert captured_shell.get_stdout() == "[/h:a b]\n"

    def test_value_operand_quote_in_tilde_word_suppresses(self,
                                                          captured_shell):
        captured_shell.run_command("echo ${u:-~:'q'}")
        assert captured_shell.get_stdout() == "~:q\n"

    def test_value_operand_invalid_user_normal_walk(self, captured_shell):
        # ~$X: the '$' lands in the username position → expansion fails →
        # the operand walks normally ($X expands).
        captured_shell.run_command('X=hello; echo ${u:-~$X}')
        assert captured_shell.get_stdout() == "~hello\n"

    def test_pattern_operand_colon(self, captured_shell):
        captured_shell.run_command('HOME=/h; p=/h:q; echo "${p#~:}"')
        assert captured_shell.get_stdout() == "q\n"

    def test_pattern_operand_rest_glob_literal(self, captured_shell):
        # The verbatim remainder of the tilde word has no glob power.
        captured_shell.run_command('HOME=/h; v=/h:xyz; echo "${v#~:x*}"')
        assert captured_shell.get_stdout() == "/h:xyz\n"

    def test_replacement_operand_colon(self, captured_shell):
        captured_shell.run_command('HOME=/h; w=qX; echo "${w/q/~:z}"')
        assert captured_shell.get_stdout() == "/h:zX\n"

    def test_replacement_operand_rest_amp_literal(self, captured_shell):
        # '&' inside the consumed tilde word is literal, not the match.
        captured_shell.run_command('HOME=/h; w=qX; echo "${w/q/~:&}"')
        assert captured_shell.get_stdout() == "/h:&X\n"

    def test_replacement_operand_failed_tilde_amp_active(self,
                                                         captured_shell):
        captured_shell.run_command('w=qX; echo "${w/q/~&}"')
        assert captured_shell.get_stdout() == "~qX\n"


class TestPrefixEndHelper:
    """The shared boundary helper itself."""

    def test_prefix_end(self, captured_shell):
        pe = captured_shell.expansion_manager.tilde_expander.prefix_end
        assert pe('~') == 1
        assert pe('~user') == 5
        assert pe('~/x') == 1
        assert pe('~:x') == 1
        assert pe('~user/x') == 5
        assert pe('~user:x') == 5
        assert pe('~+:x') == 2
        assert pe('~a:b/c') == 2

    def test_word_context_divergence_documented(self, captured_shell):
        # DOCUMENTED divergence from bash 5.2 (see module docstring): for
        # the WORD ~:$X bash pastes "$X" verbatim after the expanded
        # tilde; psh keeps the tilde literal and expands $X normally.
        captured_shell.run_command('HOME=/h; X=hello; echo ~:$X')
        assert captured_shell.get_stdout() == "~:hello\n"
