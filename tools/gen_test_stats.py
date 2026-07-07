#!/usr/bin/env python3
"""Compute the volatile project statistics that README.md reports.

The README quotes several numbers that drift as the tree grows — test count,
test-file count, source/line counts. Historically they were hand-maintained in
four places and contradicted each other (finding D1 of the 2026-07-06
tests/docs appraisal). This script is the single computation of those numbers;
``tests/unit/tooling/test_readme_statistics.py`` imports it and fails the suite
when any README location drifts out of tolerance.

Usage:
    python tools/gen_test_stats.py            # human-readable summary
    python tools/gen_test_stats.py --json     # machine-readable JSON

Nothing here rewrites the README — the numbers are quoted in prose and rounded
for the marketing lines, so updating them stays a deliberate human edit guarded
by the meta-test rather than an automatic overwrite.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _py_files(base: str) -> list[Path]:
    return [
        p for p in (REPO_ROOT / base).rglob("*.py")
        if "__pycache__" not in p.parts
    ]


def _line_count(paths: list[Path]) -> int:
    return sum(len(p.read_bytes().splitlines()) for p in paths)


def collected_test_count(timeout: float = 300.0) -> int:
    """Number of test items pytest collects from ``tests/`` (imports every
    test module in a subprocess — a few seconds)."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q",
         "-p", "no:cacheprovider"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout,
    )
    match = re.search(r"(\d+) tests collected", result.stdout)
    if not match:
        raise RuntimeError(
            "could not parse pytest collection output:\n"
            + result.stdout[-2000:])
    return int(match.group(1))


def compute_stats(include_collection: bool = True) -> dict[str, int]:
    """Return every volatile statistic the README quotes.

    ``include_collection=False`` skips the (slow) pytest collection so the
    cheap file/line counts can be obtained without spawning pytest.
    """
    psh_files = _py_files("psh")
    all_test_files = _py_files("tests")
    test_star_files = [p for p in all_test_files if p.name.startswith("test_")]

    stats = {
        "psh_files": len(psh_files),
        "psh_loc": _line_count(psh_files),
        "test_py_files": len(all_test_files),
        "test_star_files": len(test_star_files),
        "test_loc": _line_count(all_test_files),
    }
    if include_collection:
        stats["collected_tests"] = collected_test_count()
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true",
                        help="emit JSON instead of a human summary")
    parser.add_argument("--no-collection", action="store_true",
                        help="skip the pytest collection (file/line counts only)")
    args = parser.parse_args()

    stats = compute_stats(include_collection=not args.no_collection)

    if args.json:
        print(json.dumps(stats, indent=2, sort_keys=True))
        return 0

    print("PSH project statistics (computed from the tree):")
    if "collected_tests" in stats:
        print(f"  collected tests    : {stats['collected_tests']:,}")
    print(f"  test files (test_*): {stats['test_star_files']:,}")
    print(f"  test .py files     : {stats['test_py_files']:,}")
    print(f"  test lines         : {stats['test_loc']:,}")
    print(f"  psh .py files      : {stats['psh_files']:,}")
    print(f"  psh production lines: {stats['psh_loc']:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
