"""Structured phase-manifest pytest plugin for ``run_tests.py``.

Boundary Integrity Campaign, package E1 ("structured gate results"): the test
runner must judge a phase from STRUCTURED data, not from recognizing summary
text in a transcript. This plugin is loaded per phase with
``-p tools.pytest_phase_manifest`` and writes a JSON manifest containing the
collected node ids (in execution order) and per-outcome counts. ``run_tests.py``
consumes the manifest via ``classify_manifest()``; a missing, truncated, or
internally inconsistent manifest is a phase FAILURE independent of the
transcript or pytest's exit status.

It also provides ``--shuffle-seed N``: a deterministic shuffle of the collected
items (``random.Random(N).shuffle``), needed for the campaign's Phase-E exit
criterion (three standard runs under three serial-order seeds with identical
censuses). The shuffle happens in every collecting process, so under xdist all
workers compute the same shuffled order (xdist requires identical collection
order across workers), and in a serial phase the single in-process run is
shuffled the same deterministic way.

xdist notes (how the manifest stays truthful under ``-n``):

* Outcome reports are recorded on the CONTROLLER via
  ``pytest_runtest_logreport`` (xdist forwards every worker report there).
* The collected id list comes from ``pytest_xdist_node_collection_finished``
  (each worker's post-deselection collection; xdist itself enforces that all
  workers agree). In a non-xdist run it comes from ``pytest_collection_finish``.
* Deselected ids are observed worker-side (``pytest_deselected``) and shipped
  to the controller through ``config.workeroutput``; all workers deselect
  identically, so the first report wins.
* Workers never write the manifest — only the controller (or the single
  in-process run) does, atomically via ``os.replace``.

A worker crash leaves collected ids without outcome reports; the resulting
count mismatch is exactly what ``classify_manifest`` rejects.
"""

import json
import os
import random

import pytest

MANIFEST_SCHEMA = 1

#: Outcome categories, in the order they appear in the manifest counts.
OUTCOME_FIELDS = (
    "passed", "failed", "errored", "skipped", "xfailed", "xpassed",
)

# When several reports for one nodeid disagree (e.g. passed call but errored
# teardown), the highest-priority category wins, so every collected nodeid
# maps to exactly ONE category and the counts sum to the collection size.
_CATEGORY_PRIORITY = {
    "errored": 5, "failed": 4, "xpassed": 3, "xfailed": 2,
    "skipped": 1, "passed": 0,
}

_WORKEROUTPUT_KEY = "phase_manifest_deselected"


def pytest_addoption(parser):
    group = parser.getgroup("phase-manifest")
    group.addoption(
        "--phase-manifest",
        action="store",
        default=None,
        metavar="PATH",
        help="Write a JSON manifest of collected node ids and per-outcome "
             "counts for this run (consumed by run_tests.py).",
    )
    group.addoption(
        "--shuffle-seed",
        action="store",
        type=int,
        default=None,
        metavar="N",
        help="Deterministically shuffle the collected test items with "
             "random.Random(N). Identical in every collecting process, so it "
             "is xdist-safe.",
    )


def pytest_configure(config):
    if (config.getoption("--phase-manifest")
            or config.getoption("--shuffle-seed") is not None):
        config.pluginmanager.register(PhaseManifest(config),
                                      "phase-manifest-plugin")


def categorize_report(report):
    """Category contributed by one ``TestReport``, or None (no contribution).

    Mirrors pytest's own accounting: only the ``call`` phase produces
    passed/failed/xpassed; a setup/teardown failure is an ERROR; a skip can
    surface in setup (``skipif``, ``xfail(run=False)``) or call. A STRICT
    xpass is reported by pytest as ``failed`` (with ``wasxfail`` unset in
    modern pytest) and is deliberately counted here as ``failed``.
    """
    wasxfail = hasattr(report, "wasxfail")
    if report.when == "call":
        if report.outcome == "passed":
            return "xpassed" if wasxfail else "passed"
        if report.outcome == "failed":
            return "failed"
        if report.outcome == "skipped":
            return "xfailed" if wasxfail else "skipped"
        return None
    if report.outcome == "failed":
        return "errored"
    if report.outcome == "skipped":
        return "xfailed" if wasxfail else "skipped"
    return None


class PhaseManifest:
    """Collects per-run structural facts and writes the JSON manifest."""

    def __init__(self, config):
        self.config = config
        self.manifest_path = config.getoption("--phase-manifest")
        self.seed = config.getoption("--shuffle-seed")
        self.is_worker = hasattr(config, "workerinput")
        self.collected = None      # list[str] node ids, execution order
        self.deselected = []       # list[str] node ids (local observation)
        self.worker_deselected = None  # list[str] shipped from an xdist worker
        self.outcomes = {}         # nodeid -> category

    # --- collection ----------------------------------------------------------

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, config, items):
        if self.seed is not None:
            random.Random(self.seed).shuffle(items)

    def pytest_collection_finish(self, session):
        # Non-xdist runs (and xdist workers, whose value is unused): the final
        # selected items. Under xdist the controller performs no local
        # collection, so this hook records nothing there — the xdist
        # node-collection hook below fills self.collected instead.
        if self.collected is None and session.items:
            self.collected = [item.nodeid for item in session.items]

    @pytest.hookimpl(optionalhook=True)
    def pytest_xdist_node_collection_finished(self, node, ids):
        # Every worker reports the same post-deselection collection (xdist
        # enforces consistency); first report wins.
        if self.collected is None:
            self.collected = list(ids)

    def pytest_deselected(self, items):
        self.deselected.extend(item.nodeid for item in items)

    @pytest.hookimpl(optionalhook=True)
    def pytest_testnodedown(self, node, error):
        workeroutput = getattr(node, "workeroutput", None)
        if (self.worker_deselected is None and workeroutput
                and _WORKEROUTPUT_KEY in workeroutput):
            self.worker_deselected = list(workeroutput[_WORKEROUTPUT_KEY])

    # --- outcomes -------------------------------------------------------------

    def pytest_runtest_logreport(self, report):
        category = categorize_report(report)
        if category is None:
            return
        current = self.outcomes.get(report.nodeid)
        if (current is None
                or _CATEGORY_PRIORITY[category] > _CATEGORY_PRIORITY[current]):
            self.outcomes[report.nodeid] = category

    # --- manifest -------------------------------------------------------------

    def pytest_sessionfinish(self, session, exitstatus):
        if self.is_worker:
            # Ship worker-side facts to the controller; never write the file.
            workeroutput = getattr(self.config, "workeroutput", None)
            if workeroutput is not None:
                workeroutput[_WORKEROUTPUT_KEY] = list(self.deselected)
            return
        if not self.manifest_path:
            return
        self._write_manifest(int(exitstatus))

    def build_manifest(self, exitstatus):
        collected = self.collected if self.collected is not None else []
        counts = {field: 0 for field in OUTCOME_FIELDS}
        for category in self.outcomes.values():
            counts[category] += 1
        deselected = (self.deselected if self.deselected
                      else (self.worker_deselected or []))
        counts["deselected"] = len(deselected)
        return {
            "schema": MANIFEST_SCHEMA,
            "shuffle_seed": self.seed,
            "exitstatus": exitstatus,
            "collected": list(collected),
            "counts": counts,
            "failed_ids": sorted(n for n, c in self.outcomes.items()
                                 if c == "failed"),
            "errored_ids": sorted(n for n, c in self.outcomes.items()
                                  if c == "errored"),
        }

    def _write_manifest(self, exitstatus):
        manifest = self.build_manifest(exitstatus)
        tmp_path = self.manifest_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=1)
            f.write("\n")
        os.replace(tmp_path, self.manifest_path)
