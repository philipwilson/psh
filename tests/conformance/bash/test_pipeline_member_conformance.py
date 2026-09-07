"""Conformance: function / eval / source bodies as pipeline members (C001).

A pipeline member may execve() in place only for its OWN top-level simple
command. A function body, ``eval`` text or a sourced file dispatches after
that one-shot token is spent, so its first external command forks and
everything after it still runs — and the member's exit status is its LAST
command's::

    f(){ /bin/echo A; echo B; }; f | cat                   # A B, not just A
    set -o pipefail; f(){ /bin/echo A; false; }; f | cat   # rc 1, not 0

Owner: ``psh/executor/context.py#ExecutionContext.for_pipeline_member``.
The companion module ``test_compound_in_pipeline_conformance.py`` covers the
compound-member half; the three-input-mode matrix and the ``--debug-exec``
direction pins live in
``tests/integration/pipeline/test_pipeline_member_one_shot.py``.
"""

from conformance_framework import ConformanceTest


class TestFunctionBodyAsPipelineMember(ConformanceTest):
    """A function member runs its whole body, like bash."""

    def test_external_first_then_builtin(self):
        self.assert_identical_behavior(
            'f(){ /bin/echo A; echo B; }; f | cat')

    def test_external_in_the_middle(self):
        self.assert_identical_behavior(
            'f(){ echo A; /bin/echo B; echo C; }; f | cat')

    def test_nested_function_call(self):
        self.assert_identical_behavior(
            'g(){ /bin/echo G; echo g2; }; f(){ g; echo F; }; f | cat')

    def test_failing_external_first(self):
        # /usr/bin/false, not /bin/false: macOS has no /bin/false.
        self.assert_identical_behavior(
            'f(){ /usr/bin/false; echo B; }; f | cat')

    def test_member_status_is_last_command(self):
        self.assert_identical_behavior(
            'f(){ /bin/echo A; /usr/bin/false; }; f | cat; echo st=${PIPESTATUS[0]}')

    def test_pipefail_takes_the_members_real_status(self):
        self.assert_identical_behavior(
            'set -o pipefail; f(){ /bin/echo A; false; }; f | cat; echo rc=$?')

    def test_reading_member_sees_every_line(self):
        self.assert_identical_behavior(
            'f(){ /bin/echo A; echo B; }; f | while read l; do echo "got:$l"; done')

    def test_function_in_middle_stage_of_three(self):
        self.assert_identical_behavior(
            'f(){ /bin/echo A; echo B; }; echo seed | f | cat')

    def test_plain_external_member_unchanged(self):
        # The exec-in-place optimization is KEPT for a simple external member.
        self.assert_identical_behavior('/bin/echo A | cat')


class TestEvalAndSourceAsPipelineMember(ConformanceTest):
    """`eval` text and a sourced file as members run past their first
    external command."""

    def test_eval_member(self):
        self.assert_identical_behavior('echo x | eval "/bin/echo A; echo B"')

    def test_eval_member_status_is_last_command(self):
        self.assert_identical_behavior(
            'set -o pipefail; echo x | eval "/bin/echo A; false"; echo rc=$?')

    def test_source_member(self, tmp_path):
        script = tmp_path / "sourced.sh"
        script.write_text("/bin/echo A; echo B\n")
        self.assert_identical_behavior(f'echo x | . {script}')

    def test_source_member_with_dot_and_arguments(self, tmp_path):
        script = tmp_path / "sourced_args.sh"
        script.write_text('/bin/echo "$1"; echo "$2"\n')
        self.assert_identical_behavior(f'echo x | . {script} one two')

    def test_source_member_via_source_keyword(self, tmp_path):
        script = tmp_path / "sourced_kw.sh"
        script.write_text("/bin/echo A; echo B; echo C\n")
        self.assert_identical_behavior(f'echo x | source {script}')

