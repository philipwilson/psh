"""
A bare `declare NAME` (no value) inside a function is LOCAL (reappraisal #14 H4).

Regression guard: `declare NAME` / `declare -ATTR NAME` inside a function used
to find and mutate an OUTER-scope variable instead of creating a local shadow,
so `g=glob; f(){ declare g; g=x; }; f` leaked `g=x` to the global. bash treats
`declare NAME` like `local NAME`. Only the no-value forms were affected
(`declare g=val` and `local g` were already correct). Verified vs bash 5.2.
"""

import subprocess
import sys


def run_psh(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True)


def test_bare_declare_shadows_outer():
    r = run_psh('g=glob; f(){ declare g; g=x; }; f; echo "$g"')
    assert r.stdout == "glob\n"


def test_declare_integer_shadows_outer():
    r = run_psh('g=5; f(){ declare -i g; g=3+4; echo "in=$g"; }; f; echo "out=$g"')
    assert r.stdout == "in=7\nout=5\n"


def test_bare_declare_reads_as_unset_local():
    r = run_psh('g=glob; f(){ declare g; echo "[${g}]"; }; f; echo "[$g]"')
    assert r.stdout == "[]\n[glob]\n"


def test_declare_export_is_local_in_function():
    r = run_psh('g=glob; f(){ declare -x g; g=x; }; f; echo "out=$g"')
    assert r.stdout == "out=glob\n"


def test_nested_function_shadows_middle_scope():
    r = run_psh('g=top; f(){ declare g=flvl; gg(){ declare g; g=deep; echo "deep=$g"; }; '
                'gg; echo "f=$g"; }; f; echo "top=$g"')
    assert r.stdout == "deep=deep\nf=flvl\ntop=top\n"


def test_declare_readonly_local_in_function():
    r = run_psh('g=glob; f(){ declare -r g; echo "in=[$g]"; }; f; echo "out=$g"')
    assert r.stdout == "in=[]\nout=glob\n"


# --- Preserved behaviors (must not regress) ---

def test_declare_with_value_still_local():
    r = run_psh('g=glob; f(){ declare g=local; echo "in=$g"; }; f; echo "out=$g"')
    assert r.stdout == "in=local\nout=glob\n"


def test_local_keyword_unchanged():
    r = run_psh('g=glob; f(){ local g; g=x; echo "in=$g"; }; f; echo "out=$g"')
    assert r.stdout == "in=x\nout=glob\n"


def test_declare_g_modifies_global():
    r = run_psh('g=glob; f(){ declare -g g=newglob; }; f; echo "$g"')
    assert r.stdout == "newglob\n"


def test_attribute_accumulation_in_function():
    # declare -u then -l on a declared-but-unset local must accumulate/flip,
    # not reset (bash: -l wins -> lowercase).
    r = run_psh('f(){ declare -u y; declare -l y; y=AbC; echo "$y"; }; f')
    bash = subprocess.run(['bash', '-c', 'f(){ declare -u y; declare -l y; y=AbC; echo "$y"; }; f'],
                          capture_output=True, text=True)
    assert r.stdout == bash.stdout


def test_attribute_added_to_existing_local():
    r = run_psh('f(){ local g=5; declare -i g; g=2+2; echo $g; }; f')
    assert r.stdout == "4\n"


def test_bare_declare_at_top_level_unchanged():
    r = run_psh('g=glob; declare g; echo "$g"; g=x; echo "$g"')
    assert r.stdout == "glob\nx\n"
