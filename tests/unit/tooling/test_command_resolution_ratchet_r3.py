"""Static ratchet: command DISPATCH decisions resolve ONCE (campaign R3, #20 H10).

The H10 defect class is *recompute-from-raw-names*: the executor deciding a
command's scope model / exec shortcut / POSIX-special branch from a raw
``function_manager.get_function`` or ``cmd_name in POSIX_SPECIAL_BUILTINS`` read
taken BEFORE (or instead of) the one mode-aware resolution. The fix routes every
such decision through ``command_resolution.resolve_command`` and the typed
``ResolvedCommand`` it returns.

This ratchet fails if a raw dispatch read is reintroduced into
``psh/executor/command.py`` (the dispatcher), where it would once again make a
dispatch decision outside the resolver. The scan is AST-based (comments and
docstrings that merely NAME these symbols do not trip it), and each rule is
self-tested against a synthetic offender so the scanner cannot rot into a no-op.

Whitelisted, because they are NOT dispatch decisions:
- ``self.function_manager = shell.function_manager`` and
  ``self.builtin_registry = shell.builtin_registry`` — attribute wiring.
- ``self.builtin_registry.get('exec')`` — a post-resolution FETCH of the exec
  builtin instance to RUN it (the decision was already made via
  ``ResolvedCommand.is_exec_special``).
"""

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
COMMAND_PY = ROOT / "psh" / "executor" / "command.py"
RESOLUTION_PY = ROOT / "psh" / "executor" / "command_resolution.py"


def _receiver_text(node: ast.Attribute) -> str:
    try:
        return ast.unparse(node.value)
    except Exception:  # pragma: no cover - defensive
        return ""


def dispatch_reads(source: str):
    """Return [(reason, lineno)] for raw dispatch-decision reads in *source*.

    - ``.get_function(`` on ANY receiver: a function-table dispatch read.
    - the name ``POSIX_SPECIAL_BUILTINS``: a special-builtin membership read.
    - ``<...>.has(`` where the receiver mentions ``builtin_registry``: a
      builtin-registry dispatch membership read.
    """
    tree = ast.parse(source)
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if node.attr == "get_function":
                offenders.append(("function-table dispatch read (.get_function)",
                                  node.lineno))
            elif node.attr == "has" and "builtin_registry" in _receiver_text(node):
                offenders.append(("builtin-registry dispatch membership (.has)",
                                  node.lineno))
        elif isinstance(node, ast.Name) and node.id == "POSIX_SPECIAL_BUILTINS":
            offenders.append(("special-builtin membership read "
                              "(POSIX_SPECIAL_BUILTINS)", node.lineno))
    return offenders


def test_command_py_has_no_raw_dispatch_reads():
    """The dispatcher makes NO raw dispatch decision — all flow through
    resolve_command / ResolvedCommand (H10)."""
    offenders = dispatch_reads(COMMAND_PY.read_text())
    assert offenders == [], (
        "psh/executor/command.py reintroduced a raw dispatch read — route it "
        f"through resolve_command / ResolvedCommand instead: {offenders}")


def test_ratchet_flags_get_function_offender():
    src = (
        "class C:\n"
        "    def run(self, name):\n"
        "        is_fn = self.function_manager.get_function(name) is not None\n"
        "        return is_fn\n"
    )
    assert any("get_function" in r for r, _ in dispatch_reads(src))


def test_ratchet_flags_posix_special_membership_offender():
    src = (
        "class C:\n"
        "    def run(self, name):\n"
        "        return name in POSIX_SPECIAL_BUILTINS\n"
    )
    assert any("POSIX_SPECIAL_BUILTINS" in r for r, _ in dispatch_reads(src))


def test_ratchet_flags_builtin_registry_has_offender():
    src = (
        "class C:\n"
        "    def run(self, name):\n"
        "        return self.builtin_registry.has(name)\n"
    )
    assert any(".has" in r for r, _ in dispatch_reads(src))


def test_ratchet_allows_exec_builtin_fetch():
    """The post-resolution exec-builtin FETCH is not a dispatch decision."""
    src = (
        "class C:\n"
        "    def run(self):\n"
        "        return self.builtin_registry.get('exec')\n"
    )
    assert dispatch_reads(src) == []


def test_ratchet_ignores_comments_and_docstrings():
    """Prose that merely names the symbols must not trip the AST scan."""
    src = (
        "def run(name):\n"
        "    '''We no longer call get_function or POSIX_SPECIAL_BUILTINS here.'''\n"
        "    # get_function / POSIX_SPECIAL_BUILTINS are resolver-only now\n"
        "    return name\n"
    )
    assert dispatch_reads(src) == []


def test_resolver_is_the_sole_dispatch_reader():
    """resolve_command is where the dispatch registry reads legitimately live:
    it selects among the strategies via their can_execute. Confirm the resolver
    module contains the resolution entry point the dispatcher delegates to."""
    src = RESOLUTION_PY.read_text()
    assert "def resolve_command(" in src
    assert "can_execute" in src


# === Q2 family 4: tree-wide widening (command-registry reads outside resolution)
#
# The original R3 ratchet guarded ONE file (command.py, the dispatcher). Q2
# widens the same three dispatch-read shapes across the WHOLE executor dispatch
# package (psh/executor/*.py): a raw function-table / special-builtin / builtin-
# registry membership read anywhere in the executor is a dispatch decision and
# must live in the resolution machinery, never leak into another executor module.
#
# Allowlist = the executor files that ARE the resolution machinery resolve_command
# drives (each verified to contain a flagged read; shrink-only). The dispatcher
# command.py is NOT allowlisted (it must stay at 0 — the original R3 invariant).
#
# DELIBERATELY OUT OF SCOPE: introspection BUILTINS (`type`, `command -v`, `hash`,
# `help`, `declare -f`, `export -f`, `readonly -f`) read these registries to
# REPORT or MANAGE them, not to decide command execution — a categorically
# different, legitimate use. Scoping the detector to the executor dispatch path
# (where a raw read IS a dispatch decision) keeps the allowlist to the 3 genuine
# resolution-machinery files instead of needing ~10 builtin exemptions.
#
# Q2 nit-1 — evasion shapes DECLARED OUT OF SCOPE (verified zero live instances):
# an ALIASED import of the membership set (`from ... import POSIX_SPECIAL_BUILTINS
# as SPECIALS; name in SPECIALS`), a getattr-SMUGGLED table read
# (`getattr(fm, 'get_function')(name)`), and a RAW-dict membership on the function
# store (`name in fm.functions`). These are dynamic/indirect; a heuristic covering
# them would false-positive on unrelated `.has(`/membership. If one appears in the
# executor, harden `dispatch_reads` rather than allowlisting it.

EXECUTOR_DIR = ROOT / "psh" / "executor"

RESOLUTION_MACHINERY = {
    "strategies.py":
        "the ExecutionStrategy.can_execute delegates resolve_command selects "
        "among (SpecialBuiltin/Builtin/Function can_execute) AND the canonical "
        "POSIX_SPECIAL_BUILTINS definition — the reads here ARE the one "
        "mode-aware resolution",
    "command_resolver.py":
        "the PATH/hash + typed-Candidate service: it reads the function/builtin/"
        "special registries to BUILD the ResolvedCommand candidates (and the "
        "type/command -v introspection view), i.e. it computes the resolution, "
        "not a shortcut around it",
    "function.py":
        "execute_function_call fetches the function BODY to RUN it after the "
        "FunctionExecutionStrategy already won resolution (127 if it vanished "
        "between resolve and run) — a post-resolution fetch, not a decision",
}


def _executor_dispatch_offenses():
    """{filename: offenses} for every psh/executor/*.py with a dispatch read."""
    out = {}
    for path in sorted(EXECUTOR_DIR.glob("*.py")):
        offs = dispatch_reads(path.read_text())
        if offs:
            out[path.name] = offs
    return out


def test_no_dispatch_reads_outside_resolution_machinery():
    """No executor module outside the resolution machinery makes a raw dispatch
    read (widens the command.py-only R3 guard across the dispatch package)."""
    offending = {name: offs for name, offs in _executor_dispatch_offenses().items()
                 if name not in RESOLUTION_MACHINERY}
    assert not offending, (
        "raw command-dispatch registry read in an executor module that is NOT "
        "the resolution machinery — route the decision through resolve_command / "
        "ResolvedCommand (or, if this file genuinely BECAME resolution machinery, "
        "add it to RESOLUTION_MACHINERY with a specific reason):\n  "
        + "\n  ".join(f"{n}: {o}" for n, o in sorted(offending.items())))


def test_resolution_machinery_entries_still_read_registries():
    """Shrink-only: an allowlisted machinery file that no longer contains a
    dispatch read must be pruned."""
    live = _executor_dispatch_offenses()
    for name in RESOLUTION_MACHINERY:
        assert (EXECUTOR_DIR / name).exists(), f"machinery file missing: {name}"
        assert name in live, (
            f"{name} no longer contains a dispatch-registry read — remove its "
            "RESOLUTION_MACHINERY entry (the ratchet only shrinks)")


def test_every_machinery_entry_has_justification():
    for name, reason in RESOLUTION_MACHINERY.items():
        assert isinstance(reason, str) and len(reason.strip()) >= 30, (
            f"RESOLUTION_MACHINERY[{name!r}] needs a specific justification")


def test_widened_scan_flags_a_read_in_a_non_machinery_file():
    """SYNTHETIC OFFENDER: a dispatch read placed in a non-machinery executor
    module (modeled here as command.py's name) is caught by the widened scan —
    proving the tree-wide rule bites beyond the resolution machinery."""
    offender_src = (
        "class Dispatcher:\n"
        "    def run(self, name):\n"
        "        if name in POSIX_SPECIAL_BUILTINS:\n"
        "            return self._special(name)\n"
        "        return self.function_manager.get_function(name)\n"
    )
    offs = dispatch_reads(offender_src)
    # A file holding these reads, if NOT in RESOLUTION_MACHINERY, fails the scan.
    assert offs and "command.py" not in RESOLUTION_MACHINERY
    kinds = {r.split("(")[0].strip() for r, _ in offs}
    assert "special-builtin membership read" in kinds
    assert "function-table dispatch read" in kinds
