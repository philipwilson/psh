#!/opt/homebrew/bin/bash
# atk-b item 5: QR's %P zero-face claim. ~20 iterations of `time true` in
# psh (worktree) vs bash 5.2.26. Claim under attack: psh prints P=0.00 every
# run while bash prints a nonzero percentage.
set -u
WT=/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/atk-b/wt
BASH=/opt/homebrew/bin/bash
cd "$WT" || exit 1
python -c "import psh,psh.version;assert psh.__file__.startswith('$WT');assert psh.version.__version__=='0.773.0';print('DISCRIMINATOR-OK',psh.__file__)" || exit 1
CMD="TIMEFORMAT='R=%R U=%U S=%S P=%P'; time true"
echo "== psh x20"
for i in $(seq 1 20); do python -m psh -c "$CMD" 2>&1 | grep P=; done | sort | uniq -c
echo "== bash x20"
for i in $(seq 1 20); do $BASH -c "$CMD" 2>&1 | grep P=; done | awk -F'P=' '{print $2}' | sort -n | awk 'NR==1{min=$1} {vals[NR]=$1} END{print "n="NR" min="min" max="vals[NR]; nz=0; for(i=1;i<=NR;i++) if(vals[i]+0>0) nz++; print "nonzero="nz}'
