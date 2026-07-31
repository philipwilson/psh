#!/usr/bin/env python3
"""CONFIRMATION (1) for the integrator: do ALL SIX pin spellings reach the
SINGLE consumption chokepoint, on BOTH parsers?

INSTRUMENT (not rc inference): patch ``SourceProcessor._report_syntax_error``
— the method the ``except ParseError`` clause and the accumulator trial-parse
path both call with the live error OBJECT — and record, per spelling:
  * the concrete exception TYPE,
  * ``is_substitution_origin(err)`` (the typed producer contract),
  * WHICH of the two paths reported it (stack frame name).
A spelling that never appears has not reached the chokepoint.
"""
import os
import sys
import traceback

sys.path.insert(0, "/Users/pwilson/src/psh-r2-4")

from psh.parser.recursive_descent.helpers import is_substitution_origin  # noqa: E402
from psh.scripting.source_processor import SourceProcessor  # noqa: E402

RECORDS = []
_orig_report = SourceProcessor._report_syntax_error


def _spy(self, error, input_source, start_line, source_text=None):
    caller = "?"
    for fr in traceback.extract_stack()[::-1]:
        if fr.name not in ("_spy",):
            caller = fr.name
            break
    RECORDS.append({
        "type": type(error).__name__,
        "sub_origin": is_substitution_origin(error),
        "path": caller,
    })
    return _orig_report(self, error, input_source, start_line,
                        source_text=source_text)


SourceProcessor._report_syntax_error = _spy

SPELLINGS = {
    "1_cmdsub":            "echo $(if)",
    "2_procsub":           "cat <(if)",
    "3_param_default":     "x=set; echo ${x:-$(if)}",
    "4_arith":             "echo $(( $(if) + 1 ))",
    "5_subscript_read":    "a=(1 2); echo ${a[$(if)]}",
    "6_subscript_assign":  "a[$(if)]=v",
    # frame-borne variants (the eval half of the fix)
    "7_eval_cmdsub":       "eval 'echo $(if)'",
    "8_eval_procsub":      "eval 'cat <(if)'",
    # CONTROL: a plain syntax error must arrive with sub_origin=False
    "C_plain_control":     "if",
}


def main():
    from psh.shell import Shell
    for parser_name in ("rd", "combinator"):
        print("=" * 70)
        print("PARSER:", parser_name)
        for label, script in SPELLINGS.items():
            RECORDS.clear()
            sh = Shell(norc=True)
            sh.state.parser_type = parser_name
            try:
                sh.state.options['parser'] = parser_name
            except Exception:
                pass
            devnull = open(os.devnull, "w")
            real_err, sys.stderr = sys.stderr, devnull
            try:
                rc = sh.run_command(script)
            except SystemExit as e:
                rc = e.code
            finally:
                sys.stderr = real_err
                devnull.close()
                try:
                    sh.close()          # release the F2 process lease
                except Exception:
                    pass
            if not RECORDS:
                print("  %-20s rc=%-3s  *** NEVER REACHED CHOKEPOINT ***"
                      % (label, rc))
            for r in RECORDS:
                print("  %-20s rc=%-3s type=%-24s sub_origin=%-5s via=%s"
                      % (label, rc, r["type"], r["sub_origin"], r["path"]))


if __name__ == "__main__":
    main()
