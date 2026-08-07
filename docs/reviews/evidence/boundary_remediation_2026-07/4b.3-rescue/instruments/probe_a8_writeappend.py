"""A8 — the exact shape of the flipped pin `-s x; -w F; -a F`, vs bash.
(Reconstructed instrument; re-run regenerates a8_writeappend.txt.)"""
import sys
sys.path.insert(0, '.')
from _common_header import BASH, PSH, banner, shell_run  # noqa

banner()
SCRIPT = 'history -s x\nhistory -w $D/wa.txt\nhistory -a $D/wa.txt\nexit\n'
for name, seed in [("the pin's shape", None),
                   ("with a seeded HISTFILE", ['S1', 'S2'])]:
    res = {}
    for label, argv in (('bash', BASH), ('psh ', PSH)):
        _, _, _, extra = shell_run(argv, SCRIPT, seed=seed,
                                   named={'wa.txt': []})
        res[label.strip()] = extra['wa.txt']
    print(f"  -s x; -w OTHER; -a OTHER  ({name})")
    print(f"      bash OTHER={res['bash']}")
    print(f"      psh  OTHER={res['psh']}")
    print(f"      => {'MATCH' if res['bash'] == res['psh'] else 'DIVERGE'}\n")
