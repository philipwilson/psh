"""B7 evidence: the PS4 net's DEFAULT-mode (strict-errors OFF) consequence
class at tip vs base, for an INJECTED internal defect (no user-reachable
route). Monkeypatch-style injection via a copied tree, so the live worktree is
untouched."""
import os, pathlib, shutil, subprocess, sys, tempfile
ROOT = pathlib.Path("/Users/pwilson/src/psh-r3-5")
SNIP = ("        ps4 = self.shell.state.get_variable('PS4', '+ ')\n")
INJ = SNIP + ("        if 'FORCEDEFECT' in ps4:\n"
              "            def _boom(*a, **k):\n"
              "                raise TypeError('FORCED-INTERNAL-DEFECT')\n"
              "            self.expand_string_variables = _boom\n")
CMD = "set -x; PS4='FORCEDEFECT$x '; echo hi; echo TAIL"

def run(tree, strict):
    env = {**os.environ, "PYTHONPATH": str(tree)}
    env.pop("PSH_STRICT_ERRORS", None)
    if strict: env["PSH_STRICT_ERRORS"] = "1"
    return subprocess.run([sys.executable, "-m", "psh", "-c", CMD], cwd=str(tree),
                          capture_output=True, text=True, env=env, timeout=60)

for label, narrow in (("TIP  (except PshError)", True), ("BASE (except Exception)", False)):
    with tempfile.TemporaryDirectory(dir=str(ROOT / "tmp")) as td:
        tree = pathlib.Path(td)
        shutil.copytree(ROOT / "psh", tree / "psh",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        mgr = tree / "psh" / "expansion" / "manager.py"
        s = mgr.read_text()
        assert s.count(SNIP) == 1
        s = s.replace(SNIP, INJ, 1)
        if not narrow:  # revert the narrowing to reproduce BASE
            s = s.replace("        except PshError:\n            return ps4",
                          "        except Exception:\n            return ps4", 1)
        mgr.write_text(s)
        for strict in (False, True):
            r = run(tree, strict)
            mode = "strict" if strict else "DEFAULT"
            print(f"{label} [{mode:<7}] rc={r.returncode} out={r.stdout.strip()!r}")
        print()
