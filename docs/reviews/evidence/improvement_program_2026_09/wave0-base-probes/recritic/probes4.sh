#!/opt/homebrew/bin/bash
B=/opt/homebrew/bin/bash
D=$(mktemp -d); cd "$D"; mkdir -p x /tmp/cdp_probe_$$/x
psh() { env -u PWD -u OLDPWD PYTHONPATH=/Users/pwilson/src/psh PSH_STRICT_ERRORS=1 python -m psh "$@"; }
echo "##### psh -c 'echo hi' <&- (must run normally)"; echo "--- bash:"; $B -c 'echo hi' <&- 2>&1; echo "rc=$?"; echo "--- psh:"; psh -c 'echo hi' <&- 2>&1 | tail -2; echo "rc=${PIPESTATUS[0]}"
echo "##### psh <&- / psh -s <&- (126 path)"; echo "--- bash:"; $B <&- 2>&1; echo "rc=$?"; echo "--- psh:"; psh <&- 2>&1 | tail -2; echo "rc=${PIPESTATUS[0]}"
for c in 'HOME=; cd; echo rc=$? pwd=$(pwd)' 'OLDPWD=; cd -; echo rc=$?' "CDPATH=:/tmp/cdp_probe_$$; cd x; echo rc=\$?" "CDPATH=/tmp/cdp_probe_$$:; cd x; echo rc=\$?"; do echo "##### [$c]"; echo "--- bash:"; $B -c "$c" 2>&1; echo "--- psh:"; psh -c "$c" 2>&1; done
rm -rf "$D" /tmp/cdp_probe_$$
