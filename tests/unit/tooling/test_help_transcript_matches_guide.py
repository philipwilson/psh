"""The user guide's option list is the REAL `psh --help` output, not a copy.

R15-B-H. `docs/user_guide/02_getting_started.md` introduces its fenced block
with "Here's a complete list of PSH command-line options" — a claim about the
program, made in prose, maintained by hand. It had drifted: the block was
missing `--posix`, `--`, `--force-interactive`, the `-s`/`-i` wording the
program actually prints, and the mutual-exclusion line that `--help` gained
when the analysis modes became exclusive.

Refreshing it once only resets the clock. A transcript that claims to BE the
program's output should be checked against the program, which is what this
does — the help-oracle pattern (reappraisal #19) applied to a user-guide
block rather than to builtin help.

If this fails, run `python -m psh --help` and paste the output into that
fenced block verbatim. Do not edit the expectation here.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
GUIDE = REPO / "docs/user_guide/02_getting_started.md"
INTRO = "Here's a complete list of PSH command-line options"


def _guide_block() -> str:
    lines = GUIDE.read_text().split("\n")
    intro = next(i for i, line in enumerate(lines) if INTRO in line)
    opening = next(i for i in range(intro, len(lines)) if lines[i] == "```")
    closing = next(i for i in range(opening + 1, len(lines)) if lines[i] == "```")
    return "\n".join(lines[opening + 1:closing])


def _live_help() -> str:
    proc = subprocess.run([sys.executable, "-m", "psh", "--help"],
                          capture_output=True, text=True, cwd=str(REPO))
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.rstrip("\n")


def test_the_guide_block_is_the_programs_own_help_output():
    assert _guide_block() == _live_help(), (
        "docs/user_guide/02_getting_started.md's option list no longer matches "
        "`psh --help`. Paste the current output into that fenced block."
    )


def test_the_comparison_is_not_vacuous():
    """MUTATION PROOF: both sides must be substantial and really compared, so
    a block that silently became empty cannot pass by matching nothing."""
    block = _guide_block()
    assert len(block.splitlines()) > 30, len(block.splitlines())
    assert "--validate" in block and "--posix" in block
    assert block != _live_help() + "\n"        # the rstrip is load-bearing
