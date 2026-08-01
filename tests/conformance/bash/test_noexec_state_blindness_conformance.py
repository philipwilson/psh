"""`psh -n` matches `bash -n`, including where both are state-BLIND.

The user guide (17_differences_from_bash.md, "Script Analysis Tools") tells
readers that psh has two static checks answering different questions:

    "The POSIX `-n` flag is a different tool: it is Bash's syntax check, and
     like `bash -n` it does not execute a script's `shopt` commands — so
     `psh -n` and `bash -n` agree with each other rather than with
     `--validate`."

The repo principle is that a user-guide bash-conformance claim is proven in
tests/conformance/, so this module proves it. `--validate`'s deliberately
DIFFERENT answer is psh-specific and pinned separately in
tests/system/test_analysis_state_aware.py::TestTwoStaticSurfaces — a psh
extension has no place in a conformance comparison.

Why the claim is not self-evident: `-n` parses without executing, so a `shopt
-s extglob` on line 1 has not run when line 2 is parsed, and BOTH shells
therefore report a syntax error for a script that runs fine. That is the
agreement being pinned — a shared blind spot, not a shared success.
"""

from conformance_framework import ConformanceTest

# extglob enabled on one line, used on the next: runs clean in both shells,
# and is a syntax error to both shells' `-n`.
STATE_CHANGING = 'shopt -s extglob\ncase ab in +(a)b) echo MATCH;; esac'

# The control: no option change, so `-n` has nothing to be blind to.
PLAIN = 'x=1\nif [ "$x" = 1 ]; then\n  echo one\nfi'

# A genuine syntax error, so the agreement is not an artifact of `-n`
# accepting everything.
BROKEN = 'echo fine\nif'


class TestNoexecStateBlindnessConformance(ConformanceTest):
    """`-n` is bash's syntax check in psh too, blind spot included."""

    def _compare_noexec(self, script: str) -> None:
        """Run the SAME script through `psh -n` and `bash -n` and require
        identical status."""
        psh = self.framework.run_in_shell(
            script, self.framework.psh_path + ['-n'])
        bash = self.framework.run_in_shell(
            script, self.framework.bash_path + ['-n'])
        assert psh.exit_code == bash.exit_code, (
            f"psh -n and bash -n disagree on:\n{script}\n"
            f"psh: exit={psh.exit_code} stderr={psh.stderr!r}\n"
            f"bash: exit={bash.exit_code} stderr={bash.stderr!r}")

    def test_noexec_is_blind_to_a_mid_script_shopt_like_bash(self):
        """The claim's substance: neither `-n` executes the `shopt`, so both
        reject a script that both shells RUN successfully."""
        self._compare_noexec(STATE_CHANGING)

    def test_that_script_actually_runs_in_both_shells(self):
        """The control the claim rests on — if the script did not run clean,
        the agreement above would be uninteresting."""
        self.assert_identical_behavior(STATE_CHANGING)

    def test_noexec_agrees_on_a_script_with_no_option_change(self):
        self._compare_noexec(PLAIN)

    def test_noexec_agrees_on_a_genuine_syntax_error(self):
        """Proves the agreement is not `-n` waving everything through."""
        self._compare_noexec(BROKEN)
