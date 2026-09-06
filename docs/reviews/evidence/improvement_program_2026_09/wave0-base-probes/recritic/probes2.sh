#!/opt/homebrew/bin/bash
B=/opt/homebrew/bin/bash
D=$(mktemp -d); cd "$D"
psh() { env -u PWD -u OLDPWD PYTHONPATH=/Users/pwilson/src/psh PSH_STRICT_ERRORS=1 python -m psh "$@"; }
both() { echo "##### $1"; shift; echo "--- bash:"; $B -c "$1" 2>&1 | sed -n l | head -4; echo "rc=${PIPESTATUS[0]}"; echo "--- psh :"; psh -c "$1" 2>&1 | sed -n l | head -4; echo "rc=${PIPESTATUS[0]}"; }
bothscript() { echo "##### [script] $1"; printf '%s\n' "$2" > sc.sh; echo "--- bash:"; $B sc.sh 2>&1 | head -4; echo "rc=${PIPESTATUS[0]}"; echo "--- psh :"; psh sc.sh 2>&1 | head -4; echo "rc=${PIPESTATUS[0]}"; }
both "P11a shopt nullglob" 'shopt nullglob'
both "P11b shopt -o errexit" 'shopt -o errexit'
both "P11c shopt -s (first line)" 'shopt -s nullglob; shopt -s | head -1'
both "P11d set -o (first line)" 'set -o | head -1'
both "P11e shopt -p nullglob" 'shopt -p nullglob'
echo "##### P2b W0-N2 -c mode, set -m"; for c in '/bin/ls >/dev/null; sleep 0.3 & jobs; wait' 'set -m; /bin/ls >/dev/null; sleep 0.3 & jobs; wait' '/bin/true; sleep 0.3 & echo "[$!]"; jobs; wait'; do echo "--- bash [$c]:"; $B -c "$c" 2>&1 | head -3; echo "--- psh:"; psh -c "$c" 2>&1 | head -3; done
echo "##### P2c script with set -m"; printf 'set -m\n/bin/ls >/dev/null\nsleep 0.3 &\njobs\nwait\n' > j2.sh; echo "--- bash:"; $B j2.sh 2>&1 | head -3; echo "--- psh:"; psh j2.sh 2>&1 | head -3
echo "##### P7 usage-error family, -c vs script"
for c in 'shift 1 2; echo after rc=$?' 'shift abc; echo after rc=$?' 'f(){ return abc; echo in-f rc=$?; }; f; echo after rc=$?' 'for i in 1; do break abc; echo in-loop rc=$?; done; echo after rc=$?' 'for i in 1; do continue abc; echo in-loop rc=$?; done; echo after rc=$?' 'exit 7 8; echo after rc=$?' 'exit abc; echo after rc=$?' 'f(){ return 1 2; echo in-f rc=$?; }; f; echo after rc=$?'; do both "-c [$c]" "$c"; bothscript "$c" "$c"; done
echo "##### P20b usage error in trap action / eval (set -q)"
for m in '' '--posix'; do for c in 'eval "set -q" || echo caught; echo after rc=$?' 'trap "set -q; echo in-trap-after" EXIT; echo main' 'trap "shift abc; echo in-trap-after" EXIT; echo main' 'trap "export 1bad=x; echo in-trap-after" EXIT; echo main'; do echo "--- bash $m [$c]:"; $B $m -c "$c" 2>&1; echo "rc=$?"; echo "--- psh $m:"; psh $m -c "$c" 2>&1; echo "rc=$?"; done; done
echo "##### P21b trap entry-status discriminating shapes"
printf 'false\nexit\n' > t.sh
for c in 'g(){ false; exit; }; trap g EXIT; (exit 5)' 'trap "false; { exit; }" EXIT; (exit 5)' 'trap "false; eval exit" EXIT; (exit 5)' 'trap "false; for i in 1; do exit; done" EXIT; (exit 5)' 'trap "false; . ./t.sh" EXIT; (exit 5)' 'trap "false; exit" USR1; kill -USR1 $$; echo x' 'trap "false; exit" ERR; (exit 5)' 'trap "false; (exit 7); exit" EXIT; (exit 5)' 'trap "echo entry=\$?; false; exit" EXIT; (exit 5)'; do echo "--- bash [$c]:"; $B -c "$c" 2>&1; echo "rc=$?"; echo "--- psh:"; psh -c "$c" 2>&1; echo "rc=$?"; done
rm -rf "$D"
