cd "$(mktemp -d)"; mkdir d1
P() { env -u PWD -u OLDPWD PYTHONPATH=/Users/pwilson/src/psh PSH_STRICT_ERRORS=1 python -m psh "$@"; }
B() { env -u PWD -u OLDPWD /opt/homebrew/bin/bash "$@"; }
echo "=== D14 export variant ==="
echo -n "bash export HOME in-script: "; B -c 'export HOME=/probe-home; echo ~'
echo "=== OLDPWD inherited ==="
echo -n "bash valid OLDPWD: "; env -u PWD OLDPWD=/tmp /opt/homebrew/bin/bash -c 'echo "[$OLDPWD]"; cd - >/dev/null && pwd'
echo -n "psh  valid OLDPWD: "; env -u PWD OLDPWD=/tmp PYTHONPATH=/Users/pwilson/src/psh python -m psh -c 'echo "[$OLDPWD]"; cd - >/dev/null && pwd' 2>&1
echo -n "bash bogus OLDPWD: "; env -u PWD OLDPWD=/nonexistent/q /opt/homebrew/bin/bash -c 'echo "[$OLDPWD]"; cd -; echo rc=$?' 2>&1 | tr '\n' ' '; echo
echo -n "psh  bogus OLDPWD: "; env -u PWD OLDPWD=/nonexistent/q PYTHONPATH=/Users/pwilson/src/psh python -m psh -c 'echo "[$OLDPWD]"; cd -; echo rc=$?' 2>&1 | tr '\n' ' '; echo
echo "=== stale PWD: cd .. wrong target? ==="
mkdir -p a/b c/d; cd a/b
echo -n "bash: "; env -u OLDPWD PWD=$PWD/../../c/d /opt/homebrew/bin/bash -c 'cd ..; pwd; ls' | tr '\n' ' '; echo
echo -n "psh:  "; env -u OLDPWD PWD=$PWD/../../c/d PYTHONPATH=/Users/pwilson/src/psh python -m psh -c 'cd ..; pwd; ls' 2>&1 | tr '\n' ' '; echo
echo -n "psh fabricated absolute: "; env -u OLDPWD PWD=$(cd ../../c/d && pwd) PYTHONPATH=/Users/pwilson/src/psh python -m psh -c 'echo $PWD; cd ..; pwd; touch marker; ls' 2>&1 | tr '\n' ' '; echo; ls -R "$(cd ../.. && pwd)" | tr '\n' ' '; echo
echo "=== funsub / trap -P ==="
B -c 'echo ${ echo fs; }; echo "[${ }]"; echo rc=$?' 2>&1 | tr '\n' ' '; echo
B -c 'trap -P' 2>&1; echo "rc=$?"; B -c 'trap -p -P INT' 2>&1; echo "rc=$?"; B -c 'trap "echo x" INT; trap -P INT' 2>&1; echo "rc=$?"
