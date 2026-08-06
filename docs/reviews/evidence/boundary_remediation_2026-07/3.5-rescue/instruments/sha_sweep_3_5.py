"""SCRIPTED VALUE-ALLOWLIST SHA SWEEP for the slot-3.5 ledger.

The rule: every SHA in the durable record is pasted from a command's output,
never typed. This sweep is the enforcement — it extracts every hex token that
LOOKS like a git object id from the ledger and checks each against an
allowlist whose values are themselves derived from git AT SWEEP TIME (not
transcribed). Anything unrecognised fails loudly.

Runs as the LAST edit before a final-tip declaration.
"""
import pathlib
import re
import subprocess
import sys

WT = pathlib.Path("/Users/pwilson/src/psh-r3-5")
LEDGER = WT / "tmp" / "remediation-ledgers" / "3.5.md"


def git(*args):
    return subprocess.run(["git", "-C", str(WT), *args],
                          capture_output=True, text=True, check=True).stdout.strip()


BASE = "963c6eab" + ""  # prefix only; full value derived below
base_full = git("rev-parse", "963c6eab")
head_full = git("rev-parse", "HEAD")
branch_shas = git("rev-list", "963c6eab..HEAD").split()
short = {git("rev-parse", "--short", s) for s in branch_shas}

# Allowlist VALUES, all derived from git in this process.
allow = set()
allow.add(base_full)
allow.add(base_full[:8])
allow.add(head_full)
allow.add(head_full[:8])
for s in branch_shas:
    allow.add(s)
    allow.add(s[:8])
allow |= short

# NON-GIT hex values the ledger legitimately quotes. These are DERIVED from the
# same instrument that produced them in the record, never typed here — the
# point of the sweep is that no hex token enters the durable record by hand.
#
# The CPython build id: the environment table records the interpreter as
# "3.14.2 (v3.14.2:df793163d58, ...)", pasted from sys.version. It is a CPython
# commit, not a psh object, so it can never be in the git allowlist — and it
# must still not be typed. Re-derive it here.
_pyver = sys.version
_m = re.search(r"\(v[\d.]+:([0-9a-f]{7,40})", _pyver)
if _m:
    allow.add(_m.group(1))
else:  # pragma: no cover - only on a non-release build
    print(f"WARNING: no CPython build id in sys.version: {_pyver!r}")

# SHAs legitimately quoted from OTHER slots' records (prior-art references).
# Each must be a real object in this repo, so they are VERIFIED, not trusted.
FOREIGN = ["241a923c"]
for f in FOREIGN:
    try:
        git("cat-file", "-e", f + "^{commit}")
        allow.add(f)
        allow.add(git("rev-parse", f))
    except subprocess.CalledProcessError:
        print(f"FOREIGN SHA {f} is not an object in this repo — reject")
        sys.exit(2)

text = LEDGER.read_text()

# Hex runs of 7..40 chars that are plausibly object ids. Exclude sha256 digests
# (64 chars) which the instruments legitimately quote, and pure-decimal runs.
tokens = set(re.findall(r"\b[0-9a-f]{7,40}\b", text))
tokens = {t for t in tokens if not t.isdigit()}

# sha256 file digests appear as 64-char values or 16-char elided prefixes
# followed by '…' — collect those separately so they are not mistaken for SHAs.
sha256_elided = set(re.findall(r"\b([0-9a-f]{16})…", text))

unknown = sorted(t for t in tokens
                 if t not in allow and t not in sha256_elided)

print(f"ledger      : {LEDGER}")
print(f"base        : {base_full}")
print(f"HEAD        : {head_full}")
print(f"branch cmts : {len(branch_shas)}")
print(f"allowlist   : {len(allow)} derived values")
print(f"tokens seen : {len(tokens)}")
print(f"sha256 elided (not object ids): {sorted(sha256_elided)}")
if unknown:
    print("\nFAIL — unrecognised SHA-like tokens (typed, stale, or foreign):")
    for u in unknown:
        print("   ", u)
    sys.exit(1)
print("\nPASS — every SHA-like token in the ledger resolves to a git-derived "
      "allowlist value.")
