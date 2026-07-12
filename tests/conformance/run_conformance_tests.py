#!/usr/bin/env python3
"""Conformance test runner: pytest discovery + a defect-gating JSON report.

This runner is a thin, trustworthy wrapper around pytest. It exists so the
conformance suite can be driven from one command (CI/nightly, the release
gate, a developer at the keyboard) and produce a machine-readable summary --
*without* re-implementing a test harness.

Design goals (why this replaced the old hand-rolled runner):

1. **Discovery, not a hardcoded list.** The old runner imported a frozen
   subset of test classes (~360 of the ~1,500 that pytest collects) and called
   their methods directly, bypassing fixtures, parametrization, and pytest's
   xfail handling. Here we hand the whole ``tests/conformance/`` tree to
   pytest and report the *real* collected/passed/failed/skipped counts.

2. **Fail on any defect.** The old ``main()`` always exited 0, so a PSH
   regression could never fail CI. Here the process exit code is driven by
   pytest's own exit code AND cross-checked against the collected outcomes:
   any failed test, errored test, or empty collection makes us exit non-zero.
   Because ``xfail_strict = true`` is set in ``pytest.ini``, an *unexpected*
   XPASS (a stale absent-feature marker) is already a pytest failure and is
   therefore gated too.

3. **A machine-readable report.** ``pytest_runtest_logreport`` (in the small
   plugin below) records every test's outcome; at the end we emit a JSON
   document with the counts, the full per-test outcome list, and a focused
   list of failures with their tracebacks. ``report["success"]`` is the single
   boolean a CI job can gate on.

4. **No stale metrics.** Everything reported is computed from the run that
   just happened. There is no baked-in percentage.

What this runner does NOT change: how conformance tests are *written*. They
still subclass :class:`ConformanceTest` and call
``assert_identical_behavior`` / ``assert_documented_difference`` /
``assert_psh_extension``. Those assertions already
encode the policy that "a psh != bash divergence that is not a documented
difference is a defect" -- when they fail, pytest fails, and this runner gates
on it. The runner only changes how the suite is *run* and *reported*.

Usage::

    python run_conformance_tests.py                # full suite, gate + report
    python run_conformance_tests.py --posix-only   # only tests/conformance/posix
    python run_conformance_tests.py --bash-only    # only tests/conformance/bash
    python run_conformance_tests.py --summary-only  # gate + print, no JSON file
    python run_conformance_tests.py --json out.json # write report to a path
    python run_conformance_tests.py -k hash         # extra args pass to pytest

Exit code: 0 iff every collected conformance test passed (and at least one was
collected); non-zero otherwise. The non-zero value mirrors pytest's own exit
code where possible (1 = failures, 2 = interrupted, 3 = internal error,
5 = nothing collected).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, cast

import pytest

# The test modules insert this directory onto sys.path themselves, but importing
# find_bash here lets us record which bash acted as the oracle in the report.
sys.path.insert(0, os.path.dirname(__file__))
from conformance_framework import find_bash  # noqa: E402

CONFORMANCE_DIR = Path(__file__).resolve().parent

# Outcome buckets, in the order we display them. These mirror pytest's own
# terminal-summary categories so the numbers reconcile with a plain pytest run.
OUTCOME_ORDER = ["passed", "failed", "error", "skipped", "xfailed", "xpassed"]

# Outcomes that make the run a failure (i.e. represent a real defect).
DEFECT_OUTCOMES = frozenset({"failed", "error"})

# Cap stored failure tracebacks so a pathological repr can't bloat the report.
MAX_MESSAGE_CHARS = 4000


def _short_repr(report) -> str:
    """Return a bounded, human-readable representation of a failure report."""
    text = getattr(report, "longreprtext", "") or str(getattr(report, "longrepr", ""))
    if len(text) > MAX_MESSAGE_CHARS:
        text = text[:MAX_MESSAGE_CHARS] + "\n... (truncated)"
    return text


class ConformanceReportPlugin:
    """A pytest plugin that records per-test outcomes for the JSON report.

    We derive a single outcome per test node from its setup/call/teardown
    reports, using the same rules pytest's terminal reporter uses:

    * a failure/skip during *setup* means the body never ran (error / skipped);
    * the *call* phase carries the real pass/fail/skip and xfail information;
    * a failure during *teardown* is an error that upgrades a prior pass.

    ``xfail_strict = true`` means an unexpected pass of an ``xfail`` test is
    delivered as a *failed* call report, so it lands in ``failed`` and gates
    the run -- exactly what we want for a stale absent-feature marker.
    """

    def __init__(self) -> None:
        self.collected_nodeids: List[str] = []
        self._outcomes: Dict[str, str] = {}
        self._messages: Dict[str, str] = {}
        self._durations: Dict[str, float] = {}

    def pytest_collection_finish(self, session) -> None:
        # Ground-truth "collected" count, independent of how many actually ran.
        self.collected_nodeids = [item.nodeid for item in session.items]

    def pytest_runtest_logreport(self, report) -> None:
        nodeid = report.nodeid
        if report.when == "call":
            self._durations[nodeid] = getattr(report, "duration", 0.0)

        if report.when == "setup":
            if report.failed:
                self._record(nodeid, "error", report)
            elif report.skipped:
                self._record(nodeid, self._skip_kind(report), report)
        elif report.when == "call":
            if report.failed:
                self._record(nodeid, "failed", report)
            elif report.skipped:
                self._record(nodeid, self._skip_kind(report), report)
            else:  # passed
                self._record(nodeid, "xpassed" if hasattr(report, "wasxfail") else "passed", report)
        elif report.when == "teardown" and report.failed:
            # A teardown error is a defect; keep an existing call failure as the
            # primary outcome but upgrade a pass/xfail to an error.
            if self._outcomes.get(nodeid) not in ("failed", "error"):
                self._record(nodeid, "error", report)

    @staticmethod
    def _skip_kind(report) -> str:
        """Distinguish an expected failure (xfail) from a plain skip."""
        return "xfailed" if hasattr(report, "wasxfail") else "skipped"

    def _record(self, nodeid: str, outcome: str, report) -> None:
        self._outcomes[nodeid] = outcome
        if outcome in DEFECT_OUTCOMES:
            self._messages[nodeid] = _short_repr(report)

    # --- summarisation -----------------------------------------------------

    def counts(self) -> Dict[str, int]:
        counts = {name: 0 for name in OUTCOME_ORDER}
        for outcome in self._outcomes.values():
            counts[outcome] = counts.get(outcome, 0) + 1
        counts["collected"] = len(self.collected_nodeids)
        return counts

    def defect_count(self) -> int:
        return sum(1 for o in self._outcomes.values() if o in DEFECT_OUTCOMES)

    def tests(self) -> List[Dict[str, object]]:
        out = []
        for nodeid in self.collected_nodeids:
            out.append({
                "nodeid": nodeid,
                "outcome": self._outcomes.get(nodeid, "notrun"),
                "duration": round(self._durations.get(nodeid, 0.0), 4),
            })
        return out

    def failures(self) -> List[Dict[str, str]]:
        out = []
        for nodeid, outcome in self._outcomes.items():
            if outcome in DEFECT_OUTCOMES:
                out.append({
                    "nodeid": nodeid,
                    "outcome": outcome,
                    "message": self._messages.get(nodeid, ""),
                })
        out.sort(key=lambda item: item["nodeid"])
        return out


def build_pytest_args(paths: List[str], extra: List[str]) -> List[str]:
    """Assemble pytest arguments.

    ``-o addopts=`` clears ``pytest.ini``'s ``addopts`` entirely (currently
    ``--tb=short --ignore=tests/performance``) so this runner controls output on
    its own terms and prints its own summary rather than pytest's progress.
    ``--tb=short`` keeps captured tracebacks compact in the report.
    """
    args = list(paths)
    args += ["-o", "addopts=", "--tb=short", "-p", "no:cacheprovider"]
    args += extra
    return args


def selection_paths(posix_only: bool, bash_only: bool) -> tuple[str, List[str]]:
    """Map the CLI selection flags to concrete test directories."""
    if posix_only:
        return "posix", [str(CONFORMANCE_DIR / "posix")]
    if bash_only:
        return "bash", [str(CONFORMANCE_DIR / "bash")]
    return "all", [str(CONFORMANCE_DIR)]


def build_report(plugin: ConformanceReportPlugin, exit_code: int,
                 final_code: int, selection: str, duration: float) -> Dict[str, object]:
    counts = plugin.counts()
    return {
        "schema": "psh-conformance-report/1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "selection": selection,
        "bash_oracle": find_bash(),
        "duration_seconds": round(duration, 2),
        "pytest_exit_code": int(exit_code),
        "exit_code": final_code,
        "success": final_code == 0,
        "counts": counts,
        "failures": plugin.failures(),
        "tests": plugin.tests(),
    }


def print_summary(report: Dict[str, object]) -> None:
    counts = cast(Dict[str, int], report["counts"])
    failures = cast(List[Dict[str, str]], report["failures"])
    print("\n" + "=" * 72)
    print("CONFORMANCE SUMMARY")
    print("=" * 72)
    print(f"Selection:     {report['selection']}")
    print(f"Bash oracle:   {report['bash_oracle']}")
    print(f"Duration:      {report['duration_seconds']}s")
    print(f"Collected:     {counts['collected']}")
    for name in OUTCOME_ORDER:
        if counts.get(name):
            print(f"  {name:<10} {counts[name]}")
    if failures:
        print(f"\nDEFECTS ({len(failures)}):")
        for item in failures[:25]:
            print(f"  [{item['outcome']}] {item['nodeid']}")
        if len(failures) > 25:
            print(f"  ... and {len(failures) - 25} more (see JSON report)")
    verdict = "PASS" if report["success"] else "FAIL"
    print("-" * 72)
    print(f"RESULT: {verdict} (exit {report['exit_code']})")
    print("=" * 72)


def write_report(report: Dict[str, object], output_dir: Path,
                 json_path: Optional[Path]) -> Path:
    """Write the JSON report and return the path of the canonical copy."""
    if json_path is not None:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report, indent=2))
        return json_path

    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    timestamped = output_dir / f"conformance_report_{stamp}.json"
    timestamped.write_text(json.dumps(report, indent=2))
    # A stable filename a CI job can always read.
    latest = output_dir / "conformance_report.json"
    latest.write_text(json.dumps(report, indent=2))
    return latest


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run PSH conformance tests via pytest and gate on defects.",
    )
    parser.add_argument("--posix-only", action="store_true",
                        help="Run only tests/conformance/posix")
    parser.add_argument("--bash-only", action="store_true",
                        help="Run only tests/conformance/bash")
    parser.add_argument("--summary-only", action="store_true",
                        help="Print the summary and gate, but do not write a JSON file")
    parser.add_argument("--json", dest="json_path", default=None,
                        help="Write the JSON report to this exact path "
                             "(default: <output-dir>/conformance_report.json)")
    parser.add_argument("--output-dir", default=str(CONFORMANCE_DIR / "conformance_results"),
                        help="Directory for the JSON report "
                             "(default: tests/conformance/conformance_results, gitignored)")
    # Any unrecognised arguments (e.g. -k, -x, --lf) pass straight to pytest.
    args, extra = parser.parse_known_args(argv)

    if args.posix_only and args.bash_only:
        parser.error("--posix-only and --bash-only are mutually exclusive")

    selection, paths = selection_paths(args.posix_only, args.bash_only)
    pytest_args = build_pytest_args(paths, extra)

    plugin = ConformanceReportPlugin()
    start = time.time()
    exit_code = pytest.main(pytest_args, plugins=[plugin])
    duration = time.time() - start

    # Gate: honour pytest's exit code, and independently fail if any collected
    # outcome is a defect or if nothing was collected. Belt and suspenders --
    # a green pytest exit with recorded defects should never happen, but if it
    # did we must still fail loudly rather than pass silently (the exact bug
    # this runner replaced).
    exit_code = int(exit_code)
    defects = plugin.defect_count()
    collected = len(plugin.collected_nodeids)
    if exit_code != 0:
        final_code = exit_code
    elif defects > 0 or collected == 0:
        final_code = 1
    else:
        final_code = 0

    report = build_report(plugin, exit_code, final_code, selection, duration)

    if not args.summary_only:
        json_path = Path(args.json_path) if args.json_path else None
        written = write_report(report, Path(args.output_dir), json_path)
        report["_report_path"] = str(written)

    print_summary(report)
    if "_report_path" in report:
        print(f"JSON report: {report['_report_path']}")

    return final_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nConformance run interrupted", file=sys.stderr)
        sys.exit(2)
