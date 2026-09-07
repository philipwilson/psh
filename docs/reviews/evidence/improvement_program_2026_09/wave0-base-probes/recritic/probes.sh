#!/opt/homebrew/bin/bash
B=/opt/homebrew/bin/bash
D=$(mktemp -d); cd "$D"
psh() { env -u PWD -u OLDPWD PYTHONPATH=/Users/pwilson/src/psh PSH_STRICT_ERRORS=1 python -m psh "$@"; }
run() { # label, cmd
  echo "##### $1"; shift
  echo "--- bash:"; $B -c "$1" 2>&1 | head -6; echo "rc=${PIPESTATUS[0]}"
  echo "--- psh :"; psh -c "$1" 2>&1 | head -6; echo "rc=${PIPESTATUS[0]}"
}
echo "bash: $($B -c 'echo $BASH_VERSION')"
echo "##### P1 W0-N1 fd0 closed at START: -c 'read x' <&-"
echo "--- bash:"; $B -c 'read x; echo rc=$?' <&- 2>&1 | head -3; echo "rc=${PIPESTATUS[0]}"
echo "--- psh :"; psh -c 'read x; echo rc=$?' <&- 2>&1 | tail -3; echo "rc=${PIPESTATUS[0]}"
echo "--- psh script mode:"; printf 'read x\necho rc=$?\n' > s.sh; psh s.sh <&- 2>&1 | tail -2; echo "rc=${PIPESTATUS[0]}"
run "P1b per-command read x <&-" 'read x <&-; echo rc=$?'
echo "##### P2 W0-N2 job number after foreground external (stdin mode)"
printf '/bin/ls >/dev/null\nsleep 0.3 &\njobs\nwait\n' > j.sh
echo "--- bash:"; $B j.sh 2>&1 | head -3; echo "--- psh:"; psh j.sh 2>&1 | head -3
run "P3 W0-N3 regex unbalanced brace" '[[ x =~ a{1 ]]; echo rc=$?'
run "P4 W0-N5 type under unset PATH" 'cd /bin; unset PATH; type ls; echo rc=$?'
run "P5 W0-N6 declare -c" 'declare -c x=hello; echo "[$x]" rc=$?'
echo "##### P6 W0-N7 stale PWD"; echo "--- bash:"; env PWD=/nonexistent/zz $B -c 'echo "$PWD"'; echo "--- psh:"; env -u OLDPWD PWD=/nonexistent/zz PYTHONPATH=/Users/pwilson/src/psh PSH_STRICT_ERRORS=1 python -m psh -c 'echo "$PWD"'
run "P7a exit abc (-c)" 'exit abc; echo after rc=$?'
run "P7b exit 7 8 (-c)" 'exit 7 8; echo after rc=$?'
run "P7c cd a b (-c)" 'cd a b; echo after rc=$?'
run "P7d shift abc (-c)" 'shift abc; echo after rc=$?'
run "P7e break abc (-c)" 'break abc; echo after rc=$?'
echo "##### P7f script mode: exit abc / exit 7 8 / cd a b"
printf 'exit abc\necho after1 rc=$?\nexit 7 8\necho after2 rc=$?\ncd a b\necho after3 rc=$?\n' > e.sh
echo "--- bash:"; $B e.sh 2>&1; echo "rc=$?"; echo "--- psh:"; psh e.sh 2>&1; echo "rc=$?"
run "P8a declare -i on readonly" 'readonly r=1; declare -i r; echo rc=$?'
run "P8b local -i on readonly local" 'f(){ local x=1; readonly x; local -i x; echo rc=$?; }; f'
run "P8c declare -x on readonly (allowed?)" 'readonly r=1; declare -x r; echo rc=$?'
run "P9a builtin declare a=(1)" 'builtin declare a=(1); echo rc=$?'
run "P9b let a=(1)" 'let a=(1); echo rc=$?'
run "P9c eval a=(1 2)" 'eval a=(1 2); echo "${a[1]}" rc=$?'
run "P9d alias a=(1)" 'alias a=(1); echo rc=$?'
run "P9e echo a=(1)" 'echo a=(1); echo rc=$?'
run "P10a exec {v}>&- v unset" 'exec {v}>&-; echo rc=$?'
run "P10b move form per-command closes source in parent?" 'exec 3>/dev/null; true 4<&3-; echo x >&3; echo rc=$?'
echo "##### P11 shopt widths"; for c in 'shopt nullglob' 'shopt -o errexit' 'shopt -s nullglob; shopt -s | head -1' 'set -o | head -1'; do echo "--- bash [$c]:"; $B -c "$c" | cat -A; echo "--- psh  [$c]:"; psh -c "$c" | cat -A; done
echo "##### P12 posix function names"; for c in 'a.b() { echo ok; }; a.b' 'function a-b { echo ok; }; a-b'; do echo "--- bash --posix [$c]:"; $B --posix -c "$c" 2>&1; echo "rc=$?"; echo "--- psh --posix:"; psh --posix -c "$c" 2>&1; echo "rc=$?"; done
run "P13 RETURN trap return 3" 'f(){ :; }; trap "return 3" RETURN; f; echo rc=$?'
echo "##### P17 printf %a 1: $($B -c "printf '%a\n' 1")"
echo "##### P20 posix special-builtin exits"
for c in 'export 1bad=x; echo after rc=$?' 'readonly 1bad=x; echo after rc=$?' 'readonly r=1; unset r; echo after rc=$?' 'export é=1; echo after rc=$?' 'eval "export 1bad=x" || echo caught; echo after' '. ./bad.sh; echo after' 'trap "export 1bad=x; echo in-trap-after" EXIT; echo main'; do printf 'export 1bad=x\necho in-dot-after\n' > bad.sh; echo "--- bash --posix [$c]:"; $B --posix -c "$c" 2>&1; echo "rc=$?"; echo "--- psh --posix:"; psh --posix -c "$c" 2>&1; echo "rc=$?"; done
echo "##### P21 trap entry status"
for c in 'trap "true; exit" EXIT; false' 'trap "exit" ERR; false; echo notreached' 'f(){ trap "exit" EXIT; false; }; f; echo x' 'trap "if true; then exit; fi" EXIT; (exit 5)' 'trap "eval exit" EXIT; (exit 5)' 'g(){ exit; }; trap "false; g" EXIT; (exit 5)'; do echo "--- bash [$c]:"; $B -c "$c" 2>&1; echo "rc=$?"; echo "--- psh:"; psh -c "$c" 2>&1; echo "rc=$?"; done
rm -rf "$D"
