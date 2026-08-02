#!/usr/bin/env python3
"""Mutation proof: every pin class must FAIL, and fail for its OWN reason.

cp-backup discipline (NEVER `git checkout` over uncommitted work — slot 3.1
lost a phase's work to exactly that, twice). Every revert is verified byte-
identical against the backup and drops the target's __pycache__ entries.

  python3 mutate.py            run all classes
  python3 mutate.py M3         run one
"""
import filecmp
import os
import shutil
import subprocess
import sys

WT = '/Users/pwilson/src/psh-r3-2'
ENGINE = os.path.join(WT, 'psh/expansion/pattern_engine.py')
PAREXP = os.path.join(WT, 'psh/expansion/parameter_expansion.py')
BACKUP = os.path.join(WT, 'tmp/slot32/backup')

IMMUT = 'tests/unit/expansion/test_pattern_engine_immutability.py'
TRANS = 'tests/unit/expansion/test_pattern_engine_transitions.py'
BATTERY = ('tests/unit/expansion/test_pattern_bash_composition_differential.py '
           'tests/unit/expansion/test_pattern_engine_differential.py')

# (id, target, old, new, tests to run, what MUST break and why)
MUTATIONS = [
    ('M1', ENGINE,
     "    m = _Matcher(text, profile.for_pathname, profile.ic)\n"
     "    return m._starts(root, end), m",
     "    m = _Matcher(text, profile.for_pathname, profile.ic)\n"
     "    out = set()\n"
     "    for i in range(end + 1):\n"
     "        if end in m._ends(root, 0, i):\n"
     "            out.add(i)\n"
     "    return frozenset(out), m",
     TRANS, 'suffix linearity: all-start pass reverted to per-start DP'),

    ('M2', ENGINE,
     "        startable = m._starts(Sequence(root.elements + (Star(),)), len(text))\n"
     "\n"
     "        def span_at(pos: int) -> Optional[int]:\n"
     "            if pos not in startable:\n"
     "                return None\n",
     "\n"
     "        def span_at(pos: int) -> Optional[int]:\n",
     TRANS, 'no-match scan linearity: all-start pre-filter removed'),

    ('M3', ENGINE,
     "        if op == '*':\n"
     "            return bool(self._ok_table(node, seq, gi, se)[si])",
     "        if op == '*':\n"
     "            seen = {si}\n"
     "            frontier = [si]\n"
     "            while frontier:\n"
     "                nxt = []\n"
     "                for pos in frontier:\n"
     "                    for end in range(pos + 1, se + 1):\n"
     "                        if end not in seen and self._alt_span(alts, pos, end):\n"
     "                            seen.add(end)\n"
     "                            nxt.append(end)\n"
     "                frontier = nxt\n"
     "            return any(rest_ok(pos) for pos in seen)",
     TRANS, 'quirk quadratic bound: ok-table reverted to closure rebuild'),

    ('M4', ENGINE,
     "@dataclass(frozen=True, eq=False, slots=True)\nclass Literal:",
     "@dataclass(eq=False)\nclass Literal:",
     IMMUT, 'immutability: Literal unfrozen'),

    ('M5', ENGINE,
     "        setattr_(self, 'has_extglob', _derive_has_extglob(elements))",
     "        setattr_(self, 'has_extglob', False)",
     IMMUT + ' ' + BATTERY,
     'derived bits: has_extglob derivation replaced by a constant'),

    # M8 re-introduces the ROUND-1 BLOCKER itself: ungate the pre-filter so
    # extglob-bearing patterns build it again — the O(n^2)-at-construction
    # regression that turned linear eligible substitutions quadratic.
    ('M8', ENGINE,
     "        if profile.for_pathname or root.has_extglob:",
     "        if profile.for_pathname:",
     TRANS, 'B1 gate removed: eager pre-filter returns for extglob patterns'),

    ('M7', PAREXP,
     "        pre_test = wrapped.suffix_matcher(value, profile)\n"
     "        span_at = compiled.spanner(value, profile)\n"
     "        while pos < n:\n"
     "            m = self._any_match_from(pre_test, span_at, end_eligible, n, pos)",
     "        while pos < n:\n"
     "            m = self._any_match(compiled, wrapped, end_eligible,\n"
     "                                value[pos:], profile)\n"
     "            if m is not None:\n"
     "                m = (pos + m[0], pos + m[1])",
     TRANS + ' ' + BATTERY,
     'substitution scan: shared matcher reverted to per-suffix slice'),
]


def backup():
    os.makedirs(BACKUP, exist_ok=True)
    for f in (ENGINE, PAREXP):
        shutil.copy2(f, os.path.join(BACKUP, os.path.basename(f)))
    print(f"backed up {len(os.listdir(BACKUP))} files -> {BACKUP}")


def drop_pycache(target):
    d = os.path.join(os.path.dirname(target), '__pycache__')
    if os.path.isdir(d):
        stem = os.path.basename(target)[:-3]
        for f in os.listdir(d):
            if f.startswith(stem + '.'):
                os.remove(os.path.join(d, f))


def restore(target):
    src = os.path.join(BACKUP, os.path.basename(target))
    shutil.copy2(src, target)
    drop_pycache(target)
    assert filecmp.cmp(src, target, shallow=False), f"RESTORE FAILED {target}"


def run(mid):
    for m in MUTATIONS:
        if m[0] != mid:
            continue
        _id, target, old, new, tests, why = m
        text = open(target).read()
        if text.count(old) != 1:
            print(f"{_id}: ANCHOR NOT UNIQUE ({text.count(old)} hits) — SKIP")
            return None
        open(target, 'w').write(text.replace(old, new, 1))
        drop_pycache(target)
        try:
            r = subprocess.run(
                [sys.executable, '-m', 'pytest', *tests.split(), '-q',
                 '--no-header', '-x'],
                cwd=WT, capture_output=True, text=True, timeout=900)
            tail = [ln for ln in r.stdout.strip().split('\n') if ln][-1]
            broke = r.returncode != 0
            print(f"  {_id}: {'FAILS (good)' if broke else '*** STILL PASSES ***'}"
                  f"  [{why}]")
            print(f"       {tail[:120]}")
            if broke:
                first = [ln for ln in r.stdout.split('\n')
                         if ln.startswith('FAILED') or 'assert' in ln][:2]
                for ln in first:
                    print(f"       reason: {ln.strip()[:130]}")
            return broke
        finally:
            restore(target)
    print(f"unknown mutation {mid}")
    return None


if __name__ == '__main__':
    backup()
    ids = sys.argv[1:] or [m[0] for m in MUTATIONS]
    results = {}
    for i in ids:
        results[i] = run(i)
    for f in (ENGINE, PAREXP):
        restore(f)
    print("\nSUMMARY (every class must FAIL):")
    for i, v in results.items():
        print(f"  {i}: {'FAILED as required' if v else 'DID NOT FAIL' if v is False else 'skipped'}")
    print(f"\nfinal restore verified: "
          f"{all(filecmp.cmp(os.path.join(BACKUP, os.path.basename(f)), f, shallow=False) for f in (ENGINE, PAREXP))}")
