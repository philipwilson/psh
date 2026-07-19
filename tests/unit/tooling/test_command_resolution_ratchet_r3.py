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
