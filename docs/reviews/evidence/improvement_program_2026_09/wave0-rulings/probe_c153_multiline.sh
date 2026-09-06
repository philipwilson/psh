#!/bin/sh
# C153 multi-line form (one command per line) in -c / script / stdin modes.
TREE=/Users/pwilson/src/psh-w0d; BASH=/opt/homebrew/bin/bash; PY=$(command -v python3)
D=$(mktemp -d); cd "$D" || exit 1
bash_run() { env -u PWD -u OLDPWD "$BASH" "$@"; }
psh_run()  { env -u PWD -u OLDPWD PYTHONPATH="$TREE" PSH_STRICT_ERRORS=1 "$PY" -m psh "$@"; }
printf '%s\n' 'PS1="\#> "' 'echo "${PS1@P}"' 'echo "${PS1@P}"' 'true' 'echo "${PS1@P}"' > m.sh
S=$(cat m.sh)
echo "-- -c (multi-line string)";  echo "bash: $(bash_run -c "$S" | tr '\n' ' ')"; echo "psh:  $(psh_run -c "$S" | tr '\n' ' ')"
echo "-- script";                  echo "bash: $(bash_run m.sh | tr '\n' ' ')";   echo "psh:  $(psh_run m.sh | tr '\n' ' ')"
echo "-- stdin";                   echo "bash: $(bash_run < m.sh | tr '\n' ' ')"; echo "psh:  $(psh_run < m.sh | tr '\n' ' ')"
rm -rf "$D"
