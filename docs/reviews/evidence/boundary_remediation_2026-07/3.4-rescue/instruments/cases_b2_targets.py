# A8 batch 2 — resolution TARGET KIND, side-effect TARGET, carry #7,
# not-found / redirection / temp-env-visibility / POSIX-direction axes.

CASES = [
    # ---- D: resolution TARGET KIND with the posix-flipping side effect -----
    ("D1", "target = plain FUNCTION (no builtin shadow): fn must still win",
     'f(){ echo FN; }; A=$((POSIXLY_CORRECT=1)) f'),
    ("D2", "target = fn shadowing SPECIAL builtin (the signature shape)",
     'eval(){ echo FN; }; A=$((POSIXLY_CORRECT=1)) eval "echo SPECIAL"'),
    ("D3", "target = fn shadowing REGULAR builtin (posix does NOT reorder)",
     'unalias -a 2>/dev/null; pwd(){ echo FN; }; A=$((POSIXLY_CORRECT=1)) pwd'),
    ("D4", "target = SPECIAL builtin, no function shadow",
     'unset A; A=$((POSIXLY_CORRECT=1)) eval "echo SPECIAL"'),
    ("D5", "target = REGULAR builtin, no function shadow",
     'A=$((POSIXLY_CORRECT=1)) pwd >/dev/null && echo RAN'),
    ("D6", "target = EXTERNAL",
     'A=$((POSIXLY_CORRECT=1)) /bin/echo EXT'),
    ("D7", "target = NOT FOUND: rc + side-effect persistence + posix state",
     'unset POSIXLY_CORRECT; A=$((POSIXLY_CORRECT=1)) nosuchcmd_xyz; '
     'echo "rc=$?"; echo "pc=[${POSIXLY_CORRECT-UNSET}]"; '
     'shopt -qo posix && echo posix-ON || echo posix-OFF'),
    ("D8", "target = fn shadowing special builtin ':' ",
     ':(){ echo FN; } 2>/dev/null; A=$((POSIXLY_CORRECT=1)) : ; echo "rc=$?"'),
    ("D9", "target = fn shadowing 'export' (special)",
     'export(){ echo FN; }; unset V; A=$((POSIXLY_CORRECT=1)) export V=1; '
     'echo "V=[${V-UNSET}]"'),
    ("D10", "target = fn shadowing 'unset' (special)",
     'W=keep; unset(){ echo FN; }; A=$((POSIXLY_CORRECT=1)) unset W; '
     'echo "W=[${W-UNSET}]"'),

    # ---- persistence of the command's OWN prefix per target kind -----------
    ("P1", "flip + special builtin: does THAT command's prefix persist?",
     'unset POSIXLY_CORRECT A; A=$((POSIXLY_CORRECT=1)) eval ":"; '
     'echo "A=[${A-UNSET}]"'),
    ("P2", "flip + fn-shadowed special builtin: prefix persistence",
     'unset POSIXLY_CORRECT A; eval(){ echo FN; }; '
     'A=$((POSIXLY_CORRECT=1)) eval ":"; echo "A=[${A-UNSET}]"'),
    ("P3", "flip + REGULAR builtin: prefix must NOT persist",
     'unset POSIXLY_CORRECT A; A=$((POSIXLY_CORRECT=1)) pwd >/dev/null; '
     'echo "A=[${A-UNSET}]"'),
    ("P4", "flip + FUNCTION: prefix must NOT persist",
     'unset POSIXLY_CORRECT A; f(){ :; }; A=$((POSIXLY_CORRECT=1)) f; '
     'echo "A=[${A-UNSET}]"'),
    ("P5", "flip + EXTERNAL: prefix must NOT persist",
     'unset POSIXLY_CORRECT A; A=$((POSIXLY_CORRECT=1)) /bin/echo x >/dev/null; '
     'echo "A=[${A-UNSET}]"'),
    ("P6", "flip + NOT-FOUND: prefix persistence",
     'unset POSIXLY_CORRECT A; A=$((POSIXLY_CORRECT=1)) nosuchcmd_xyz 2>/dev/null; '
     'echo "A=[${A-UNSET}]"'),

    # ---- POSIX DIRECTION ---------------------------------------------------
    ("Q1", "already-ON, side effect rewrites POSIXLY_CORRECT (no change)",
     'set -o posix; eval(){ echo FN; } 2>/dev/null; '
     'A=$((POSIXLY_CORRECT=1)) eval "echo SPECIAL"'),
    ("Q2", "already-OFF, no side effect (control)",
     'eval(){ echo FN; }; eval "echo SPECIAL"'),
    ("Q3", "flip-OFF attempt: can an expansion UNSET POSIXLY_CORRECT?",
     'POSIXLY_CORRECT=1; eval(){ echo FN; } 2>/dev/null; '
     'A=$(unset POSIXLY_CORRECT; echo x) eval "echo SPECIAL"'),
    ("Q4", "does set +o posix unset POSIXLY_CORRECT? (coupling direction)",
     'POSIXLY_CORRECT=1; set +o posix; echo "pc=[${POSIXLY_CORRECT-UNSET}]"; '
     'shopt -qo posix && echo posix-ON || echo posix-OFF'),
    ("Q5", "readonly POSIXLY_CORRECT blocks the arith flip?",
     'unset POSIXLY_CORRECT; readonly POSIXLY_CORRECT; eval(){ echo FN; }; '
     'A=$((POSIXLY_CORRECT=1)) eval "echo SPECIAL"; echo "rc=$?"'),

    # ---- T: side-effect TARGET (non-posix) ---------------------------------
    ("T1", "later prefix reads earlier prefix (A=1 B=$A) - must SURVIVE",
     'unset A B; A=1 B=$A /bin/echo "B-via-env"; A=1 B=$A eval \'echo "B=[$B]"\''),
    ("T2", "PATH written by a := side effect, external target search",
     'mkdir -p tmp/a8/pd && printf "#!/bin/sh\\necho MINE\\n" > tmp/a8/pd/mycmd_xyz '
     '&& chmod +x tmp/a8/pd/mycmd_xyz; OLD=$PATH; unset PATH; '
     'A=${PATH:=$OLD:'
     '$PWD/tmp/a8/pd} mycmd_xyz; echo "rc=$?"'),
    ("T3", "PATH written by arithmetic (numeric clobber) then external",
     'A=$((PATH=0)) /bin/echo abs-path-still-works; echo "rc=$?"'),
    ("T4", "IFS written by := side effect, seen by a later prefix expansion",
     'set -- a b c; unset IFS; A=${IFS:=-} B="$*" eval \'echo "B=[$B]"\''),
    ("T5", "plain var written by arith, read by a LATER prefix",
     'unset Z; A=$((Z=7)) B=$Z eval \'echo "B=[$B]"\''),
    ("T6", "plain var written by :=, read by a LATER prefix",
     'unset Z; A=${Z:=7} B=$Z eval \'echo "B=[$B]"\''),

    # ---- carry #7: RANDOM in prefix ----------------------------------------
    ("C7a", "RANDOM=1 b=$RANDOM printenv b  (external target)",
     'RANDOM=1 b=$RANDOM printenv b'),
    ("C7b", "RANDOM=1 b=$RANDOM f  (function target)",
     'f(){ echo "b=$b"; }; RANDOM=1 b=$RANDOM f'),
    ("C7c", "RANDOM=1 b=$RANDOM  + regular builtin reading $b",
     'RANDOM=1 b=$RANDOM eval \'echo "b=[$b]"\''),
    ("C7d", "RANDOM=1 b=$RANDOM external, $b-visible via sh -c",
     'RANDOM=1 b=$RANDOM /bin/sh -c \'echo "b=[$b]"\''),
    ("C7e", "does RANDOM=1 prefix persist after an external command?",
     'RANDOM=1 /bin/echo x >/dev/null; r1=$RANDOM; r2=$RANDOM; '
     '[ "$r1" = "$r2" ] && echo SAME || echo DIFFERENT'),
    ("C7f", "RANDOM masking for a function (shipped family, must stay)",
     'f(){ echo "$RANDOM"; }; RANDOM=5 f'),
    ("C7g", "RANDOM=1 b=$RANDOM c=$RANDOM (two later reads)",
     'RANDOM=1 b=$RANDOM c=$RANDOM eval \'echo "b=[$b] c=[$c]"\''),
    ("C7h", "SECONDS in prefix, later prefix reads it",
     'SECONDS=100 b=$SECONDS eval \'echo "b=[$b]"\''),

    # ---- E: temp-env visibility to the command -----------------------------
    ("E1", "flip mid-list: what does a FUNCTION see?",
     'f(){ echo "A=[$A] B=[$B]"; }; unset A B POSIXLY_CORRECT; '
     'A=$((POSIXLY_CORRECT=1)) B=2 f'),
    ("E2", "flip mid-list: what does a special BUILTIN see?",
     'unset A B POSIXLY_CORRECT; '
     'A=$((POSIXLY_CORRECT=1)) B=2 eval \'echo "A=[$A] B=[$B]"\''),
    ("E3", "flip mid-list: what does an EXTERNAL see (env)?",
     'unset A B POSIXLY_CORRECT; '
     'A=$((POSIXLY_CORRECT=1)) B=2 /bin/sh -c \'echo "A=[$A] B=[$B]"\''),
    ("E4", "declare -p of a prefix var inside a special builtin",
     'unset A POSIXLY_CORRECT; A=$((POSIXLY_CORRECT=1)) eval \'declare -p A\''),

    # ---- R: redirection error x resolution timing --------------------------
    ("R1", "redirect fails on a flip-prefixed special builtin",
     'unset POSIXLY_CORRECT; eval(){ echo FN; }; '
     'A=$((POSIXLY_CORRECT=1)) eval ":" > /nonexistent_dir_xyz/f; echo "rc=$?"; '
     'echo "pc=[${POSIXLY_CORRECT-UNSET}]"; '
     'shopt -qo posix && echo posix-ON || echo posix-OFF'),
    ("R2", "redirect fails on a flip-prefixed EXTERNAL",
     'unset POSIXLY_CORRECT A; '
     'A=$((POSIXLY_CORRECT=1)) /bin/echo x > /nonexistent_dir_xyz/f; '
     'echo "rc=$?"; echo "pc=[${POSIXLY_CORRECT-UNSET}]"'),
    ("R3", "redirect fails on a flip-prefixed NOT-FOUND command",
     'unset POSIXLY_CORRECT; '
     'A=$((POSIXLY_CORRECT=1)) nosuchcmd_xyz > /nonexistent_dir_xyz/f; '
     'echo "rc=$?"; echo "pc=[${POSIXLY_CORRECT-UNSET}]"'),
]
