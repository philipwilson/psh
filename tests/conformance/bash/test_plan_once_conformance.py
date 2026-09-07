"""Conformance: a redirect target is expanded exactly once (C031).

Planning a redirect runs its target's command substitutions and forks its
process substitutions, so "how many times was this redirect resolved" is
observable behavior.  For an in-process builtin with a redirect on fd >= 3 psh
resolved it TWICE: ``setup_builtin_redirections`` planned the operation, threw
the plan away, and let the fd-level fallback rebuild a program and plan again.

Reproducing command:

    echo hi 3> "$(echo x >> ctr; echo o3)"; wc -l < ctr
    # bash: 1     psh (before): 2

The harm was not only duplicated side effects.  Only the SECOND resolution was
what the fd pointed at, while the noclobber check had run against the FIRST, so
``set -C`` could refuse a name the redirect was never going to open and create
nothing where bash creates a file:

    echo 0 > c; echo OLD > f2; set -C
    echo hi 3> "$(n=$(cat c); n=$((n+1)); echo $n >| c; echo f$n)"; ls
    # bash: c f1 f2      psh (before): "f2: cannot overwrite existing file", c f2

Every row observes the ACTUAL target -- the counter file's line count, the
bytes in the file that was opened, the value read back through the fd -- never
a bare exit status.  Diagnostics are routed to /dev/null or observed through
``cat``/``ls`` because a shell's error prefix names the shell.

Controls pin the paths that were already correct (compound, function, external,
fd 1, ``exec``, named fd): losing them would mean the fix had merely moved the
second expansion somewhere else.  Owner:
``psh/io_redirect/manager.py#_builtin_redirect_fd_level``.  Verified against
bash 5.3.15.
"""

from conformance_framework import ConformanceTest

# A target whose expansion appends one line to `ctr` and names the file to open.
CTR = '"$(echo x >> ctr; echo o3)"'
# A target that CHANGES on every expansion: reads a counter out of `c`,
# increments it, writes it back, and names `f<n>`.  The first expansion names
# f1, the second f2 -- so the name that is opened identifies which expansion
# the shell actually used.
INCR = '"$(n=$(cat c); n=$((n+1)); echo $n > c; echo f$n)"'
INCR_CLOBBER = '"$(n=$(cat c); n=$((n+1)); echo $n >| c; echo f$n)"'


class TestBuiltinFdThreeExpandsTargetOnce(ConformanceTest):
    """An in-process builtin with a redirect on fd >= 3 (the defect)."""

    def test_echo_output_redirect(self):
        self.assert_identical_behavior(
            f'echo hi 3> {CTR}; wc -l < ctr')

    def test_echo_append_redirect(self):
        self.assert_identical_behavior(
            f'echo hi 3>> {CTR}; wc -l < ctr')

    def test_colon_builtin_high_fd(self):
        self.assert_identical_behavior(
            ': 9> "$(echo x >> ctr; echo o9)"; wc -l < ctr')

    def test_printf_builtin(self):
        self.assert_identical_behavior(
            'printf "hi\\n" 4> "$(echo x >> ctr; echo o4)"; wc -l < ctr')

    def test_read_write_open(self):
        self.assert_identical_behavior(
            f'echo hi 3<> {CTR}; wc -l < ctr')

    def test_input_redirect_and_the_bytes_read_through_it(self):
        self.assert_identical_behavior(
            'printf "L\\n" > src; '
            'read -u 3 v 3< "$(echo x >> ctr; echo src)"; '
            'echo "v=$v $(wc -l < ctr)"')

    def test_two_redirects_expand_once_each_in_source_order(self):
        self.assert_identical_behavior(
            'echo hi 3> "$(echo a >> ctr; echo o3)" '
            '4> "$(echo b >> ctr; echo o4)"; cat ctr')

    def test_nested_eval_expands_each_operation_once(self):
        self.assert_identical_behavior(
            'eval "echo inner 3> \\"\\$(echo x >> ctr; echo i3)\\"" '
            f'3> "$(echo y >> ctr; echo o3)"; cat ctr')

    def test_the_fd_points_at_the_single_expansion(self):
        self.assert_identical_behavior(
            f'eval "echo payload >&3" 3> {CTR}; wc -l < ctr; cat o3')


class TestProcessSubstitutionTargetForksOnce(ConformanceTest):
    """A process substitution as a redirect target forks exactly one child.

    Each row READS fd 3, which synchronizes on the child's own output; the
    child appends to the counter before writing it.  Sampling the counter
    without reading fd 3 races the child in bash too, so it would not be a
    conformance question.
    """

    def test_read_from_process_substitution(self):
        self.assert_identical_behavior(
            'read -u 3 v 3< <(echo x >> ctr; echo data); '
            'echo "v=$v $(wc -l < ctr)"')

    def test_mapfile_from_process_substitution(self):
        self.assert_identical_behavior(
            'mapfile -t -u 3 arr 3< <(echo x >> ctr; echo L1; echo L2); '
            'echo "${arr[0]}-${arr[1]} $(wc -l < ctr)"')


class TestNoclobberChecksTheNameItOpens(ConformanceTest):
    """The noclobber check and the open must see the SAME expansion.

    With a target that changes on every expansion, which file exists afterwards
    identifies which expansion the shell used.
    """

    def test_the_first_expansion_is_the_file_created(self):
        self.assert_identical_behavior(
            f'echo 0 > c; echo hi 3> {INCR}; ls')

    def test_second_name_pre_existing_does_not_block_the_first(self):
        self.assert_identical_behavior(
            'echo 0 > c; echo OLD > f2; set -C; '
            f'{{ echo hi 3> {INCR_CLOBBER}; }} 2>/dev/null; echo "rc=$?"; '
            'ls; cat f2')

    def test_the_checked_name_is_the_one_refused(self):
        # The refusal is a SETUP failure, so `2>/dev/null` on the same command
        # is applied too late to catch it -- the wrapping group is what routes
        # the shell-named diagnostic away.
        self.assert_identical_behavior(
            'echo 0 > c; echo OLD > f1; set -C; '
            f'{{ echo hi 3> {INCR_CLOBBER}; }} 2>/dev/null; echo "rc=$?"; '
            'ls; cat f1 c')

    def test_noclobber_still_refuses_an_existing_target(self):
        # Control: the fix must not have disabled the check.
        self.assert_identical_behavior(
            'echo OLD > t; set -C; { echo hi 3> t; } 2>/dev/null; '
            'echo "rc=$?"; cat t')

    def test_append_is_not_subject_to_noclobber(self):
        self.assert_identical_behavior(
            'echo OLD > t; set -C; eval "echo new >&3" 3>> t; echo "rc=$?"; cat t')


class TestDupAndCloseOnFdThree(ConformanceTest):
    """Dups, moves and closes on fd >= 3 keep their fd-level meaning.

    The move split (`n>&m-` = dup then close the source) derives both halves
    from the already-resolved plan; these rows pin that neither half changed.
    """

    def test_dup_from_stdout(self):
        self.assert_identical_behavior('eval "echo d >&3" 3>&1')

    def test_move_dups_then_closes_the_source(self):
        self.assert_identical_behavior(
            'eval "echo v4 >&4" 3> t3 4>&3-; cat t3')

    def test_move_leaves_the_source_closed(self):
        self.assert_identical_behavior(
            '{ eval "echo v3 >&3" 3> t3 4>&3-; } 2>/dev/null; '
            'echo "rc=$?"; cat t3')

    def test_self_move_keeps_the_fd_open(self):
        self.assert_identical_behavior(
            'eval "echo s >&3" 3> t3 3>&3-; cat t3')

    def test_close_of_a_high_fd(self):
        self.assert_identical_behavior(
            '{ exec 3> t3; eval "echo c >&3" 3>&-; } 2>/dev/null; '
            'echo "rc=$?"; exec 3>&-; cat t3')


class TestHereDocumentsOnHighFds(ConformanceTest):
    """A here-document body on fd >= 3 is materialized once and readable."""

    def test_heredoc_on_fd_three(self):
        self.assert_identical_behavior(
            'read -u 3 v 3<<EOF\nhello\nEOF\necho "v=$v"')

    def test_here_string_on_fd_three(self):
        self.assert_identical_behavior(
            'read -u 3 v 3<<< "here string"; echo "v=$v"')


class TestPathsThatAlreadyExpandedOnce(ConformanceTest):
    """Controls: every other application path, unchanged by the fix."""

    def test_brace_group(self):
        self.assert_identical_behavior(
            f'{{ echo hi; }} 3> {CTR}; wc -l < ctr')

    def test_function(self):
        self.assert_identical_behavior(
            f'g() {{ echo hi; }}; g 3> {CTR}; wc -l < ctr')

    def test_external_command(self):
        self.assert_identical_behavior(
            f'/bin/echo hi 3> {CTR}; wc -l < ctr')

    def test_stdout_stream_path(self):
        self.assert_identical_behavior(
            'echo hi > "$(echo x >> ctr; echo o1)"; wc -l < ctr; cat o1')

    def test_stderr_stream_path(self):
        self.assert_identical_behavior(
            'eval "echo e >&2" 2> "$(echo x >> ctr; echo o2)"; '
            'wc -l < ctr; cat o2')

    def test_combined_redirect(self):
        self.assert_identical_behavior(
            'eval "echo o; echo e >&2" &> "$(echo x >> ctr; echo ob)"; '
            'wc -l < ctr; cat ob')

    def test_permanent_exec_redirect(self):
        self.assert_identical_behavior(
            f'exec 3> {CTR}; echo permanent >&3; exec 3>&-; '
            'wc -l < ctr; cat o3')

    def test_named_fd_redirect(self):
        self.assert_identical_behavior(
            'echo hi {v}> "$(echo x >> ctr; echo ov)"; wc -l < ctr')

    def test_pipeline_member(self):
        self.assert_identical_behavior(
            f'echo hi 3> {CTR} | cat; wc -l < ctr')

    def test_subshell(self):
        self.assert_identical_behavior(
            f'( echo hi ) 3> {CTR}; wc -l < ctr')
