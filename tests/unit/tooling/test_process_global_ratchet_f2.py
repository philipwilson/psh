"""Static ratchet: process-global mutations live only in lease-owning modules.

Campaign F2's chokepoint guard: the ``ProcessLeaseCoordinator`` is the one
gate for process-global ownership, so the PRIMITIVES that mutate that state
— ``locale.setlocale``, ``sys.setrecursionlimit``, ``signal.signal`` — may
appear only in the modules that own the corresponding lease/policy.  A new
call site anywhere else is an offense: it would mutate the process behind
the coordinator's back (exactly the pre-F2 state that let constructing a
second shell change the first shell's behavior).

The allowlists are RATCHETS: they may only shrink.  Each retained
``signal.signal`` site is scoped (child-side after fork, the entry-point
SignalManager whose installs are symmetric-restored, the trap lease itself,
or a save/restore window) — unifying them further under the coordinator is
follow-on work, but no NEW site may appear.

AST-based (comments and strings never false-positive), with synthetic
offender self-tests proving each scanner fires.
"""
import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PSH_DIR = REPO_ROOT / "psh"

#: The one module that may call locale.setlocale — application under the
#: LOCALE lease (ensure_applied), baseline capture/restore, and the
#: setlocale-query helpers all live here.
SETLOCALE_ALLOWED = {
    "psh/core/locale_service.py",
}

#: The one module that may raise the recursion limit — at activation grant.
SETRECURSIONLIMIT_ALLOWED = {
    "psh/core/process_lease.py",
}

#: signal.signal call sites (FROZEN; may only shrink). Scopes:
#: - trap_manager: the SIGNALS component lease + trap install/reset paths;
#: - signal_manager: entry-point installs, saved-original symmetric restore;
#: - signal_utils: the registry wrapper every managed install records into;
#: - child_policy / pipeline / process_launcher: child-side after fork;
#: - command_sub / process_sub: scoped save/restore windows around a wait.
SIGNAL_SIGNAL_ALLOWED = {
    "psh/core/trap_manager.py",
    "psh/interactive/signal_manager.py",
    "psh/utils/signal_utils.py",
    "psh/executor/child_policy.py",
    "psh/executor/pipeline.py",
    "psh/executor/process_launcher.py",
    "psh/expansion/command_sub.py",
    "psh/io_redirect/process_sub.py",
}


def _attribute_calls(source: str, filename: str, modules: set,
                     attr: str) -> list:
    """[(lineno, snippet)] for every ``<name>.<attr>(...)`` call where
    <name> binds one of *modules* — the plain module name, any PRE-SEEDED
    alias in *modules* (the in-tree ``import locale as _locale`` spelling),
    or any alias THIS FILE introduces (``import signal as sig``) — plus
    ``from <module> import <attr>``.  Two passes: aliases first, so an
    aliased import anywhere in the file is caught regardless of position."""
    tree = ast.parse(source, filename=filename)
    names = set(modules)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in modules and alias.asname:
                    names.add(alias.asname)
    hits = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == attr
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in names):
            hits.append((node.lineno, f"{node.func.value.id}.{attr}()"))
        elif isinstance(node, ast.ImportFrom) and node.module in modules:
            for alias in node.names:
                if alias.name == attr:
                    hits.append((node.lineno,
                                 f"from {node.module} import {attr}"))
    return hits


def _scan(modules: set, attr: str, allowed: set) -> list:
    offenders = []
    for path in sorted(PSH_DIR.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in allowed:
            continue
        for lineno, snippet in _attribute_calls(path.read_text(), rel,
                                                modules, attr):
            offenders.append(f"{rel}:{lineno}: {snippet}")
    return offenders


def test_setlocale_only_in_locale_service():
    offenders = _scan({"locale", "_locale"}, "setlocale", SETLOCALE_ALLOWED)
    assert not offenders, (
        "locale.setlocale called outside psh/core/locale_service.py — libc "
        "locale mutation must go through the LOCALE component lease "
        "(campaign F2):\n" + "\n".join(offenders))


def test_setrecursionlimit_only_in_process_lease():
    offenders = _scan({"sys"}, "setrecursionlimit",
                      SETRECURSIONLIMIT_ALLOWED)
    assert not offenders, (
        "sys.setrecursionlimit called outside psh/core/process_lease.py — "
        "the headroom raise is an activation-grant fact (campaign F2):\n"
        + "\n".join(offenders))


def test_signal_signal_sites_are_frozen():
    offenders = _scan({"signal"}, "signal", SIGNAL_SIGNAL_ALLOWED)
    assert not offenders, (
        "signal.signal called from a NEW module — signal-disposition "
        "mutation belongs to the allowlisted lease/policy owners "
        "(campaign F2 ratchet; the list may only shrink):\n"
        + "\n".join(offenders))


def test_allowlisted_files_exist():
    """A ratchet entry for a deleted file is stale — prune it (shrink)."""
    for rel in (SETLOCALE_ALLOWED | SETRECURSIONLIMIT_ALLOWED
                | SIGNAL_SIGNAL_ALLOWED):
        assert (REPO_ROOT / rel).is_file(), f"stale allowlist entry: {rel}"


# --- synthetic offenders: prove each scanner fires ------------------------

def test_scanner_fires_on_setlocale_offender():
    source = "import locale\nlocale.setlocale(locale.LC_ALL, 'C')\n"
    assert _attribute_calls(source, "offender.py", {"locale", "_locale"},
                            "setlocale")
    aliased = "import locale as _locale\n_locale.setlocale(_locale.LC_CTYPE, name)\n"
    assert _attribute_calls(aliased, "offender.py", {"locale", "_locale"},
                            "setlocale")
    from_import = "from locale import setlocale\n"
    assert _attribute_calls(from_import, "offender.py", {"locale"},
                            "setlocale")


def test_scanner_fires_on_setrecursionlimit_offender():
    source = "import sys\nsys.setrecursionlimit(99999)\n"
    assert _attribute_calls(source, "offender.py", {"sys"},
                            "setrecursionlimit")


def test_scanner_fires_on_signal_offender():
    source = "import signal\nsignal.signal(signal.SIGUSR1, handler)\n"
    assert _attribute_calls(source, "offender.py", {"signal"}, "signal")


def test_scanner_fires_on_aliased_signal_offender():
    # The alias is introduced by the offending FILE itself (bounce nit 4):
    # `import signal as sig; sig.signal(...)` must be caught, in either
    # order of appearance.
    source = "import signal as sig\nsig.signal(2, handler)\n"
    assert _attribute_calls(source, "offender.py", {"signal"}, "signal")
    aliased_locale = "import locale as loc\nloc.setlocale(loc.LC_ALL, 'C')\n"
    assert _attribute_calls(aliased_locale, "offender.py",
                            {"locale", "_locale"}, "setlocale")
    aliased_sys = "import sys as s\ns.setrecursionlimit(99999)\n"
    assert _attribute_calls(aliased_sys, "offender.py", {"sys"},
                            "setrecursionlimit")
    # An alias of an UNRELATED module must not false-positive.
    unrelated = "import signals_toolkit as sig\nsig.signal(2, handler)\n"
    assert not _attribute_calls(unrelated, "clean.py", {"signal"}, "signal")


def test_scanner_ignores_comments_and_strings():
    source = (
        "# locale.setlocale(locale.LC_ALL, 'C') in a comment\n"
        "x = 'signal.signal(signal.SIGUSR1, h)'\n"
        '"""sys.setrecursionlimit(5)"""\n'
    )
    assert not _attribute_calls(source, "clean.py", {"locale"}, "setlocale")
    assert not _attribute_calls(source, "clean.py", {"signal"}, "signal")
    assert not _attribute_calls(source, "clean.py", {"sys"},
                                "setrecursionlimit")
