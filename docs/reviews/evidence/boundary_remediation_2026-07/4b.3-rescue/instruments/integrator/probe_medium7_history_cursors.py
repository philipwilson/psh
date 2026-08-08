"""Integrator dispatch probe — slot 4B.3 (MEDIUM-7 + carry #32) at base bd13b303.

Three legs, each psh-vs-bash in piped -i mode (history builtins are
interactive-gated; carry #34 says PROMPT_COMMAND doesn't fire piped, but the
history family works piped — that's how carry #32 was originally probed):

  A. cursor conflation: seed file A B C; `history -d 1`; append seedD to
     $HISTFILE via redirect (external write); `history -n`.
     bash: file counter stays 3 → -n adds only seedD (seedC appears ONCE).
     psh:  delete_entry decremented _file_read_len 3→2 → -n re-reads
           seedC (seedC appears TWICE).
  B. `history -s` HISTSIZE bypass: HISTSIZE=3, HISTIGNORE='history *' (so
     the probe's own invocations are never recorded and add_to_history's
     trim never masks the store): 5x `history -s sN`.
     bash: memory capped at 3 (s3 s4 s5). psh: store_entry never caps → 5.
  C. carry #32 counter model: empty file; `echo seedX`; -a; -c; -n.
     bash: -n after -c re-reads NOTHING already consumed (seedX absent
     from final listing). psh: clear_history resets _file_read_len=0 →
     -n re-materializes seedX.
"""
import os
import subprocess
import sys
import tempfile

REPO = '/Users/pwilson/src/psh'
sys.path.insert(0, REPO)
import psh  # noqa: E402
print("DISCRIMINATOR:", psh.__file__)

BASH = ['/opt/homebrew/bin/bash', '--norc', '-i']
PSH = [sys.executable, '-m', 'psh', '--norc', '-i']


def run(argv, script, histfile, extra_env=None):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('HIST', 'PROMPT'))}
    env.update({'HISTFILE': histfile, 'TERM': 'dumb',
                'PYTHONPATH': REPO})
    if extra_env:
        env.update(extra_env)
    p = subprocess.run(argv, input=script.encode(), stdout=subprocess.PIPE,
                       stderr=subprocess.DEVNULL, cwd=REPO, env=env,
                       timeout=20)
    return p.stdout.decode(errors='replace')


def counts(out, tokens):
    # count occurrences as history-listing lines (avoid matching the
    # echoed command output by requiring the leading list-number format)
    res = {}
    for tok in tokens:
        res[tok] = sum(1 for ln in out.splitlines()
                       if ln.strip().split('  ')[-1] == tok
                       and ln.strip()[:1].isdigit())
    return res


def leg_a(argv, label):
    with tempfile.TemporaryDirectory(dir=os.path.join(REPO, 'tmp')) as d:
        hf = os.path.join(d, 'hist')
        with open(hf, 'w') as f:
            f.write('seedA\nseedB\nseedC\n')
        script = ('history -d 1\n'
                  f'echo seedD >> {hf}\n'
                  'history -n\n'
                  'history\n'
                  'exit\n')
        out = run(argv, script, hf)
        c = counts(out, ['seedA', 'seedB', 'seedC', 'seedD'])
        print(f"A {label}: {c}")


def leg_b(argv, label):
    with tempfile.TemporaryDirectory(dir=os.path.join(REPO, 'tmp')) as d:
        hf = os.path.join(d, 'hist')
        open(hf, 'w').close()
        script = ''.join(f'history -s s{i}\n' for i in range(1, 6))
        script += 'history\nexit\n'
        out = run(argv, script, hf,
                  {'HISTSIZE': '3', 'HISTIGNORE': 'history *:history'})
        c = counts(out, [f's{i}' for i in range(1, 6)])
        print(f"B {label}: {c}  (listing lines: "
              f"{sum(1 for ln in out.splitlines() if ln.strip()[:1].isdigit())})")


def leg_c(argv, label):
    with tempfile.TemporaryDirectory(dir=os.path.join(REPO, 'tmp')) as d:
        hf = os.path.join(d, 'hist')
        open(hf, 'w').close()
        script = ('echo seedX\n'
                  'history -a\n'
                  'history -c\n'
                  'history -n\n'
                  'history\n'
                  'exit\n')
        out = run(argv, script, hf)
        c = counts(out, ['echo seedX'])
        print(f"C {label}: 'echo seedX' in final listing: {c['echo seedX']}")


for leg in (leg_a, leg_b, leg_c):
    leg(BASH, 'bash')
    leg(PSH, 'psh ')
    print()
