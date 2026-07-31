#!/usr/bin/env python3
"""CONFIRMATION (1), part 2: the SAME chokepoint census for the REAL
`-c` and script-FILE channels, which reach the parse error through the
CommandAccumulator's trial parse rather than the in-process run_command path.

Runs psh's actual entry point in a subprocess with the spy pre-installed, so
the channel machinery is the real one. One case per invocation.
"""
import os
import subprocess
import sys

ROOT = "/Users/pwilson/src/psh-r2-4"
HERE = os.path.dirname(os.path.abspath(__file__))

SPY = r'''
import sys, traceback
sys.path.insert(0, "%s")
from psh.parser.recursive_descent.helpers import is_substitution_origin
from psh.scripting.source_processor import SourceProcessor
_orig = SourceProcessor._report_syntax_error
def _spy(self, error, input_source, start_line, source_text=None):
    caller = "?"
    for fr in traceback.extract_stack()[::-1]:
        if fr.name != "_spy":
            caller = fr.name
            break
    sys.stdout.write("CHOKEPOINT type=%%s sub_origin=%%s via=%%s\n" %% (
        type(error).__name__, is_substitution_origin(error), caller))
    sys.stdout.flush()
    return _orig(self, error, input_source, start_line, source_text=source_text)
SourceProcessor._report_syntax_error = _spy
from psh.__main__ import main
sys.argv = ["psh"] + sys.argv[1:]
sys.exit(main())
''' % ROOT

SPELLINGS = {
    "1_cmdsub":           "echo $(if)",
    "2_procsub":          "cat <(if)",
    "3_param_default":    "x=set; echo ${x:-$(if)}",
    "4_arith":            "echo $(( $(if) + 1 ))",
    "5_subscript_read":   "a=(1 2); echo ${a[$(if)]}",
    "6_subscript_assign": "a[$(if)]=v",
    "7_eval_cmdsub":      "eval 'echo $(if)'",
    "8_eval_procsub":     "eval 'cat <(if)'",
    "C_plain_control":    "if",
    # MULTI-LINE shapes: these can complete via the CommandAccumulator's
    # trial parse rather than the execution-path parse, so the corpus must
    # cover them before claiming a single raise site suffices.
    "9_golden_heredoc":   ": p1\n: p2\necho $(if) <<EOF\nbody\nEOF",
    "10_multiline_pre":   "echo one\necho two\necho $(if)",
    "11_inside_ifblock":  "if true; then\n  echo $(if)\nfi",
    "12_inside_loop":     "for i in 1 2; do\n  echo $(if)\ndone",
    "13_multiline_eval":  "echo one\neval 'echo $(if)'\necho two",
    "14_cont_line":       "echo \\\n  $(if)",
    # ERROR-KIND axis (round 2). Round 1 held this constant at the
    # unterminated `if` family and therefore only ever exercised ONE of the
    # two consumer sites. These bodies are COMPLETE but ill-formed, so the
    # accumulator's trial parse finishes and they leave by the OTHER exit —
    # which is exactly what the round-1 census could not see.
    "K1_fi_cmdsub":        "echo $(fi)",
    "K2_fi_procsub":       "cat <(fi)",
    "K3_fi_param":         "x=set; echo ${x:-$(fi)}",
    "K4_fi_arith":         "echo $(( $(fi) + 1 ))",
    "K5_fi_subscr_read":   "a=(1 2); echo ${a[$(fi)]}",
    "K6_fi_subscr_asgn":   "a[$(fi)]=v",
    "K7_semi":             "echo $(;)",
    "K8_dsemi":            "echo $(x ;; y)",
    "K9_done":             "echo $(done)",
    "K10_lead_pipe":       "echo $(| x)",
    "K11_fi_eval":         "eval 'echo $(fi)'",
    "K12_fi_multiline":    "echo one\necho $(fi)\necho two",
    "KC_plain_fi_CONTROL": "fi",
}


def main():
    work = os.path.join(HERE, "work-census")
    os.makedirs(work, exist_ok=True)
    runner = os.path.join(work, "spy_runner.py")
    with open(runner, "w") as f:
        f.write(SPY)
    env = dict(os.environ)
    env["PYTHONPATH"] = ROOT
    env.pop("PSH_STRICT_ERRORS", None)

    for parser in ("rd", "combinator"):
        print("=" * 74)
        print("PARSER:", parser)
        for label, script in SPELLINGS.items():
            sf = os.path.join(work, "case.sh")
            with open(sf, "wb") as f:
                f.write((script + "\n").encode())
            for channel in ("c", "file"):
                if channel == "c":
                    argv = [sys.executable, runner, "--parser", parser,
                            "-c", script]
                else:
                    argv = [sys.executable, runner, "--parser", parser, sf]
                r = subprocess.run(argv, capture_output=True, text=True,
                                   cwd=work, env=env, timeout=30)
                hits = [ln for ln in r.stdout.splitlines()
                        if ln.startswith("CHOKEPOINT")]
                if not hits:
                    print("  %-19s [%-4s] rc=%-3s *** NEVER REACHED ***"
                          % (label, channel, r.returncode))
                for h in hits:
                    print("  %-19s [%-4s] rc=%-3s %s"
                          % (label, channel, r.returncode,
                             h[len("CHOKEPOINT "):]))


if __name__ == "__main__":
    main()
