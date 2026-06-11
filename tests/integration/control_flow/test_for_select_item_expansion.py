"""for/select item lists go through the canonical Word expansion engine.

Pins bash 5.2 semantics (every case probe-verified against bash 5.2.26):
items are expanded exactly like simple-command arguments — IFS splitting
of unquoted command substitutions and variables, quote suppression,
globbing (with nullglob / set -f), tilde expansion, empty-expansion
elision, and ``$@``/``${a[@]}`` field semantics.

Regression target: the legacy ControlFlowExecutor path split command
substitutions on whitespace only, ignoring IFS (``IFS=:; for i in
$(printf a:b)`` iterated once instead of twice), and never
tilde-expanded items.
"""

import subprocess
import sys


def run_psh(script, parser=None, input_text=None):
    cmd = [sys.executable, '-m', 'psh']
    if parser:
        cmd += ['--parser', parser]
    cmd += ['-c', script]
    return subprocess.run(cmd, capture_output=True, text=True,
                          input=input_text)


class TestForItemIFSSplitting:
    """IFS-aware splitting of unquoted expansions in item lists."""

    def test_command_sub_splits_on_ifs(self, captured_shell):
        captured_shell.run_command(
            'IFS=:; for i in $(printf a:b); do printf "<%s>" "$i"; done')
        assert captured_shell.get_stdout() == '<a><b>'

    def test_backtick_command_sub_splits_on_ifs(self, captured_shell):
        captured_shell.run_command(
            'IFS=:; for i in `printf a:b`; do printf "<%s>" "$i"; done')
        assert captured_shell.get_stdout() == '<a><b>'

    def test_variable_splits_on_ifs(self, captured_shell):
        captured_shell.run_command(
            'IFS=:; x=a:b; for i in $x; do printf "<%s>" "$i"; done')
        assert captured_shell.get_stdout() == '<a><b>'

    def test_variable_splits_on_default_ifs(self, captured_shell):
        captured_shell.run_command(
            'x="a b"; for i in $x; do printf "<%s>" "$i"; done')
        assert captured_shell.get_stdout() == '<a><b>'

    def test_composite_item_splits_joining_prefix(self, captured_shell):
        # pre$x with IFS=: and x=a:b → fields "prea", "b" (bash)
        captured_shell.run_command(
            'IFS=:; x=a:b; for i in pre$x; do printf "<%s>" "$i"; done')
        assert captured_shell.get_stdout() == '<prea><b>'

    def test_arithmetic_result_subject_to_ifs(self, captured_shell):
        # IFS=3 splits the arith result "3" into one empty field, while
        # the LITERAL x3y is never field-split (bash)
        captured_shell.run_command(
            'IFS=3; for i in $((1+2)) x3y; do printf "<%s>" "$i"; done')
        assert captured_shell.get_stdout() == '<><x3y>'

    def test_command_sub_default_ifs(self, captured_shell):
        captured_shell.run_command(
            'for i in $(echo a b); do printf "<%s>" "$i"; done')
        assert captured_shell.get_stdout() == '<a><b>'


class TestForQuotedItems:
    """Quoted items never split."""

    def test_quoted_variable_does_not_split(self, captured_shell):
        captured_shell.run_command(
            'x="a b"; for i in "$x"; do printf "<%s>" "$i"; done')
        assert captured_shell.get_stdout() == '<a b>'

    def test_quoted_command_sub_does_not_split(self, captured_shell):
        captured_shell.run_command(
            'for i in "$(echo a b)"; do printf "<%s>" "$i"; done')
        assert captured_shell.get_stdout() == '<a b>'

    def test_quoted_star_joins_params(self, captured_shell):
        captured_shell.run_command(
            'set -- "a b" c; for i in "$*"; do printf "<%s>" "$i"; done')
        assert captured_shell.get_stdout() == '<a b c>'


class TestForEmptyExpansions:
    """Empty unquoted expansions contribute zero items (bash)."""

    def test_empty_unquoted_variable_zero_iterations(self, captured_shell):
        captured_shell.run_command(
            'e=""; n=0; for i in $e; do n=$((n+1)); done; printf "n=%s" "$n"')
        assert captured_shell.get_stdout() == 'n=0'

    def test_unset_variable_zero_iterations(self, captured_shell):
        captured_shell.run_command(
            'n=0; for i in $__unset__; do n=$((n+1)); done; printf "n=%s" "$n"')
        assert captured_shell.get_stdout() == 'n=0'

    def test_empty_quoted_variable_one_iteration(self, captured_shell):
        captured_shell.run_command(
            'e=""; n=0; for i in "$e"; do n=$((n+1)); done; printf "n=%s" "$n"')
        assert captured_shell.get_stdout() == 'n=1'


class TestForPositionalAndArrayItems:
    """$@ / $* / ${a[@]} field semantics in item lists."""

    def test_unquoted_at_splits_each_param(self, captured_shell):
        captured_shell.run_command(
            'set -- "a b" c; for i in $@; do printf "<%s>" "$i"; done')
        assert captured_shell.get_stdout() == '<a><b><c>'

    def test_quoted_at_preserves_params(self, captured_shell):
        captured_shell.run_command(
            'set -- "a b" c; for i in "$@"; do printf "<%s>" "$i"; done')
        assert captured_shell.get_stdout() == '<a b><c>'

    def test_unquoted_star_splits_each_param(self, captured_shell):
        captured_shell.run_command(
            'set -- "a b" c; for i in $*; do printf "<%s>" "$i"; done')
        assert captured_shell.get_stdout() == '<a><b><c>'

    def test_for_without_in_uses_quoted_params(self, captured_shell):
        captured_shell.run_command(
            'f() { for i; do printf "<%s>" "$i"; done; }; f "x y" z')
        assert captured_shell.get_stdout() == '<x y><z>'

    def test_quoted_array_at_preserves_elements(self, captured_shell):
        captured_shell.run_command(
            'a=("x y" z); for i in "${a[@]}"; do printf "<%s>" "$i"; done')
        assert captured_shell.get_stdout() == '<x y><z>'

    def test_unquoted_array_at_splits_elements(self, captured_shell):
        captured_shell.run_command(
            'a=("x y" z); for i in ${a[@]}; do printf "<%s>" "$i"; done')
        assert captured_shell.get_stdout() == '<x><y><z>'


class TestForTildeAndBraceItems:
    """Tilde, brace, and assignment-shaped items."""

    def test_tilde_item_expands(self, captured_shell):
        captured_shell.run_command(
            'HOME=/h; for i in ~; do printf "<%s>" "$i"; done')
        assert captured_shell.get_stdout() == '</h>'

    def test_assignment_shaped_item_tilde_expands(self, captured_shell):
        # bash tilde-expands for-items shaped like assignments
        captured_shell.run_command(
            'HOME=/h; for i in P=~/x; do printf "<%s>" "$i"; done')
        assert captured_shell.get_stdout() == '<P=/h/x>'

    def test_brace_expansion_items(self, captured_shell):
        captured_shell.run_command(
            'for i in {1..3}; do printf "<%s>" "$i"; done')
        assert captured_shell.get_stdout() == '<1><2><3>'


class TestForGlobItems:
    """Pathname expansion of item words (nullglob, set -f, quoting)."""

    def test_glob_item_expands(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('touch a.txt b.txt')
        shell.run_command(
            'for f in *.txt; do printf "<%s>" "$f" >> out; done')
        with open('out') as f:
            assert f.read() == '<a.txt><b.txt>'

    def test_unmatched_glob_stays_literal(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command(
            'for f in *.nope; do printf "<%s>" "$f" >> out; done')
        with open('out') as f:
            assert f.read() == '<*.nope>'

    def test_nullglob_removes_unmatched_item(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('touch out')
        shell.run_command(
            'shopt -s nullglob; for f in *.nope; do printf "<%s>" "$f" >> out; done')
        with open('out') as f:
            assert f.read() == ''

    def test_noglob_disables_expansion(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('touch a.txt')
        shell.run_command(
            'set -f; for f in *.txt; do printf "<%s>" "$f" >> out; done')
        with open('out') as f:
            assert f.read() == '<*.txt>'

    def test_quoted_glob_stays_literal(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('touch a.txt')
        shell.run_command(
            'for f in "*.txt"; do printf "<%s>" "$f" >> out; done')
        with open('out') as f:
            assert f.read() == '<*.txt>'

    def test_glob_from_variable_expands(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('touch a.txt b.txt')
        shell.run_command(
            'x="*.txt"; for f in $x; do printf "<%s>" "$f" >> out; done')
        with open('out') as f:
            assert f.read() == '<a.txt><b.txt>'


class TestSelectItemExpansion:
    """select item lists use the same Word engine (driven via stdin)."""

    def test_select_items_split_on_ifs(self):
        result = run_psh(
            'IFS=:; select i in $(printf "a:b"); do '
            'printf "picked:%s" "$i"; break; done 2>/dev/null',
            input_text='1\n')
        assert result.stdout == 'picked:a'

    def test_select_quoted_item_not_split(self):
        result = run_psh(
            'x="p q"; select i in "$x" z; do '
            'printf "picked:%s" "$i"; break; done 2>/dev/null',
            input_text='2\n')
        assert result.stdout == 'picked:z'

    def test_select_basic_items(self):
        result = run_psh(
            'select i in a b; do printf "picked:%s" "$i"; break; '
            'done 2>/dev/null',
            input_text='1\n')
        assert result.stdout == 'picked:a'

    def test_select_without_in_uses_params(self):
        result = run_psh(
            'set -- m n; select i; do printf "picked:%s" "$i"; break; '
            'done 2>/dev/null',
            input_text='1\n')
        assert result.stdout == 'picked:m'


class TestCombinatorParserParity:
    """The experimental combinator parser builds the same item Words."""

    def test_combinator_command_sub_splits_on_ifs(self):
        result = run_psh(
            'IFS=:; for i in $(printf a:b); do printf "<%s>" "$i"; done',
            parser='combinator')
        assert result.stdout == '<a><b>'

    def test_combinator_composite_item_is_one_word(self):
        result = run_psh(
            'IFS=:; x=a:b; for i in pre$x; do printf "<%s>" "$i"; done',
            parser='combinator')
        assert result.stdout == '<prea><b>'

    def test_combinator_tilde_item_expands(self):
        result = run_psh(
            'HOME=/h; for i in ~; do printf "<%s>" "$i"; done',
            parser='combinator')
        assert result.stdout == '</h>'

    def test_combinator_quoted_item_not_split(self):
        result = run_psh(
            'x="a b"; for i in "$x"; do printf "<%s>" "$i"; done',
            parser='combinator')
        assert result.stdout == '<a b>'
