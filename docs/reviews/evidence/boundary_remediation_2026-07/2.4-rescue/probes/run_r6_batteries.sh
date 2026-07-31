#!/bin/bash
# Re-run every round-6 battery AT THE CURRENT TIP and stamp each output with
# the SHA it ran at, so the discharge audit can prove the evidence is the
# declared tip's evidence and not a leftover from an earlier commit.
#
# Usage:  bash tmp/r24-probes/run_r6_batteries.sh          (from the worktree root)
# Outputs: tmp/r24-probes/<battery>-TIP.txt  (each begins "SHA: <sha>")
set -u
cd "$(dirname "$0")/../.." || exit 1
SHA=$(git rev-parse HEAD)
echo "running round-6 batteries at $SHA"

for battery in r6b r6b2 r6b3 r6b4 r6b5 r6f r7a r8a r9a r10a r6c_flags r6d_embed r6_bounced; do
    out="tmp/r24-probes/${battery}-TIP.txt"
    { echo "SHA: $SHA"; echo "battery: ${battery}.py"; echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"; } > "$out"
    timeout 900 python "tmp/r24-probes/${battery}.py" >> "$out" 2>&1
    echo "  ${battery}: exit $? -> $out"
done

# The PTY battery is last: it drives real terminals, so it runs alone.
out="tmp/r24-probes/r6c_pty-TIP.txt"
{ echo "SHA: $SHA"; echo "battery: r6c_pty.py"; echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"; } > "$out"
timeout 600 python tmp/r24-probes/r6c_pty.py >> "$out" 2>&1
echo "  r6c_pty: exit $? -> $out"

# The guard-bite experiment: inserts a real offender under psh/, shows the
# guards RED, removes it, shows them green. Its own script prints the SHA.
bash tmp/r24-probes/guard_bite_evade.sh > tmp/r24-probes/guard-bite-TIP.txt 2>&1
echo "  guard-bite: -> tmp/r24-probes/guard-bite-TIP.txt"

# The chain table folds the three member batteries against the base/r4 outputs
# (those are commit-named and deliberately NOT re-run here).
out="tmp/r24-probes/r6b-CHAIN-TIP.txt"
{ echo "SHA: $SHA"; } > "$out"
python tmp/r24-probes/r6b_chain.py TIP >> "$out" 2>&1
echo "  chain: -> $out"

echo "done at $SHA"
