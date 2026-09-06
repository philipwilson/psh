cd "$(mktemp -d)"
P() { env -u PWD -u OLDPWD PYTHONPATH=/Users/pwilson/src/psh PSH_STRICT_ERRORS=1 python -m psh "$@"; }
B() { env -u PWD -u OLDPWD /opt/homebrew/bin/bash "$@"; }
echo "=== 1 RETURN trap ==="
for s in 'f(){ :; }; trap "return 3" RETURN; f; echo rc=$?' 'f(){ return 5; }; trap "return 3" RETURN; f; echo rc=$?'; do
  echo "[$s]"; echo -n "bash: "; timeout 3 /opt/homebrew/bin/bash -c "$s" 2>&1 | tr '\n' ' '; echo " (t=$?)"
  echo -n "psh:  "; timeout 3 env PYTHONPATH=/Users/pwilson/src/psh PSH_STRICT_ERRORS=1 python -m psh -c "$s" 2>&1 | tr '\n' ' '; echo " (t=$?)"
done
grep -rln "RETURN" /Users/pwilson/src/psh/tests/conformance/bash/ | head -3
echo "=== 2 W0-N1 fd0 closed at startup ==="
P -c 'read x; echo rc=$?' <&- 2>&1 | tail -2 | cut -c1-200
printf 'read x; echo rc=$?\n' > s.sh; P s.sh <&- 2>&1 | tail -2 | cut -c1-200
echo "=== 3 closed fd0 no -c ==="
B <&- ; echo "bash rc=$?"
P <&- 2>&1 | tail -1; echo "psh rc=${PIPESTATUS[0]}"
echo -n "bash -c hi <&-: "; B -c 'echo hi' <&-; echo "rc=$?"
echo "=== 10 tilde in subscript (D14 premise) ==="
echo -n "bash in-script HOME: "; B -c 'HOME=/probe-home; declare -A a; a[~]=v; echo "${!a[@]}" ~' 
echo -n "bash env HOME:       "; env -u PWD HOME=/probe-home /opt/homebrew/bin/bash -c 'declare -A a; a[~]=v; echo "${!a[@]}" ~'
echo -n "psh in-script HOME:  "; P -c 'HOME=/probe-home; declare -A a; a[~]=v; echo "${!a[@]}" ~'
echo -n "bash in-script HOME plain tilde word: "; B -c 'HOME=/probe-home; echo ~ ~/x "${HOME}"'
