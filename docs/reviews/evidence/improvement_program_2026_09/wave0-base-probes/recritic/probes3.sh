#!/opt/homebrew/bin/bash
B=/opt/homebrew/bin/bash
D=$(mktemp -d); cd "$D"
psh() { env -u PWD -u OLDPWD PYTHONPATH=/Users/pwilson/src/psh PSH_STRICT_ERRORS=1 python -m psh "$@"; }
echo "##### W0-N2 triage shape (script): sleep 5 & sleep 0.1; sleep 5 & jobs"
printf 'sleep 5 & sleep 0.1; sleep 5 & jobs; kill %%1 %%2 2>/dev/null; wait 2>/dev/null\n' > n2.sh
echo "--- bash:"; $B n2.sh 2>&1 | head -3; echo "--- psh:"; psh n2.sh 2>&1 | head -3
echo "##### bare shopt -o listing width"; echo "--- bash:"; $B -c 'shopt -o | head -1' | sed -n l; echo "--- psh:"; psh -c 'shopt -o | head -1' | sed -n l
echo "##### shopt -o query width"; echo "--- bash:"; $B -c 'shopt -o errexit' | sed -n l
echo "##### read wording, bash 5.3.15 script + -c + read -u"
printf 'read x\necho rc=$?\n' > r.sh; $B r.sh <&- 2>&1; $B -c 'read -u 7 x; echo rc=$?' 2>&1; $B -c 'exec 5<&-; read -u 5 x; echo rc=$?' 2>&1
echo "--- psh:"; psh -c 'read -u 7 x; echo rc=$?' 2>&1
echo "##### 2.1 signal/ERR trap boundary shapes"
printf 'false\nexit\n' > t.sh
for c in 'g(){ false; exit; }; trap g ERR; (exit 5)' 'trap "false; . ./t.sh" ERR; (exit 5)' 'trap "false; { exit; }" ERR; (exit 5)' 'trap "false; eval exit" ERR; (exit 5)' 'trap "false; if true; then exit; fi" ERR; (exit 5)' 'trap "false; (exit); echo sub-rc=\$?" ERR; (exit 5); echo after' 'g(){ false; exit; }; trap g USR1; kill -USR1 $$; echo x' 'trap "false; . ./t.sh" USR1; kill -USR1 $$; echo x' 'trap "false; { exit; }" USR1; kill -USR1 $$; echo x' 'trap "false; exit" DEBUG; true' 'trap "false; exit" RETURN; f(){ :; }; f; echo x'; do echo "--- bash [$c]:"; $B -c "$c" 2>&1; echo "rc=$?"; echo "--- psh:"; psh -c "$c" 2>&1; echo "rc=$?"; done
rm -rf "$D"
