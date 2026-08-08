"""A7e — where does `-s` sit in bash's fixed internal order relative to the
file op?  `-sw FILE STORED` decides it: store-then-write would leave STORED in
FILE.  (Reconstructed instrument; re-run regenerates a7e_storeorder.txt.)"""
import sys
sys.path.insert(0, '.')
from _common_header import BASH, banner, listing, shell_run  # noqa

banner()
for spec, note in [
    ('-sw $D/other STORED', 'store-then-write => other CONTAINS STORED'),
    ('-sa $D/other STORED', 'store-then-append => other CONTAINS STORED'),
    ('-s STORED', 'control'),
    ('-w $D/other', 'control'),
]:
    script = f'history {spec}\nhistory\nexit\n'
    out, _, _, extra = shell_run(BASH, script, seed=['S1', 'S2', 'S3'],
                                 named={'other': []})
    print(f"  history {spec}")
    print(f"      mem   ={listing(out)}")
    print(f"      other ={extra['other']}")
    print(f"      ({note})\n")
