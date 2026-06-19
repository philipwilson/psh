"""The `examples/` scripts must parse, run, and analyze as documented.

The project README and `examples/README.md` point readers at these scripts
and at specific analysis-tool output. This test keeps those promises honest:
every example parses, the safe ones run to a clean exit, and the metrics the
README prints for `fibonacci.sh` actually match `--metrics` output.

All checks run psh in a subprocess (no shared-cwd writes), so they are
xdist-safe. `security_demo.sh` is intentionally destructive (it would touch
the filesystem); it is parsed and statically analyzed but never executed.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = PROJECT_ROOT / "examples"

# Every example script, discovered from the tree.
ALL_EXAMPLES = sorted(p.name for p in EXAMPLES.glob("*.sh"))

# Scripts that are safe to actually execute (no filesystem mutation, no
# destructive commands). security_demo.sh is deliberately excluded.
SAFE_TO_RUN = {
    "fibonacci.sh",
    "shell_basics.sh",
    "control_structures.sh",
    "text_stats.sh",
}


def _run(*args, **kwargs):
    return subprocess.run(
        [sys.executable, "-m", "psh", *args],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=60, **kwargs
    )


def test_examples_directory_is_populated():
    """Guard against the directory vanishing or a rename breaking discovery."""
    assert ALL_EXAMPLES, "no examples/*.sh found"
    # The README and examples/README.md name these explicitly.
    for expected in ("fibonacci.sh", "shell_basics.sh", "security_demo.sh"):
        assert expected in ALL_EXAMPLES, f"missing example: {expected}"


@pytest.mark.parametrize("script", ALL_EXAMPLES)
def test_example_parses(script):
    """Every example parses cleanly (--validate exits 0 on valid syntax)."""
    result = _run("--validate", f"examples/{script}")
    assert result.returncode == 0, (
        f"examples/{script} failed to validate:\n{result.stdout}\n{result.stderr}"
    )


@pytest.mark.parametrize("script", sorted(SAFE_TO_RUN))
def test_safe_example_runs(script):
    """The non-destructive examples run to a clean exit with output."""
    args = [f"examples/{script}"]
    if script == "text_stats.sh":
        args.append("examples/shell_basics.sh")  # needs a file argument
    result = _run(*args)
    assert result.returncode == 0, (
        f"examples/{script} exited {result.returncode}:\n{result.stderr}"
    )
    assert result.stdout.strip(), f"examples/{script} produced no output"


def _parse_metrics(text):
    """Turn 'Label: 12' lines from the metrics report into a {label: int}."""
    out = {}
    for line in text.splitlines():
        m = re.match(r"\s*([A-Za-z][A-Za-z ]+?):\s+(\d+)\s*$", line)
        if m:
            out[m.group(1).strip()] = int(m.group(2))
    return out


def test_metrics_match_readme():
    """`--metrics examples/fibonacci.sh` must match the numbers in README.md.

    These are the values printed in the README's "Example Output" block; if
    fibonacci.sh changes, update both the README block and this test.
    """
    result = _run("--metrics", "examples/fibonacci.sh")
    assert result.returncode == 0, result.stderr
    m = _parse_metrics(result.stdout)
    assert m.get("Total Commands") == 18
    assert m.get("Unique Commands") == 8
    assert m.get("Functions Defined") == 2
    assert m.get("Loops") == 3
    assert m.get("Conditionals") == 1
    assert m.get("Cyclomatic Complexity") == 5
    assert m.get("Max Nesting Depth") == 2


def test_security_demo_is_flagged():
    """The deliberately-insecure demo must trip --security (non-zero exit)."""
    result = _run("--security", "examples/security_demo.sh")
    assert result.returncode != 0, "security_demo.sh should report issues"
    assert "eval" in result.stdout.lower(), (
        f"expected an eval finding:\n{result.stdout}"
    )
