"""A7d — is `-d` REJECTING combinations, or CONSUMING the cluster remainder as
its option argument (standard getopt)?  `-d1`, `-ad 1` and `-da 1` separate the
two readings.  (Instrument reconstructed from the round's inline run so the
transcript does not outlive its script; re-run regenerates a7d_dopt.txt.)"""
import sys
sys.path.insert(0, '.')
from _common_header import BASH, PSH, banner, listing, rc_of, shell_run  # noqa

banner()
CASES = [
    ('-d 1', 'baseline: delete entry 1'),
    ('-d1', 'attached argument — getopt should accept'),
    ('-cd1', 'cluster + attached arg'),
    ('-ad 1', 'if -d consumes the REMAINDER this is -a then -d 1 => rc 0'),
    ('-da 1', 'if -d consumes the REMAINDER this is -d "a" => invalid => rc 1'),
    ('-ds 1 X', '-d "s" => invalid'),
    ('-sd X 1', '-s wins/returns before -d is applied'),
]
for spec, note in CASES:
    script = f'history {spec}; echo "RC=$?"\nhistory\nexit\n'
    for label, argv in (('bash', BASH), ('psh ', PSH)):
        out, _, _, _ = shell_run(argv, script, seed=['S1', 'S2', 'S3'],
                                 histignore='history*:exit:echo*')
        print(f"  history {spec:10s} {label} rc={rc_of(out)} mem={listing(out)}")
    print(f"  {'':19s} ({note})\n")
