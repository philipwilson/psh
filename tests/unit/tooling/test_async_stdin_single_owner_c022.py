"""Guard: ONE answer to "is fd 0 the shell's own stdin right now" (C022).

The POSIX async ``/dev/null`` rule needs that fact, and before the fd-0 binding
existed the launcher simply assumed it — every backgrounded command got
``/dev/null`` even when a pipeline or a compound redirect had supplied the
frame's input, so ``echo hi | { cat & wait; }`` lost the pipe's bytes.

The fact now has exactly one producer
(``psh/core/stdin_binding.py#StdinBinding.is_shell_stdin``) and one consumer
(``AsyncJobPolicy.for_launch``'s ``stdin_is_shell_own``). This guard fails if a
SECOND one appears: a re-implementation of the property, a second policy
construction site, a call that answers the question inline (a literal, an
``isatty``/``S_ISFIFO`` sniff), or a new fd-0 origin heuristic anywhere in the
core / executor / io_redirect layers.

Each check has a synthetic offender below, so the guard cannot rot into a
no-op.
"""

import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
PSH = ROOT / "psh"

OWNER_MODULE = "psh/core/stdin_binding.py"
CLASSIFIER_MODULE = "psh/io_redirect/redirect_program.py"
CONSUMER_MODULE = "psh/executor/process_launcher.py"

#: member -> the ONE module allowed to define it. The answer's producer and its
#: feeders, plus the classifier that decides what "supplied fd 0" means (a
#: second copy of THAT is how the direction half went missing in round 1).
OWNER_MEMBERS = {
    "is_shell_stdin": OWNER_MODULE,
    "note_compound_applied": OWNER_MODULE,
    "note_compound_restored": OWNER_MODULE,
    "note_pipe_stdin": OWNER_MODULE,
    "supplies_frame_stdin": CLASSIFIER_MODULE,
    "list_supplies_frame_stdin": CLASSIFIER_MODULE,
    "target_fd_of": CLASSIFIER_MODULE,
}

#: fd-0 ORIGIN sniffs are how a second answer would be spelled. The layers
#: below must contain none except this frozen allowlist, whose entry answers a
#: DIFFERENT question (does this process have a controlling terminal?).
SNIFF_LAYERS = ("core", "executor", "io_redirect")
SNIFF_ALLOWLIST = {
    ("psh/core/terminal_state.py", "isatty"),
}


def _psh_sources():
    return [(str(p.relative_to(ROOT)), p.read_text(encoding="utf-8"))
            for p in sorted(PSH.rglob("*.py"))]


# --- detectors (shared by the real scan and the synthetic offenders) --------

def _members_defined(sources, names):
    """Every (module, member) definition of *names*.

    A definition is a ``def``/``async def``, an annotated assignment, OR a
    plain assignment (``is_shell_stdin = property(...)``, ``supplies_frame_stdin
    = _my_copy``) — round-1 verification planted the plain-``Assign`` spelling
    and the guard did not see it.
    """
    found = []
    for path, src in sources:
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and node.name in names:
                found.append((path, node.name))
            elif isinstance(node, ast.AnnAssign) and \
                    isinstance(node.target, ast.Name) and node.target.id in names:
                found.append((path, node.target.id))
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    for leaf in ast.walk(target):
                        if isinstance(leaf, ast.Name) and leaf.id in names:
                            found.append((path, leaf.id))
                        elif isinstance(leaf, ast.Attribute) and leaf.attr in names:
                            found.append((path, leaf.attr))
    return found


def _policy_references(sources):
    """Every mention of ``AsyncJobPolicy.for_launch`` in the tree.

    Returns ``(path, arg_or_None, is_direct_call)``. A reference that is NOT
    the callee of a call — ``launch = AsyncJobPolicy.for_launch`` and then
    ``launch(...)`` — is an ALIASED call site: round-1 verification planted one
    and the call-site count stayed at 1, so the alias is now itself an
    offense.
    """
    refs = []
    for path, src in sources:
        tree = ast.parse(src)
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                called.add(id(node.func))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Attribute) and node.attr == "for_launch"):
                continue
            if not (isinstance(node.value, ast.Name)
                    and node.value.id == "AsyncJobPolicy"):
                continue
            direct = id(node) in called
            arg = None
            if direct:
                call = next(c for c in ast.walk(tree)
                            if isinstance(c, ast.Call) and c.func is node)
                arg = next((kw.value for kw in call.keywords
                            if kw.arg == "stdin_is_shell_own"), None)
            refs.append((path, arg, direct))
    return refs


def _policy_call_sites(sources):
    """The DIRECT call sites only (an aliased reference is flagged separately)."""
    return [(path, arg) for path, arg, direct in _policy_references(sources)
            if direct]


def _answers_from_the_owner(arg):
    """True when the argument READS the owner's property rather than deciding.

    Accepts ``<anything>.stdin_binding.is_shell_stdin``; rejects a literal, a
    call, a comparison — anything that re-derives the fact at the call site.
    """
    return (isinstance(arg, ast.Attribute)
            and arg.attr == "is_shell_stdin"
            and isinstance(arg.value, ast.Attribute)
            and arg.value.attr == "stdin_binding")


def _fd0_origin_sniffs(sources):
    """``os.isatty(0)`` / ``os.fstat(0)`` / ``stat.S_ISFIFO(...)`` sites."""
    hits = []
    for path, src in sources:
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = (node.func.attr if isinstance(node.func, ast.Attribute)
                    else node.func.id if isinstance(node.func, ast.Name) else None)
            if name == "S_ISFIFO":
                hits.append((path, name))
            elif name in ("isatty", "fstat"):
                zero = (node.args and isinstance(node.args[0], ast.Constant)
                        and node.args[0].value == 0)
                if zero:
                    hits.append((path, name))
    return hits


# --- the real scan ---------------------------------------------------------

def test_the_answer_has_exactly_one_producer():
    """Each owned member is defined in exactly one module — its own."""
    defined = _members_defined(_psh_sources(), OWNER_MEMBERS)
    assert sorted(defined) == sorted((module, name)
                                     for name, module in OWNER_MEMBERS.items()), \
        defined


def test_the_policy_has_one_call_site_reading_the_owner():
    """One construction site, and it passes the OWNER's answer through.

    A second site (or a hard-coded ``stdin_is_shell_own=True``) would be a
    second decision about the same fact — the shape C022 was.
    """
    refs = _policy_references(_psh_sources())
    aliased = [(path, direct) for path, _, direct in refs if not direct]
    assert not aliased, f"AsyncJobPolicy.for_launch referenced without calling it: {aliased}"
    sites = _policy_call_sites(_psh_sources())
    assert [path for path, _ in sites] == [CONSUMER_MODULE], sites
    assert _answers_from_the_owner(sites[0][1]), ast.dump(sites[0][1])


def test_no_second_fd0_origin_heuristic_in_the_core_layers():
    """No ``isatty(0)``/``fstat(0)``/``S_ISFIFO`` outside the frozen allowlist."""
    sources = [(path, src) for path, src in _psh_sources()
               if any(path.startswith(f"psh/{layer}/") for layer in SNIFF_LAYERS)]
    hits = set(_fd0_origin_sniffs(sources))
    assert hits <= SNIFF_ALLOWLIST, sorted(hits - SNIFF_ALLOWLIST)


# --- synthetic offenders: the detectors must BITE --------------------------

SECOND_PRODUCER = '''
class OtherThing:
    @property
    def is_shell_stdin(self):
        return True
'''

SECOND_CALL_SITE = '''
def launch(self):
    AsyncJobPolicy.for_launch(background=True, job_control_off=True,
                              stdin_is_shell_own=True)
'''

INLINE_ANSWER = '''
def launch(self):
    AsyncJobPolicy.for_launch(
        background=True, job_control_off=True,
        stdin_is_shell_own=not stat.S_ISFIFO(os.fstat(0).st_mode))
'''

SNIFF = '''
def looks_inherited():
    import os, stat
    return stat.S_ISFIFO(os.fstat(0).st_mode) or os.isatty(0)
'''


ASSIGNED_PRODUCER = """
class OtherThing:
    is_shell_stdin = property(lambda self: True)
"""

ASSIGNED_CLASSIFIER = """
supplies_frame_stdin = _local_copy
"""

ALIASED_CALL = """
def launch(self):
    go = AsyncJobPolicy.for_launch
    go(background=True, job_control_off=True, stdin_is_shell_own=True)
"""


@pytest.mark.parametrize("source,member", [
    (SECOND_PRODUCER, "is_shell_stdin"),
    (ASSIGNED_PRODUCER, "is_shell_stdin"),
    (ASSIGNED_CLASSIFIER, "supplies_frame_stdin"),
])
def test_offender_second_producer_is_flagged(source, member):
    """A second producer counts whether it is a def, an annotated assignment
    or a PLAIN assignment (the round-1 evasion)."""
    found = _members_defined([("psh/executor/sneaky.py", source)], OWNER_MEMBERS)
    assert found == [("psh/executor/sneaky.py", member)]


def test_offender_aliased_call_site_is_flagged():
    """Binding the classmethod to a name and calling THAT is still a call site."""
    refs = _policy_references([("psh/executor/sneaky.py", ALIASED_CALL)])
    assert refs == [("psh/executor/sneaky.py", None, False)]
    assert _policy_call_sites([("psh/executor/sneaky.py", ALIASED_CALL)]) == []


@pytest.mark.parametrize("source", [SECOND_CALL_SITE, INLINE_ANSWER])
def test_offender_call_site_that_decides_for_itself_is_flagged(source):
    sites = _policy_call_sites([("psh/executor/sneaky.py", source)])
    assert len(sites) == 1
    assert not _answers_from_the_owner(sites[0][1])


def test_offender_fd0_sniff_is_flagged():
    hits = _fd0_origin_sniffs([("psh/executor/sneaky.py", SNIFF)])
    assert sorted(hits) == [("psh/executor/sneaky.py", "S_ISFIFO"),
                            ("psh/executor/sneaky.py", "fstat"),
                            ("psh/executor/sneaky.py", "isatty")]


def test_detectors_do_not_flag_the_innocent():
    """CONTROL: the real call site passes, and an unrelated isatty does not."""
    innocent = '''
def show(stream, fd):
    return stream.isatty() or os.isatty(fd)
'''
    assert _fd0_origin_sniffs([("psh/io_redirect/x.py", innocent)]) == []
    real = '''
def go(self):
    AsyncJobPolicy.for_launch(
        background=True, job_control_off=self._job_control_off(),
        stdin_is_shell_own=self.state.stdin_binding.is_shell_stdin).apply(c)
'''
    sites = _policy_call_sites([("psh/executor/process_launcher.py", real)])
    assert _answers_from_the_owner(sites[0][1])
