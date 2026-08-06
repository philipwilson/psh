# A8 batch 1 — signature family + side-effect KIND axis.
# Each case: (id, description, script)

CASES = [
    # ---- S: the two signature cells from the brief -------------------------
    ("S1", "arith side effect flips posix; fn shadows special builtin",
     'eval(){ echo FN; }; A=$((POSIXLY_CORRECT=1)) eval "echo BUILTIN-PATH"'),
    ("S2", ":= side effect flips posix; fn shadows special builtin",
     'unset POSIXLY_CORRECT; eval(){ echo FN; }; '
     'A=${POSIXLY_CORRECT:=1} eval "echo BUILTIN-PATH"'),

    # ---- control: NAME-level flip (predecessor R3, already correct) --------
    ("S3", "name-level POSIXLY_CORRECT prefix (shipped-correct control)",
     'eval(){ echo FN; }; POSIXLY_CORRECT=1 eval "echo BUILTIN-PATH"'),
    ("S4", "no side effect at all (control: function must win)",
     'eval(){ echo FN; }; A=1 eval "echo BUILTIN-PATH"'),
    ("S5", "arith with NO posix write (control: function must win)",
     'eval(){ echo FN; }; A=$((Q=1)) eval "echo BUILTIN-PATH"'),

    # ---- K: side-effect KIND ----------------------------------------------
    ("K1", "arith plain assign",
     'eval(){ echo FN; }; A=$((POSIXLY_CORRECT=1)) eval "echo B"'),
    ("K2", "arith += onto unset",
     'eval(){ echo FN; }; A=$((POSIXLY_CORRECT+=1)) eval "echo B"'),
    ("K3", "arith postincrement",
     'eval(){ echo FN; }; A=$((POSIXLY_CORRECT++)) eval "echo B"'),
    ("K4", ":= store nonempty",
     'unset POSIXLY_CORRECT; eval(){ echo FN; }; '
     'A=${POSIXLY_CORRECT:=1} eval "echo B"'),
    ("K5", ":= store EMPTY value (name-level says any value counts)",
     'unset POSIXLY_CORRECT; eval(){ echo FN; }; '
     'A=${POSIXLY_CORRECT:=} eval "echo B"'),
    ("K6", "= store (unset-only) on unset var",
     'unset POSIXLY_CORRECT; eval(){ echo FN; }; '
     'A=${POSIXLY_CORRECT=1} eval "echo B"'),
    ("K7", "command substitution doing the write (SUBSHELL - must NOT flip)",
     'unset POSIXLY_CORRECT; eval(){ echo FN; }; '
     'A=$(POSIXLY_CORRECT=1; echo x) eval "echo B"'),
    ("K8", "command substitution + export (still a subshell)",
     'unset POSIXLY_CORRECT; eval(){ echo FN; }; '
     'A=$(export POSIXLY_CORRECT=1; echo x) eval "echo B"'),
    ("K9", "nested: := whose default runs an arith write",
     'unset POSIXLY_CORRECT Z; eval(){ echo FN; }; '
     'A=${Z:=$((POSIXLY_CORRECT=1))} eval "echo B"'),
    ("K10", "arith side effect in the FIRST of several prefixes",
     'eval(){ echo FN; }; A=$((POSIXLY_CORRECT=1)) B=2 C=3 eval "echo B"'),
    ("K11", "arith side effect in the LAST of several prefixes",
     'eval(){ echo FN; }; B=2 C=3 A=$((POSIXLY_CORRECT=1)) eval "echo B"'),
    ("K12", "arith side effect in the MIDDLE of several prefixes",
     'eval(){ echo FN; }; B=2 A=$((POSIXLY_CORRECT=1)) C=3 eval "echo B"'),
    ("K13", "side effect inside array-subscript arithmetic",
     'unset arr; eval(){ echo FN; }; arr[$((POSIXLY_CORRECT=1))]=v '
     'eval "echo B"'),
    ("K14", "${var:?} / ${var+alt} - no store, must NOT flip",
     'unset POSIXLY_CORRECT; eval(){ echo FN; }; '
     'A=${POSIXLY_CORRECT+set} eval "echo B"'),

    # ---- V: what PERSISTS after the command --------------------------------
    ("V1", "does the arith POSIXLY_CORRECT write persist after the command?",
     'unset POSIXLY_CORRECT; eval(){ echo FN; }; '
     'A=$((POSIXLY_CORRECT=1)) eval ":"; echo "pc=[${POSIXLY_CORRECT-UNSET}]"'),
    ("V2", "does the posix OPTION persist after the command?",
     'unset POSIXLY_CORRECT; eval(){ echo FN; }; '
     'A=$((POSIXLY_CORRECT=1)) eval ":"; '
     'shopt -qo posix && echo posix-ON || echo posix-OFF'),
    ("V3", "does the := store persist after the command?",
     'unset POSIXLY_CORRECT; eval(){ echo FN; }; '
     'A=${POSIXLY_CORRECT:=1} eval ":"; echo "pc=[${POSIXLY_CORRECT-UNSET}]"'),
    ("V4", "does the PREFIX var A persist? (special builtin in posix mode)",
     'unset POSIXLY_CORRECT A; eval(){ echo FN; }; '
     'A=$((POSIXLY_CORRECT=1)) eval ":"; echo "A=[${A-UNSET}]"'),
    ("V5", "baseline: shopt -qo posix reporting works at all",
     'shopt -qo posix && echo posix-ON || echo posix-OFF; set -o posix; '
     'shopt -qo posix && echo posix-ON || echo posix-OFF'),
    ("V6", "prefix persistence after special builtin, posix pre-set (R3 family)",
     'set -o posix; unset A; A=v eval ":"; echo "A=[${A-UNSET}]"'),
    ("V7", "prefix persistence after special builtin, NOT posix",
     'unset A; A=v eval ":"; echo "A=[${A-UNSET}]"'),
]
