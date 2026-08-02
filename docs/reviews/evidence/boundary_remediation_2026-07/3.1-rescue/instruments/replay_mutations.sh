#!/bin/sh
# Slot 3.1 mutation-proof replay (R6: one-command, WITH cache hygiene).
# Runs all six mutation classes M1-M6 against the tip tree: mutate, run the
# noticing instrument, revert, AND drop the target's __pycache__ entries
# (same-second same-size reverts are invisible to mtime+size .pyc
# validation — the B7 lesson). Expected: every phase prints a FAILURE line
# for its OWN reason; the final suite run is green.
#
# Usage: sh tmp/slot31/replay_mutations.sh   (from the worktree root)
set -u
cd "$(dirname "$0")/../.." || exit 1
echo "tree: $(git rev-parse HEAD) ($(git status --porcelain | wc -l | tr -d ' ') dirty files before)"

clean_caches() {
    rm -f tests/unit/expansion/__pycache__/test_pattern_bash_composition_differential* \
          tests/unit/expansion/__pycache__/test_pattern_engine_differential* \
          psh/expansion/__pycache__/pattern_engine* \
          psh/expansion/__pycache__/parameter_expansion*
}

# Backup/restore by FILE COPY, never `git checkout` — a checkout would
# discard any UNCOMMITTED work-in-progress in these files (campaign lesson
# "never git-checkout over uncommitted mutations"; bitten once in Phase C).
TARGETS="psh/expansion/pattern_engine.py psh/expansion/parameter_expansion.py tests/unit/expansion/test_pattern_bash_composition_differential.py"
BAK=tmp/slot31/.replay-bak
backup() {
    rm -rf "$BAK"; mkdir -p "$BAK"
    for f in $TARGETS; do cp "$f" "$BAK/$(basename "$f")"; done
}
revert() {
    for f in $TARGETS; do cp "$BAK/$(basename "$f")" "$f"; done
    clean_caches
}

backup


echo '=== M1: engine enclosed-rule flip -> corpus names enclosure cells ==='
python - <<'EOF'
p = 'psh/expansion/pattern_engine.py'
src = open(p).read()
old = "                    return not cast(Extglob, node2).enclosed"
assert src.count(old) == 1
open(p, 'w').write(src.replace(old, old.replace(
    "return not cast(Extglob, node2).enclosed", "return True")))
EOF
clean_caches
python -m pytest tests/unit/expansion/test_pattern_bash_composition_differential.py::test_composition_corpus_engine_matches_bash -q 2>&1 | grep -oE "[0-9]+ divergences over [0-9]+ grammar-v2 cells" | head -1
revert

echo '=== M2: suffix pre-test disabled -> pretest_end rows ==='
python - <<'EOF'
p = 'psh/expansion/parameter_expansion.py'
src = open(p).read()
old = """        if not fast_ok:
            if not wrapped.full_match(value, profile):
                return value
        starts = compiled.matching_starts(value, len(value), profile)"""
new = """        starts = compiled.matching_starts(value, len(value), profile)"""
assert src.count(old) == 1
open(p, 'w').write(src.replace(old, new))
EOF
clean_caches
python -m pytest tests/unit/expansion/test_pattern_bash_composition_differential.py::test_consumer_propagation_and_empty_subject_family -q 2>&1 | grep -o "pretest_end[^)]*" | head -2
revert

echo '=== M3: end gate forced open -> emptysub family + q4 closure ==='
python - <<'EOF'
p = 'psh/expansion/parameter_expansion.py'
src = open(p).read()
old = "    end_eligible = pattern.startswith('*')"
assert src.count(old) == 1
open(p, 'w').write(src.replace(old, "    end_eligible = True"))
EOF
clean_caches
python -m pytest tests/unit/expansion/test_pattern_bash_composition_differential.py::test_consumer_propagation_and_empty_subject_family tests/unit/expansion/test_pattern_engine_differential.py::test_former_known_divergences_now_match_bash -q 2>&1 | grep -oE "emptysub_[a-z]+', 'psh!=bash[^)]*" | head -2
revert

echo '=== M4: memo disabled -> state guard NAMES the pattern ==='
python - <<'EOF'
p = 'psh/expansion/pattern_engine.py'
src = open(p).read()
old = """    def match(self, seq: Sequence, ei: int, si: int, se: int) -> bool:
        key = (id(seq), ei, si, se)
        r = self.memo.get(key)
        if r is None:
            self.states += 1
            r = self._match(seq, ei, si, se)
            self.memo[key] = r
        return r"""
new = """    def match(self, seq: Sequence, ei: int, si: int, se: int) -> bool:
        self.states += 1
        return self._match(seq, ei, si, se)"""
assert src.count(old) == 1
open(p, 'w').write(src.replace(old, new))
EOF
clean_caches
python -m pytest tests/unit/expansion/test_pattern_bash_composition_differential.py::test_bash_matcher_states_stay_polynomial -q 2>&1 | grep -o "pattern '[^']*' on [^:]*: [0-9]* states[^—]*" | head -1
revert

echo '=== M5: residual bash value corrupted -> oracle-drift arm ==='
python - <<'EOF'
p = 'tests/unit/expansion/test_pattern_bash_composition_differential.py'
src = open(p).read()
old = '''    ("lex_q1", "[[ 'a' == !(\\"a\\") ]]\\nprintf 'lex_q1=%s\\\\n' $?",
     "1", "0"),'''
assert src.count(old) == 1
open(p, 'w').write(src.replace(old, old.replace('"1", "0"', '"0", "0"')))
EOF
clean_caches
python -m pytest tests/unit/expansion/test_pattern_bash_composition_differential.py::test_residual_divergences_still_divergent -q 2>&1 | grep -o "lex_q1', 'oracle drift[^)]*" | head -1
revert

echo '=== M6: fast-path end-policy broken -> boundary equivalence notices ==='
python - <<'EOF'
p = 'psh/expansion/parameter_expansion.py'
src = open(p).read()
old = "            elif length is not None and not (pos == n and n > 0):"
assert src.count(old) == 1
open(p, 'w').write(src.replace(old, "            elif length is not None:"))
EOF
clean_caches
python -m pytest tests/unit/expansion/test_pattern_bash_composition_differential.py::test_fast_path_eligibility_boundary -q 2>&1 | grep -oE "\('[^']*', '[^']*', 'substitute_[a-z]+', '[^']*', '[^']*'\)" | head -2
revert

echo '=== post-replay: tree clean + module green ==='

git status --porcelain | head -3
python -m pytest tests/unit/expansion/test_pattern_bash_composition_differential.py -q 2>&1 | tail -1
