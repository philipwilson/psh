# A8 batch 5 — readonly x staging-route asymmetry (found via the ALT-2
# must-not-flip failure). Is the set_temp_env_var readonly-UNSET gap already
# observable at BASE, independent of slot 3.4's reorder?

CASES = [
    ("RO1", "readonly+UNSET, FUNCTION target: is the assignment refused?",
     'readonly RX 2>/dev/null; f(){ echo "RX=[${RX-UNSET}]"; }; RX=1 f; '
     'echo "rc=$?"'),
    ("RO2", "readonly+SET, FUNCTION target",
     'RX=keep; readonly RX; f(){ echo "RX=[${RX-UNSET}]"; }; RX=1 f; '
     'echo "rc=$?"'),
    ("RO3", "readonly+UNSET, BUILTIN target (layer route)",
     'readonly RX 2>/dev/null; RX=1 eval \'echo "RX=[${RX-UNSET}]"\'; '
     'echo "rc=$?"'),
    ("RO4", "readonly+UNSET, EXTERNAL target (layer route)",
     'readonly RX 2>/dev/null; RX=1 /bin/sh -c \'echo "RX=[${RX-UNSET}]"\'; '
     'echo "rc=$?"'),
    ("RO5", "readonly+UNSET POSIXLY_CORRECT blocks flip (the R3 pin shape)",
     'readonly POSIXLY_CORRECT 2>/dev/null; eval(){ echo fn; }; '
     '{ POSIXLY_CORRECT=1 eval "echo builtin-ran"; } 2>/dev/null'),
    ("RO6", "readonly+UNSET POSIXLY_CORRECT, FUNCTION target after it",
     'readonly POSIXLY_CORRECT 2>/dev/null; f(){ echo FN; }; '
     '{ POSIXLY_CORRECT=1 f; } 2>/dev/null; echo "rc=$?"'),
]
