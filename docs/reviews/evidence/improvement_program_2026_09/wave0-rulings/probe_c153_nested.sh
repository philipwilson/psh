#!/bin/sh
# C153 nested-read rows (bounce B2): does `\#` advance for commands executed by
# eval, `.`/source, $(...), a subshell, a function body and a loop body?
# One construction, run in -c / script / stdin modes against bash 5.3.15 and psh.
TREE=/Users/pwilson/src/psh-w0d; BASH=/opt/homebrew/bin/bash; PY=$(command -v python3)
D=$(mktemp -d); cd "$D" || exit 1
bash_run() { env -u PWD -u OLDPWD "$BASH" "$@"; }
psh_run()  { env -u PWD -u OLDPWD PYTHONPATH="$TREE" PSH_STRICT_ERRORS=1 "$PY" -m psh "$@"; }
printf '%s\n' 'echo "src:${PS1@P}"' 'echo "src2:${PS1@P}"' > inc.sh
cat > n.sh <<'EOF'
PS1='\#|'
echo "a:${PS1@P}"
eval 'echo "ev:${PS1@P}"; true; true'
echo "b:${PS1@P}"
. ./inc.sh
echo "c:${PS1@P}"
x=$(echo "cs:${PS1@P}"; true); echo "$x"
echo "d:${PS1@P}"
( echo "sub:${PS1@P}"; true )
echo "e:${PS1@P}"
f() { echo "fn:${PS1@P}"; true; }
f
echo "g:${PS1@P}"
for i in 1 2 3; do :; done
echo "h:${PS1@P}"
source ./inc.sh
echo "i:${PS1@P}"
EOF
S=$(cat n.sh)
echo "identity: $(bash_run -c 'echo bash $BASH_VERSION'); $(env -u PWD -u OLDPWD PYTHONPATH="$TREE" "$PY" -c 'import psh;print("psh.__file__", psh.__file__)')"
for mode in c script stdin; do
  case $mode in
    c)      b=$(bash_run -c "$S" | tr '\n' ' '); p=$(psh_run -c "$S" | tr '\n' ' ');;
    script) b=$(bash_run n.sh | tr '\n' ' ');     p=$(psh_run n.sh | tr '\n' ' ');;
    stdin)  b=$(bash_run < n.sh | tr '\n' ' ');   p=$(psh_run < n.sh | tr '\n' ' ');;
  esac
  echo "-- $mode"; echo "bash: $b"; echo "psh:  $p"
done
rm -rf "$D"
