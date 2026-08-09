#!/opt/homebrew/bin/bash
# B1 — TWO-AXIS forcing for the narrowed maskers (brief: "Pins YOU create").
#
#   AXIS 1 (REGRESSION): every non-defect path — valid AND invalid INPUT —
#     byte-identical base vs tip. Invalid input is NOT a defect: `popd letters`
#     must print exactly what it printed. This axis must come back EMPTY.
#   AXIS 2 (RECLASSIFICATION): the forced defect, which used to be swallowed as
#     a user diagnostic, now surfaces per the strict-errors taxonomy.
#
# Usage: B1_masker_two_axis.sh <ROOT> <label>
set -u
ROOT="${1:?usage: $0 <ROOT> <label>}"; LABEL="${2:?}"
BASH_BIN="$(command -v bash)"
[ "$BASH_BIN" = "/bin/bash" ] && { echo "REFUSING /bin/bash" >&2; exit 2; }
cd "$ROOT" || exit 2
PYTHONPATH="$ROOT" python3 -c "import psh,os,sys; p=os.path.dirname(psh.__file__); \
  sys.exit(0) if p==os.path.join('$ROOT','psh') else (print('DISCRIMINATOR FAILED '+p),sys.exit(2))" || exit 2
echo "# $LABEL  tree=$ROOT  oracle=$BASH_BIN $("$BASH_BIN" --version|head -1|sed 's/.*version //;s/ .*//')"

# The probe runs from a FIXED neutral cwd, identical for the base and tip
# runs, because `dirs` prints the current directory: run from $ROOT the two
# trees would differ in every dirs cell purely because they sit at different
# paths. A diff that is non-empty for a reason I then explain away is exactly
# what this axis must not produce -- pin the cwd so EMPTY means empty.
NEUTRAL="/Users/pwilson/src/psh-r5c-1/tmp/w5c1-neutral"
mkdir -p "$NEUTRAL"
p () { (cd "$NEUTRAL" && PYTHONPATH="$ROOT" PYTHONDONTWRITEBYTECODE=1 \
        python3 -m psh -c "$1" 2>&1); echo "  rc=$?"; }

echo "=== AXIS 1: non-defect paths (valid AND invalid input) ==="
for s in \
  'cd /tmp; pushd /usr >/dev/null; popd; echo rc=$?' \
  'cd /tmp; pushd /usr >/dev/null; popd +0 >/dev/null; echo rc=$?' \
  'cd /tmp; pushd /usr >/dev/null; popd -0 >/dev/null; echo rc=$?' \
  'popd letters' \
  'popd +letters' \
  'popd -letters' \
  'popd +99' \
  'popd -99' \
  'popd ""' \
  'popd +' \
  'popd -' \
  'cd /tmp; pushd /usr >/dev/null; popd -n; echo rc=$?' \
  'popd -n letters' \
  'popd -n +99' \
  'dirs' \
  'dirs -v' \
  'dirs +0' \
  'dirs -0' \
  'dirs letters' \
  'dirs +letters' \
  'dirs +99' \
  'dirs -99' \
  'dirs +' \
  'dirs -q' \
  'disown %bogus' \
  'disown notanumber' \
  'disown 999999' \
  'disown -h notanumber' \
  'disown %1' \
  'disown' \
  'sleep 0.2 & disown %1; jobs; echo rc=$?' \
  'sleep 0.2 & disown $!; jobs; echo rc=$?' \
  ; do
  printf '%-52s ::: ' "$s"; p "$s" | tr '\n' '|'; echo
done
