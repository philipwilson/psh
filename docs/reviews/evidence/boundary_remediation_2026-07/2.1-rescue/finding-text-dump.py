"""Condition-2 harness leg: dump finding TEXTS per case per analysis mode.

SHA-portable: run from a psh tree root; writes JSON {case: {mode: [issue
lines]}} to the path given as argv[1]. A separate differ compares two dumps
as MULTISETS per case+mode — base-present-but-tip-absent texts are LOSSES
(blocker-grade unless named intentional); tip-only texts are gains.
"""
import json
import os
import subprocess
import sys

ROOT = os.getcwd()
OUT = sys.argv[1]

SHAPES = [
    ("operand-:-", 'echo "${x:-$(echo $y)}"'),
    ("operand-:+", 'echo "${x:+$(echo $y)}"'),
    ("operand--", 'echo "${x-$(echo $y)}"'),
    ("operand-:?", 'echo "${x:?$(echo $y)}"'),
    ("operand-replace", 'echo "${x/$(echo $y)/z}"'),
    ("operand-plainvar", 'echo "${x:-$y}"'),
    ("operand-backtick", 'echo "${x:-`echo $y`}"'),
    ("assign-value", 'FOO=$(echo $y)'),
    ("assign-plainvar", 'FOO=$y'),
    ("redirect-target", 'echo hi > $(echo $y).log'),
    ("redirect-plain", 'echo hi > $y.log'),
    ("for-item", 'for i in $(echo $y); do :; done'),
    ("case-subject", 'case "$(echo $y)" in a) :;; esac'),
    ("arith-template", 'echo "$(( $(echo $y) ))"'),
    ("subscript-template", 'a[$(echo $y)]=v'),
    ("cmd-arg", 'echo $(echo $y)'),
    ("redirect-only", '>/etc/passwd'),
    ("for-subject-sub", 'for i in $(echo hi); do :; done'),
    ("case-subject-sub", 'case "$(echo hi)" in a) :;; esac'),
]

MODES = ["--validate", "--lint", "--security"]


def issue_lines(mode, stdout):
    out = []
    for line in stdout.splitlines():
        if mode == "--security" and line.strip().startswith("•"):
            out.append(line.strip())
        elif mode == "--validate" and line.strip().startswith("["):
            out.append(line.strip())
        elif mode == "--lint" and line.startswith("["):
            out.append(line.strip())
    return out


def run(mode, args):
    r = subprocess.run([sys.executable, "-m", "psh", mode, *args],
                       capture_output=True, text=True, timeout=60, cwd=ROOT)
    return issue_lines(mode, r.stdout)


dump = {"__tree__": ROOT}
for label, src in SHAPES:
    dump[label] = {m: run(m, ["-c", src]) for m in MODES}

examples = sorted(
    f for f in os.listdir(os.path.join(ROOT, "examples")) if f.endswith(".sh")
)
for ex in examples:
    dump[f"example:{ex}"] = {m: run(m, [os.path.join("examples", ex)])
                             for m in MODES}

with open(OUT, "w") as f:
    json.dump(dump, f, indent=1, sort_keys=True)
print(f"dumped {len(dump)-1} cases from {ROOT}")
