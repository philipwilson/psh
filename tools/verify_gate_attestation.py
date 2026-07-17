#!/usr/bin/env python3
"""Verify the same-SHA gate attestation before release tagging (campaign E4).

Called by ``.github/workflows/release-tag.yml`` BEFORE creating the release
tag. The Boundary Integrity Campaign decision (E4, 2026-07-17): the local-gate
fast loop is retained — no required PR CI — but release-tag.yml stops tagging
unattested commits. ``python run_tests.py --parallel --write-attestation``
writes ``gate_attestation.json`` only on a fully green gate (plus ruff+mypy);
this script proves the attestation vouches for THIS tag:

1. ``gate_attestation.json`` exists at the repo root (absence = loud failure
   naming the campaign decision — the bootstrap case);
2. it is valid JSON with the expected schema and keys;
3. its ``version`` equals ``psh/version.py`` at HEAD (the version being
   tagged);
4. its ``gated_commit`` exists and is an ancestor of HEAD;
5. its ``gated_tree`` matches that commit's tree (internal consistency);
6. ``git diff --name-only <gated_commit> HEAD`` touches NOTHING except the
   attestation file itself — i.e. "nothing but the attestation changed since
   the gate ran", which solves the gated-tip vs merge-commit SHA mismatch.

Any failed check exits 1 so the workflow FAILS loudly and does NOT tag.

The checks live in ``verify_attestation()`` (repo path injected) so they are
unit-testable against scratch repositories:
tests/unit/tooling/test_gate_attestation.py.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ATTESTATION_FILENAME = "gate_attestation.json"
ATTESTATION_SCHEMA = 1
REQUIRED_KEYS = frozenset({
    "schema", "version", "gated_commit", "gated_tree", "platform", "phases",
    "ruff", "mypy_files", "timestamp", "command",
})

BOOTSTRAP_MESSAGE = (
    f"{ATTESTATION_FILENAME} is ABSENT at the repository root.\n"
    "Boundary Integrity Campaign decision (E4, 2026-07-17): release tagging\n"
    "requires a same-SHA gate attestation written by\n"
    "`python run_tests.py --parallel --write-attestation` on a fully green\n"
    "gate and committed as the final pre-push commit. No attestation, no tag\n"
    "— this loud failure is the designed bootstrap behavior; the first real\n"
    "attestation is written during the E1 release ceremony."
)


def _git(repo_root, *args):
    """Run git in *repo_root*; return (returncode, stdout_stripped)."""
    proc = subprocess.run(["git", *args], cwd=repo_root,
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip()


def _read_tree_version(repo_root):
    version_py = Path(repo_root) / "psh" / "version.py"
    if not version_py.exists():
        return None
    m = re.search(r'__version__\s*=\s*"([^"]+)"',
                  version_py.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def verify_attestation(repo_root, attestation_path=None):
    """Run all checks; return ``(ok, messages)``. No process exit here."""
    repo_root = Path(repo_root)
    if attestation_path is None:
        attestation_path = repo_root / ATTESTATION_FILENAME
    attestation_path = Path(attestation_path)

    if not attestation_path.exists():
        return False, [BOOTSTRAP_MESSAGE]

    try:
        data = json.loads(attestation_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        return False, [f"FAIL: {ATTESTATION_FILENAME} is unreadable or not "
                       f"valid JSON ({e})."]
    if not isinstance(data, dict):
        return False, [f"FAIL: {ATTESTATION_FILENAME} is not a JSON object."]

    messages = []
    missing = sorted(REQUIRED_KEYS - data.keys())
    if missing:
        messages.append(f"FAIL: attestation is missing required keys: "
                        f"{', '.join(missing)}.")
    if data.get("schema") != ATTESTATION_SCHEMA:
        messages.append(f"FAIL: attestation schema is {data.get('schema')!r}, "
                        f"expected {ATTESTATION_SCHEMA}.")
    if messages:
        return False, messages

    head_version = _read_tree_version(repo_root)
    if head_version is None:
        messages.append("FAIL: could not read __version__ from psh/version.py "
                        "at HEAD.")
    elif data["version"] != head_version:
        messages.append(
            f"FAIL: attestation version {data['version']!r} != psh/version.py "
            f"at HEAD {head_version!r}. The gate did not run for the version "
            "being tagged — re-run the gate with --write-attestation.")

    gated_commit = data["gated_commit"]
    rc, resolved = _git(repo_root, "rev-parse", "--verify", "--quiet",
                        f"{gated_commit}^{{commit}}")
    if rc != 0:
        messages.append(
            f"FAIL: gated_commit {gated_commit} is not a commit in this "
            "repository (shallow fetch? forged attestation?).")
        return False, messages

    rc, _ = _git(repo_root, "merge-base", "--is-ancestor", gated_commit,
                 "HEAD")
    if rc != 0:
        messages.append(
            f"FAIL: gated_commit {gated_commit} is NOT an ancestor of HEAD — "
            "the gated tree is not part of this history.")

    rc, gated_tree = _git(repo_root, "rev-parse", f"{gated_commit}^{{tree}}")
    if rc != 0 or gated_tree != data["gated_tree"]:
        messages.append(
            f"FAIL: attestation gated_tree {data['gated_tree']} does not "
            f"match the tree of {gated_commit} ({gated_tree or 'unresolvable'}).")

    rc, diff = _git(repo_root, "diff", "--name-only", gated_commit, "HEAD")
    if rc != 0:
        messages.append("FAIL: could not diff gated_commit against HEAD.")
    else:
        extras = sorted(set(diff.splitlines()) - {ATTESTATION_FILENAME})
        if extras:
            messages.append(
                "FAIL: files besides the attestation changed between "
                f"gated_commit and HEAD (the gate did not test what is being "
                f"tagged): {', '.join(extras)}.")

    if messages:
        return False, messages
    return True, [
        f"OK: {ATTESTATION_FILENAME} attests version {data['version']} at "
        f"gated_commit {gated_commit[:12]}; nothing but the attestation "
        "changed since the gate ran."
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=".",
                        help="Repository root (default: cwd).")
    parser.add_argument("--attestation", default=None,
                        help=f"Attestation path (default: <repo>/"
                             f"{ATTESTATION_FILENAME}).")
    args = parser.parse_args(argv)

    ok, messages = verify_attestation(args.repo, args.attestation)
    for message in messages:
        print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
