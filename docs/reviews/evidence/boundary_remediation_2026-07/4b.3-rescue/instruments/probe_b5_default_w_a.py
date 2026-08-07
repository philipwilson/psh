"""b5 (R4-1) — the DEFAULT-file `-w` then `-a` face, both shells, with the
`-a; -a` control that keeps the claim from over-generalising.
(Reconstructed; regenerates b5_default_w_a.txt.)"""
import sys
sys.path.insert(0, '.')
from _common_header import BASH, PSH, banner, shell_run  # noqa

banner()
for name, script, seed in [
    ("-s x; -w (default); -a (default)",
     'history -s x\nhistory -w\nhistory -a\nexit\n', None),
    ("-s x; -w; -a  with a seeded HISTFILE",
     'history -s x\nhistory -w\nhistory -a\nexit\n', ['S1', 'S2']),
    ("typed; -w; -a (default)",
     'true typed1\nhistory -w\nhistory -a\nexit\n', ['S1']),
    ("CONTROL -s x; -a; -a (no -w)",
     'history -s x\nhistory -a\nhistory -a\nexit\n', None),
]:
    _, _, b, _ = shell_run(BASH, script, seed=seed)
    _, _, p, _ = shell_run(PSH, script, seed=seed)
    print(f"  {name}")
    print(f"      bash HISTFILE={b}")
    print(f"      psh  HISTFILE={p}")
    print(f"      => {'MATCH' if b == p else 'DIVERGE'}\n")
