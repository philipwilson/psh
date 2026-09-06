#!/bin/sh
# C153 (\# command number) and C181 (-c + set -m job notice) re-derivation
# against bash 5.3.15 and psh at the w0/pkg-d worktree. Run from anywhere;
# every probe executes from a fresh mktemp -d with PWD/OLDPWD unset (D15).
TREE=/Users/pwilson/src/psh-w0d
BASH=/opt/homebrew/bin/bash
PY=$(command -v python3)
D=$(mktemp -d)
cd "$D" || exit 1

bash_run() { env -u PWD -u OLDPWD "$BASH" "$@"; }
psh_run()  { env -u PWD -u OLDPWD PYTHONPATH="$TREE" PSH_STRICT_ERRORS=1 "$PY" -m psh "$@"; }

echo "== identity"
echo "tree=$TREE  cwd=$D"
bash_run -c 'echo "bash $BASH_VERSION"'
psh_run -c 'echo "psh discriminator: $(python3 -c "import psh,sys;print(psh.__file__)" 2>/dev/null)"'
env -u PWD -u OLDPWD PYTHONPATH="$TREE" "$PY" -c 'import psh; print("psh.__file__ =", psh.__file__)'

echo
echo "== C153: PS1='\\#> ' via \${PS1@P} after a few commands"
SCRIPT='PS1="\#> "; echo "${PS1@P}"; echo "${PS1@P}"; true; echo "${PS1@P}"'
printf '%s\n' "$SCRIPT" > c153.sh
echo "-- -c mode"
echo "bash: $(bash_run -c "$SCRIPT" | tr '\n' ' ')"
echo "psh:  $(psh_run  -c "$SCRIPT" | tr '\n' ' ')"
echo "-- script mode"
echo "bash: $(bash_run c153.sh | tr '\n' ' ')"
echo "psh:  $(psh_run  c153.sh | tr '\n' ' ')"
echo "-- stdin mode"
echo "bash: $(bash_run < c153.sh | tr '\n' ' ')"
echo "psh:  $(psh_run  < c153.sh | tr '\n' ' ')"

echo
echo "== C181: -c + set -m, background job finishing before exit"
C181='set -m; sleep 0.01 & wait; echo end'
echo "-- bash -c"
bash_run -c "$C181" > o.out 2> o.err; echo "rc=$? stdout=$(tr '\n' '|' < o.out) stderr=$(tr '\n' '|' < o.err)"
echo "-- psh -c"
psh_run -c "$C181" > o.out 2> o.err; echo "rc=$? stdout=$(tr '\n' '|' < o.out) stderr=$(tr '\n' '|' < o.err)"
C181B='set -m; sleep 0.1 & sleep 0.3; jobs; echo end'
echo "-- bash -c (jobs listing variant)"
bash_run -c "$C181B" > o.out 2> o.err; echo "rc=$? stdout=$(tr '\n' '|' < o.out) stderr=$(tr '\n' '|' < o.err)"
echo "-- psh -c (jobs listing variant)"
psh_run -c "$C181B" > o.out 2> o.err; echo "rc=$? stdout=$(tr '\n' '|' < o.out) stderr=$(tr '\n' '|' < o.err)"
printf '%s\n' "$C181" > c181.sh
echo "-- bash script"
bash_run c181.sh > o.out 2> o.err; echo "rc=$? stdout=$(tr '\n' '|' < o.out) stderr=$(tr '\n' '|' < o.err)"
echo "-- psh script"
psh_run c181.sh > o.out 2> o.err; echo "rc=$? stdout=$(tr '\n' '|' < o.out) stderr=$(tr '\n' '|' < o.err)"

rm -rf "$D"
