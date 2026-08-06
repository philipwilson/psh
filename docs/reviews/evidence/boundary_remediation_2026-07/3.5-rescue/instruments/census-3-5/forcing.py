"""Per-leg REACHABILITY forcing, on the REAL path (lesson 7: a proof that
cannot fail is not a proof).

Method. ONE injection point inside ``evaluate_arithmetic``'s own try body but
OUTSIDE ``_evaluate_arithmetic_inner``'s try — i.e. exactly the region whose
escaping exceptions the OUTER catch legs are there to handle. The injection is
sentinel-gated (it fires only for an expression containing the sentinel name),
so the rest of the shell — startup, the test corpus, unrelated arithmetic —
runs untouched, and every observation context below reaches the SAME raise
through its own real call chain.

A second injection point (INNER) sits at the top of
``_evaluate_arithmetic_inner``'s try body, to separate "the inner conversion
layer caught it" from "it escaped to the outer legs".

Restore discipline (git checkout is BANNED): cp-backup, patch, run, restore
from the backup, then ASSERT byte-identity by sha256 and drop __pycache__.
The assert runs even if the body raised.
"""
import hashlib
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASH = "/opt/homebrew/bin/bash"
ENV = {**os.environ, "PYTHONPATH": str(ROOT)}
ENV.pop("PSH_STRICT_ERRORS", None)
ENV_STRICT = {**ENV, "PSH_STRICT_ERRORS": "1"}
PSH = [sys.executable, "-m", "psh"]

EVAL = ROOT / "psh" / "expansion" / "arithmetic" / "evaluator.py"

# (anchor line text, indent) -> the injection is placed BEFORE the anchor.
OUTER_ANCHOR = "        if depth >= _MAX_ARITH_RECURSION:"
INNER_ANCHOR = "        # First, expand all shell variables and parameter expansions."

INJECT = (
    "{i}if 'FORCEVE' in expr: raise ValueError('FORCED-VE')\n"
    "{i}if 'FORCETE' in expr: raise TypeError('FORCED-TE')\n"
    "{i}if 'FORCERT' in expr: raise RuntimeError('FORCED-RT')\n"
)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def drop_pycache():
    for d in ROOT.rglob("__pycache__"):
        shutil.rmtree(d, ignore_errors=True)


class Injected:
    """Context manager: patch EVAL before `anchor`, restore + verify on exit."""

    def __init__(self, anchor, indent):
        self.anchor, self.indent = anchor, indent

    def __enter__(self):
        self.backup = EVAL.with_suffix(".py.bak-forcing")
        shutil.copy2(EVAL, self.backup)
        self.before = sha(EVAL)
        src = EVAL.read_text()
        assert src.count(self.anchor) == 1, (
            f"anchor not unique ({src.count(self.anchor)}): {self.anchor!r}")
        patched = src.replace(
            self.anchor, INJECT.format(i=self.indent) + self.anchor, 1)
        assert patched != src
        EVAL.write_text(patched)
        drop_pycache()
        return self

    def __exit__(self, *exc):
        shutil.copy2(self.backup, EVAL)
        self.backup.unlink()
        drop_pycache()
        after = sha(EVAL)
        assert after == self.before, (
            f"RESTORE FAILED: {self.before} -> {after}")
        print(f"    [restore verified: sha256 {after[:16]}… unchanged]")
        return False


# --- observation contexts: each reaches evaluate_arithmetic by its OWN chain -
CONTEXTS = [
    ("arith_expansion  $(( ))     -> arithmetic_expansion_value/797",
     "echo A$((SENT))B"),
    ("substring offset  ${v:o:l}  -> operators.py:90",
     "v=abcdefgh; echo X${v:SENT:2}Y"),
    ("arith command     (( ))     -> core.py:517",
     "(( SENT )); echo rc=$?"),
    ("c-style for init  for(( ))  -> control_flow.py:416",
     "for ((SENT; 0; 0)); do :; done; echo rc=$?"),
    ("c-style for cond  for(( ))  -> control_flow.py:432",
     "for ((i=0; SENT; i++)); do :; done; echo rc=$?"),
    ("enhanced test     [[ -eq ]] -> core.py:576",
     "[[ SENT -eq 0 ]]; echo rc=$?"),
    ("indexed subscript ${a[i]}   -> subscript.py:375",
     "a=(1 2 3); echo X${a[SENT]}Y"),
    ("let builtin       let       -> builtins",
     "let SENT; echo rc=$?"),
    ("array assign      a[i]=v    -> executor/array.py",
     "a=(1 2 3); a[SENT]=9; echo rc=$?"),
]

SENTINELS = ["FORCEVE", "FORCETE", "FORCERT"]


def run_ctx(script, env):
    return subprocess.run(PSH + ["-c", script], cwd=str(ROOT),
                          capture_output=True, text=True, env=env, timeout=30)


def report(point_name, anchor, indent):
    print(f"\n{'='*78}\n== INJECTION POINT: {point_name}\n{'='*78}")
    with Injected(anchor, indent):
        # instrument-bites control: the sentinel must actually change behaviour
        ctl = run_ctx("echo A$((1+1))B", ENV)
        print(f"  [control, no sentinel] rc={ctl.returncode} "
              f"out={ctl.stdout.strip()!r}  (must be A2B / rc0)")
        for label, tmpl in CONTEXTS:
            print(f"\n  -- {label}")
            for sent in SENTINELS:
                script = tmpl.replace("SENT", sent)
                d = run_ctx(script, ENV)
                s = run_ctx(script, ENV_STRICT)
                print(f"     {sent}: default rc={d.returncode:<4} "
                      f"out={d.stdout.strip()[:26]!r:<28} "
                      f"err={d.stderr.strip()[:58]!r}")
                print(f"     {'':<{len(sent)}}  strict  rc={s.returncode:<4} "
                      f"err={s.stderr.strip()[-58:]!r}")


def main():
    disc = subprocess.run(
        [sys.executable, "-c",
         "import psh, psh.version as v; print(psh.__file__, v.__version__)"],
        cwd=str(ROOT), capture_output=True, text=True, env=ENV)
    assert disc.stdout.split()[0] == str(ROOT / "psh" / "__init__.py"), disc.stdout
    print("# tree :", disc.stdout.strip())
    print("# bash :", subprocess.run([BASH, "--version"], capture_output=True,
                                     text=True).stdout.splitlines()[0])
    print(f"# EVAL sha256 (pre) : {sha(EVAL)}")

    report("OUTER — inside evaluate_arithmetic, OUTSIDE the inner try",
           OUTER_ANCHOR, "        ")
    report("INNER — inside _evaluate_arithmetic_inner's try body",
           INNER_ANCHOR, "        ")

    print(f"\n# EVAL sha256 (post): {sha(EVAL)}")
    print("# (must equal the pre value)")


if __name__ == "__main__":
    main()
