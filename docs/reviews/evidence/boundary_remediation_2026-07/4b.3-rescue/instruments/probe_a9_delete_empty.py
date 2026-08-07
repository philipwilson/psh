"""A9 — the `-cd 1` divergence: ORDER, or does bash tolerate an out-of-range
`-d` on an EMPTY history?  (Reconstructed; regenerates a9_delete_empty.txt.)"""
import sys
sys.path.insert(0, '.')
from _common_header import BASH, PSH, banner, listing, rc_of, shell_run  # noqa

banner()
CASES = [
    ('history -c; history -d 1; echo "RC=$?"',
     'plain -d on an EMPTY history: does bash report out-of-range?'),
    ('history -d 9; echo "RC=$?"',
     'plain -d out of range on a NON-empty history'),
    ('history -cd 1; echo "RC=$?"', 'the cluster: rc 0 in bash'),
    ('history -cd 1; echo "RC=$?"; history', 'and what is left in memory?'),
    ('history -dc 1; echo "RC=$?"',
     '-d takes "c" as its argument => invalid offset'),
]
for script, note in CASES:
    print(f"  {script}")
    for label, argv in (('bash', BASH), ('psh ', PSH)):
        out, err, _, _ = shell_run(argv, script + '\nexit\n',
                                   seed=['S1', 'S2', 'S3'],
                                   histignore='history*:exit:echo*',
                                   capture_stderr=True)
        msg = [x for x in err.splitlines() if 'range' in x][:1]
        print(f"      {label} rc={rc_of(out)} mem={listing(out)} err={msg}")
    print(f"      ({note})\n")
