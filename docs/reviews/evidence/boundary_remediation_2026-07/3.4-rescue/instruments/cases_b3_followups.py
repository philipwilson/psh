# A8 batch 3 — Q-axis redesign (define fn BEFORE posix), R1 destination
# semantics, and the confounder isolated as its own cell.

CASES = [
    # ---- the CONFOUNDER found in b2 (out-of-charter; isolate + record) -----
    ("X1", "CONFOUNDER: defining a fn named after a special builtin in posix mode",
     'set -o posix; eval(){ echo FN; }; echo "rc=$?"'),
    ("X2", "same, non-posix (control)",
     'eval(){ echo FN; }; echo "rc=$?"'),
    ("X3", "fn defined BEFORE posix, then posix turned on: fn survives?",
     'eval(){ echo FN; }; set -o posix; eval "echo SPECIAL"'),

    # ---- Q axis, redesigned: define the function BEFORE flipping ----------
    ("Q1b", "already-ON (fn predefined), side effect rewrites POSIXLY_CORRECT",
     'eval(){ echo FN; }; set -o posix; A=$((POSIXLY_CORRECT=1)) eval "echo SPECIAL"'),
    ("Q3b", "flip-OFF attempt via command-sub unset (subshell: must NOT flip off)",
     'eval(){ echo FN; }; POSIXLY_CORRECT=1; '
     'A=$(unset POSIXLY_CORRECT; echo x) eval "echo SPECIAL"'),
    ("Q6", "is flip-OFF reachable from a prefix expansion at all? (arith cannot unset)",
     'eval(){ echo FN; }; POSIXLY_CORRECT=1; '
     'A=$((POSIXLY_CORRECT=0)) eval "echo SPECIAL"; '
     'echo "pc=[${POSIXLY_CORRECT-UNSET}]"; '
     'shopt -qo posix && echo posix-ON || echo posix-OFF'),
    ("Q7", "POSIXLY_CORRECT=0 name-level prefix still flips ON (presence counts)",
     'eval(){ echo FN; }; unset POSIXLY_CORRECT; '
     'POSIXLY_CORRECT=0 eval "echo SPECIAL"'),

    # ---- R1 destination semantics: posix + special builtin + redirect error
    ("R4", "PRE-SET posix, special builtin, redirect error: shell exits?",
     'set -o posix; A=1 eval ":" > /nonexistent_dir_xyz/f; echo AFTER'),
    ("R5", "NON-posix, special builtin, redirect error: shell continues",
     'A=1 eval ":" > /nonexistent_dir_xyz/f; echo AFTER'),
    ("R6", "PRE-SET posix, REGULAR builtin, redirect error: continues",
     'set -o posix; A=1 pwd > /nonexistent_dir_xyz/f; echo AFTER'),
    ("R1b", "flip-in-prefix + special builtin + redirect error (EXIT-trap probe)",
     'trap \'echo "TRAP pc=[${POSIXLY_CORRECT-UNSET}] A=[${A-UNSET}]"\' EXIT; '
     'unset POSIXLY_CORRECT A; '
     'A=$((POSIXLY_CORRECT=1)) eval ":" > /nonexistent_dir_xyz/f; echo AFTER'),

    # ---- more special-builtin targets under a mid-prefix flip --------------
    ("D11", "fn shadowing 'set'",
     'set(){ echo FN; }; A=$((POSIXLY_CORRECT=1)) set -- x y; echo "1=[$1]"'),
    ("D12", "fn shadowing 'shift'",
     'shift(){ echo FN; }; set -- a b c; A=$((POSIXLY_CORRECT=1)) shift; '
     'echo "1=[$1]"'),
    ("D13", "fn shadowing 'readonly'",
     'readonly(){ echo FN; }; unset RV; A=$((POSIXLY_CORRECT=1)) readonly RV=1; '
     'RV=2 2>/dev/null; echo "RV=[$RV]"'),
    ("D14", "fn shadowing 'exec' (is_exec_special path)",
     'exec(){ echo FN; }; A=$((POSIXLY_CORRECT=1)) exec /bin/echo EXECED; '
     'echo AFTER'),
    ("D15", "fn shadowing '.' (source)",
     'printf "echo SOURCED\\n" > tmp/a8/src_xyz.sh; .(){ echo FN; } 2>/dev/null; '
     'A=$((POSIXLY_CORRECT=1)) . tmp/a8/src_xyz.sh'),
    ("D16", "fn shadowing 'break' inside a loop",
     'break(){ echo FN; }; for i in 1 2 3; do '
     'A=$((POSIXLY_CORRECT=1)) break; done; echo "i=[$i]"'),
    ("D17", "fn shadowing 'return' inside a function",
     'return(){ echo FN; }; g(){ A=$((POSIXLY_CORRECT=1)) return; echo NOTREACHED; }; '
     'g; echo "rc=$?"'),
    ("D18", "'command' prefix + flip (command bypasses functions anyway)",
     'eval(){ echo FN; }; A=$((POSIXLY_CORRECT=1)) command eval "echo SPECIAL"'),
    ("D19", "flip + builtin 'builtin' prefix",
     'eval(){ echo FN; }; A=$((POSIXLY_CORRECT=1)) builtin eval "echo SPECIAL"'),
]
