"""Round-2 item-4 follow-up: RE-VERIFY every conversion with SEPARATE
stdout / stderr / rc comparison.

Round 1's probes used `b=$(bash -c "$cmd" 2>&1)` — which MERGES the two
streams and ignores the exit status. That is exactly how the `disown --help`
error got through: both shells exit 2, and merging streams hides that bash's
text is on stdout while psh's is on stderr. This harness compares all three
channels independently.
"""
import subprocess, sys

BASH = "/opt/homebrew/bin/bash"
PSH = [sys.executable, "-m", "psh"]

CASES = [
    ("arith substring literal",    'str="hello world"; echo "${str:3:4}"'),
    ("arith substring computed",   'str="hello world"; echo "${str:$((2+1)):$((2*2))}"'),
    ("arith offset/len literal",   'text="abcdefghijk"; echo "${text:4:4}"'),
    ("arith offset/len computed",  'text="abcdefghijk"; start=2; len=3; echo "${text:$((start*2)):$((len+1))}"'),
    ("case ^",                     'TEXT="hello world"; echo "${TEXT^}"'),
    ("case ^^",                    'TEXT="hello world"; echo "${TEXT^^}"'),
    ("case ,",                     'TEXT="HELLO WORLD"; echo "${TEXT,}"'),
    ("case ,,",                    'TEXT="HELLO WORLD"; echo "${TEXT,,}"'),
    ("c-style for + array idx",    'arr=(first second third); for ((i=0; i<${#arr[@]}; i++)); do echo "Index $i: ${arr[i]}"; done'),
    ("large array 100",            'arr=(); for ((i=0; i<100; i++)); do arr[i]="element_$i"; done; echo ${#arr[@]}'),
    ("break 2",                    'i=0; while [ $i -lt 5 ]; do j=0; while [ $j -lt 5 ]; do if [ $i -eq 2 ] && [ $j -eq 2 ]; then break 2; fi; echo "i=$i j=$j"; j=$((j+1)); done; i=$((i+1)); done; echo done'),
    ("array elem quoting",         'ARR=("first element" "second element"); echo "${ARR[0]}" "${ARR[1]}"'),
    ("array assign splitting",     'VAR="one two three"; ARR=($VAR); echo "${ARR[0]}" "${ARR[1]}" "${ARR[2]}"'),
    ("return outside function",    'return 5'),
    ("readonly -f redefine",       'myfunc() { echo "test"; }; readonly -f myfunc; myfunc() { echo "new"; }; echo "redef_rc=$?"; myfunc'),
    ("disown --help",              'disown --help'),
]

def run(argv, cmd):
    r = subprocess.run(argv + ["-c", cmd], capture_output=True, timeout=30)
    return r.stdout, r.stderr, r.returncode

print(f"{'case':<28} {'stdout':<8} {'stderr':<8} {'rc':<8} verdict")
print("-" * 72)
for name, cmd in CASES:
    bo, be, brc = run([BASH], cmd)
    po, pe, prc = run(PSH, cmd)
    so = "SAME" if bo == po else "DIFF"
    se = "SAME" if be == pe else "DIFF"
    src = "SAME" if brc == prc else "DIFF"
    verdict = "IDENTICAL" if (so, se, src) == ("SAME",)*3 else "DIVERGES"
    print(f"{name:<28} {so:<8} {se:<8} {src:<8} {verdict}")
    if verdict == "DIVERGES":
        print(f"    bash: rc={brc} out={bo[:70]!r} err={be[:70]!r}")
        print(f"    psh : rc={prc} out={po[:70]!r} err={pe[:70]!r}")
