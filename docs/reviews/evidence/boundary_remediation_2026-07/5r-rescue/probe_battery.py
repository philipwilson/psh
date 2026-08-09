#!/usr/bin/env python3
"""5R rider probe battery: printf %a/%A precision + '#' flag vs bash.

Runs a fixed grid of (format, args) cells through BOTH:
  - the oracle: PATH bash (/opt/homebrew/bin/bash 5.2.26 — NEVER /bin/bash)
  - psh:        [sys.executable, -m, psh] with cwd = the tree under test

and reports stdout/rc per cell with a DIFF flag.  Usage:

    python tmp/5r-probes/probe_battery.py <psh-tree-root> <label>

The label ('base' / 'tip') names the transcript:
    tmp/5r-probes/transcript-<label>.txt
"""
import subprocess
import sys

BASH = '/opt/homebrew/bin/bash'

# ---------------------------------------------------------------------------
# The grid.  Every format gets '\n' appended by the runner.
# Cells marked TIE probe the libc rounding mode (half-even vs half-up).
GRID = [
    # -- %a precision: the headline defect (%.2a full-precision vs 0x1.92p+1)
    ('%a', ['3.14']),
    ('%.0a', ['3.14']),
    ('%.1a', ['3.14']),
    ('%.2a', ['3.14']),
    ('%.3a', ['3.14']),
    ('%.13a', ['3.14']),
    ('%.20a', ['3.14']),
    ('%a', ['2']),
    ('%.0a', ['2']),
    ('%.2a', ['2']),
    ('%.0a', ['1.9999999999']),
    ('%.0a', ['0x1.fp0']),
    ('%.1a', ['0x1.ffp0']),
    # -- rounding ties (TIE): distinguish half-even from half-up
    ('%.1a', ['0x1.08p+0']),   # tie, even keep -> 0x1.0p+0 under half-even
    ('%.1a', ['0x1.18p+0']),   # tie, odd  up   -> 0x1.2p+0 either mode
    ('%.1a', ['0x1.28p+0']),   # tie, even keep -> 0x1.2p+0 under half-even
    ('%.1a', ['0x1.38p+0']),   # tie, odd  up   -> 0x1.4p+0 either mode
    ('%.2a', ['0x1.118p+0']),
    ('%.2a', ['0x1.128p+0']),
    ('%.1a', ['0x1.081p+0']),  # just past tie: must round up
    # -- zero / signed zero / negatives
    ('%a', ['0']),
    ('%.2a', ['0']),
    ('%.0a', ['0']),
    ('%a', ['-0']),
    ('%.2a', ['-3.14']),
    # -- extremes and subnormals (platform-divergence watch: glibc vs BSD)
    ('%a', ['1e308']),
    ('%.2a', ['1e308']),
    ('%a', ['2.2250738585072014e-308']),
    ('%a', ['5e-324']),
    ('%a', ['1e-310']),
    ('%.2a', ['5e-324']),
    # -- inf / nan
    ('%a', ['inf']),
    ('%a', ['-inf']),
    ('%a', ['nan']),
    ('%.2a', ['inf']),
    # -- %A uppercase
    ('%A', ['3.14']),
    ('%.2A', ['3.14']),
    ('%A', ['inf']),
    ('%A', ['nan']),
    ('%A', ['-0']),
    ('%#A', ['2']),
    ('%.0A', ['1.9999999999']),
    # -- '#' flag on %a/%A
    ('%#a', ['2']),
    ('%#a', ['3.14']),
    ('%#.0a', ['3.14']),
    ('%#.0a', ['2']),
    ('%#a', ['0']),
    ('%#.2a', ['2']),
    # -- '#' flag on the other float conversions
    ('%#.0f', ['3']),
    ('%#.0f', ['3.7']),
    ('%#.0e', ['3']),
    ('%#f', ['3']),
    ('%#g', ['3']),
    ('%#g', ['3.14']),
    ('%#.3g', ['3.14159']),
    ('%#.0g', ['3']),
    ('%#.10g', ['3.14']),
    ('%#G', ['0.0001234']),
    ('%#g', ['123456789']),
    # -- width / zero flag / sign flags with %a (prefix-aware padding)
    ('%20a|', ['3.14']),
    ('%-20a|', ['3.14']),
    ('%020a', ['3.14']),
    ('%020.2a', ['3.14']),
    ('%020a', ['-3.14']),
    ('%020A', ['3.14']),
    ('%+a', ['3.14']),
    ('% a', ['3.14']),
    ('%+.2A', ['3.14']),
    ('%#020.3a', ['3.14']),
    ('%20.2a|', ['3.14']),
    # -- zero flag with non-finite values (C: 0 flag ignored, space pad)
    ('%010f', ['inf']),
    ('%010a', ['inf']),
    ('%010.2f', ['nan']),
    ('%010e', ['-inf']),
    ('%#a', ['inf']),
    ('%+a', ['inf']),
    ('% 10a', ['nan']),
    # -- length modifier ignored (bash accepts %La)
    ('%.2La', ['3.14']),
    # -- decimal-string inputs exercising the mantissa path
    ('%.2a', ['0.1']),
    ('%.4a', ['0.1']),
    ('%a', ['0.1']),
    ('%.2a', ['100']),
    ('%.1a', ['0.375']),
]


def sh_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def run_one(cmd_argv, shell_cmd):
    p = subprocess.run(cmd_argv + ['-c', shell_cmd],
                       capture_output=True, text=True, timeout=30)
    return p.stdout, p.stderr, p.returncode


def main():
    if len(sys.argv) != 3:
        sys.exit('usage: probe_battery.py <psh-tree-root> <label>')
    tree, label = sys.argv[1], sys.argv[2]

    diffs = 0
    lines = []
    lines.append(f'# 5R probe battery — label={label} tree={tree}')
    lines.append(f'# oracle: {BASH}')
    v = subprocess.run([BASH, '--version'], capture_output=True, text=True)
    lines.append('# ' + v.stdout.splitlines()[0])
    lines.append(f'# cells: {len(GRID)}')
    lines.append('')

    for fmt, args in GRID:
        shell_cmd = ('printf ' + sh_quote(fmt + '\\n') + ' '
                     + ' '.join(sh_quote(a) for a in args))
        b_out, b_err, b_rc = run_one([BASH], shell_cmd)
        p = subprocess.run([sys.executable, '-m', 'psh', '-c', shell_cmd],
                           capture_output=True, text=True, timeout=30,
                           cwd=tree)
        p_out, p_err, p_rc = p.stdout, p.stderr, p.returncode
        same = (b_out == p_out) and (b_rc == p_rc)
        tag = 'SAME' if same else 'DIFF'
        if not same:
            diffs += 1
        lines.append(f'[{tag}] fmt={fmt!r} args={args!r}')
        lines.append(f'    bash: out={b_out!r} rc={b_rc}'
                     + (f' err={b_err!r}' if b_err else ''))
        if not same:
            lines.append(f'    psh : out={p_out!r} rc={p_rc}'
                         + (f' err={p_err!r}' if p_err else ''))
        elif p_err:
            lines.append(f'    psh : err={p_err!r}')

    lines.append('')
    lines.append(f'# TOTAL cells={len(GRID)} DIFF={diffs}')
    report = '\n'.join(lines) + '\n'
    out_path = f'tmp/5r-probes/transcript-{label}.txt'
    with open(out_path, 'w') as f:
        f.write(report)
    print(report[-2000:])
    print(f'written: {out_path}')


if __name__ == '__main__':
    main()
