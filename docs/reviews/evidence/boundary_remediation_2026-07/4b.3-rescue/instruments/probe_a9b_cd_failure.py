"""A9b — when the `-d` half of a `-cd` cluster FAILS, does bash still clear, and
what is the rc/message?  (Reconstructed; regenerates a9b_cd_failure.txt.)"""
import sys
sys.path.insert(0, '.')
from _common_header import BASH, banner, listing, rc_of, shell_run  # noqa

banner()
for script, note in [
    ('history -cd 9; echo "RC=$?"; history', 'delete OUT OF RANGE + clear'),
    ('history -cd 1; echo "RC=$?"; history', 'delete valid + clear (control)'),
    ('history -cd 0; echo "RC=$?"; history', 'offset 0 is invalid in both'),
    ('history -d 9; echo "RC=$?"; history', 'delete out of range alone'),
]:
    out, err, _, _ = shell_run(BASH, script + '\nexit\n',
                               seed=['S1', 'S2', 'S3'],
                               histignore='history*:exit:echo*',
                               capture_stderr=True)
    msg = [x for x in err.splitlines() if 'range' in x][:1]
    print(f"  {script}")
    print(f"      bash rc={rc_of(out)} mem={listing(out)} err={msg}")
    print(f"      ({note})\n")
