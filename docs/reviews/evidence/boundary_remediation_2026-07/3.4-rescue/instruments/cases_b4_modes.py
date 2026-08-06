# A8 batch 4 — the MODE/PARSER axis subset (run under -c, script, stdin,
# and under both parsers). Deliberately small and signature-focused.

CASES = [
    ("M-S1", "signature: arith flip, fn shadows special builtin",
     'eval(){ echo FN; }; A=$((POSIXLY_CORRECT=1)) eval "echo BUILTIN-PATH"'),
    ("M-S2", "signature: := flip, fn shadows special builtin",
     'unset POSIXLY_CORRECT; eval(){ echo FN; }; '
     'A=${POSIXLY_CORRECT:=1} eval "echo BUILTIN-PATH"'),
    ("M-S3", "name-level control (shipped-correct)",
     'eval(){ echo FN; }; POSIXLY_CORRECT=1 eval "echo BUILTIN-PATH"'),
    ("M-P1", "prefix persistence of the flipping command's own prefix",
     'unset POSIXLY_CORRECT A; A=$((POSIXLY_CORRECT=1)) eval ":"; '
     'echo "A=[${A-UNSET}]"'),
    ("M-C7a", "carry #7: RANDOM=1 b=$RANDOM external",
     'RANDOM=1 b=$RANDOM printenv b'),
    ("M-C7c", "carry #7: RANDOM=1 b=$RANDOM builtin-visible",
     'RANDOM=1 b=$RANDOM eval \'echo "b=[$b]"\''),
    ("M-T1", "left-to-right visibility (must-not-flip)",
     'unset A B; A=1 B=$A eval \'echo "B=[$B]"\''),
    ("M-T5", "arith write read by a later prefix (must-not-flip)",
     'unset Z; A=$((Z=7)) B=$Z eval \'echo "B=[$B]"\''),
    ("M-D7", "not-found: rc + side-effect persistence",
     'unset POSIXLY_CORRECT; A=$((POSIXLY_CORRECT=1)) nosuchcmd_xyz 2>/dev/null; '
     'echo "rc=$?"; shopt -qo posix && echo posix-ON || echo posix-OFF'),
    ("M-K11", "side effect in the LAST prefix still flips",
     'eval(){ echo FN; }; B=2 C=3 A=$((POSIXLY_CORRECT=1)) eval "echo B"'),
]
