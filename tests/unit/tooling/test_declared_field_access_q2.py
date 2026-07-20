"""Ratchet: defensive ``getattr``/``hasattr`` on a DECLARED field (campaign Q2, §13).

Anti-pattern #20 named: ``getattr(obj, 'field', default)`` / ``hasattr(obj,
'field')`` where ``field`` is a member the receiver's class ALWAYS has — a
dataclass field, a ``@property``, a class attribute with a value, or an
attribute unconditionally assigned in ``__init__``. The defensive access hides
the guaranteed presence, defeats type-checking, and its fallback branch is dead
code. Dynamic/optional attributes (a computed attr name, a ``getattr`` on a
module / exception / ``Optional`` receiver, an attribute assigned only lazily in
some method) are LEGITIMATE and out of scope by design.

**The detector line (precision over recall — charter §13).** This guard flags a
``getattr``/``hasattr`` with a CONSTANT attr name ONLY when it can STATICALLY
resolve the receiver to a psh class that DECLARES that member. It reflects each
psh class's declared members (dataclass fields + properties + valued class attrs
+ ``self.X`` assignments in ``__init__``) and resolves the receiver's type from:
``self`` inside the class; a parameter/local annotated with a psh type; the
element type of a ``List[T]``/``Optional[T]`` annotation; or a known
``self.shell`` / ``self.state`` / ``self.shell_state`` binding. Receivers it
CANNOT statically type (an unannotated ``node``/``part`` param, an unannotated
container element) are deliberately NOT claimed — a heuristic broad enough to
reach them would need mass exemptions. The archived census
(``tmp/boundary-ledgers/Q2-probes/getattr_sites.txt``, derived by
``scan_getattr.py``) records **168 constant-attr getattr/hasattr sites (152
unique signatures)** tree-wide; this mechanically self-verifying detector
resolves and locks the subset it can PROVE a declared-member access for and
prevents new provable ones. The remainder (dynamic attr names, module/exception/
Optional/unresolvable receivers, non-declared attrs) is out of scope; a
typed-access cleanup is a recorded carry. (An earlier "~116" figure was an
unverified subagent estimate with no derivation and is retracted.)

The frozen set is the CURRENT provable-declared-member accesses. It may only
SHRINK: fixing a site (``getattr(x,'f',d)`` → ``x.f``, behavior-inert because
``f`` is guaranteed) removes its entry. A NEW provable site fails
``test_no_new_declared_member_access``. Synthetic offenders prove the resolver
bites and does not false-positive on dynamic/module receivers.
"""

import ast
import dataclasses
import importlib
import inspect
import pathlib
import pkgutil
import textwrap

import psh

ROOT = pathlib.Path(__file__).resolve().parents[3]
PSH_ROOT = ROOT / "psh"


# --- reflect declared, runtime-present members of every psh class ------------

def _build_member_map():
    members: dict = {}
    for m in pkgutil.walk_packages(psh.__path__, "psh."):
        if m.name.endswith("__main__"):
            continue  # importing __main__ would run the CLI
        try:
            mod = importlib.import_module(m.name)
        except Exception:  # noqa: BLE001 - a module that won't import has no members here
            continue
        for nm in dir(mod):
            obj = getattr(mod, nm, None)
            if not (isinstance(obj, type)
                    and getattr(obj, "__module__", "").startswith("psh")):
                continue
            names: set = set()
            if dataclasses.is_dataclass(obj):
                names |= {f.name for f in dataclasses.fields(obj)}
            for kls in obj.__mro__:
                for k, v in vars(kls).items():
                    if isinstance(v, property):
                        names.add(k)
                    elif (not k.startswith("__") and not callable(v)
                          and not isinstance(v, (staticmethod, classmethod))):
                        names.add(k)
                init = kls.__dict__.get("__init__")
                if init is not None and not isinstance(init, type(object.__init__)):
                    try:
                        tree = ast.parse(textwrap.dedent(inspect.getsource(init)))
                    except (OSError, SyntaxError, TypeError):
                        tree = None
                    if tree is not None:
                        for a in ast.walk(tree):
                            if (isinstance(a, ast.Attribute)
                                    and isinstance(a.value, ast.Name)
                                    and a.value.id == "self"
                                    and isinstance(a.ctx, ast.Store)):
                                names.add(a.attr)
            if names:
                members.setdefault(obj.__name__, set()).update(names)
    # WordPart's concrete subclasses (LiteralPart/ExpansionPart) both declare
    # these even though the WordPart base is field-less.
    members.setdefault("WordPart", set()).update({"quoted", "quote_char"})
    return members


MEMBERS = _build_member_map()

# Receivers of the form self.<attr> whose type is known (attribute-chain).
_SELF_ATTR_TYPE = {"shell": "Shell", "state": "ShellState",
                   "shell_state": "ShellState"}


def _annotation_type(ann):
    """(type_name, is_element) for an annotation. Unwraps Optional[X] to X and
    List[X]/Tuple[X] to (X, element=True)."""
    if ann is None:
        return None, False
    if isinstance(ann, ast.Constant) and isinstance(ann.value, str):
        try:
            ann = ast.parse(ann.value, mode="eval").body
        except SyntaxError:
            return None, False
    if isinstance(ann, ast.Name):
        return ann.id, False
    if isinstance(ann, ast.Subscript) and isinstance(ann.value, ast.Name):
        if ann.value.id == "Optional":
            return _annotation_type(ann.slice)
        if ann.value.id in ("List", "list", "Sequence", "Iterable", "Tuple", "tuple"):
            inner, _ = _annotation_type(ann.slice)
            return inner, True
    return None, False


def _name_type(fn, name):
    """(type_name, is_element) for a local/param ``name`` in function ``fn``,
    from its annotation (param or AnnAssign). ``fn`` passed explicitly (not
    closed over) so the resolver is a pure helper."""
    t, el = None, False
    if fn is not None:
        for a in (list(fn.args.posonlyargs) + list(fn.args.args)
                  + list(fn.args.kwonlyargs)):
            if a.arg == name:
                t, el = _annotation_type(a.annotation)
        for st in ast.walk(fn):
            if (isinstance(st, ast.AnnAssign)
                    and isinstance(st.target, ast.Name)
                    and st.target.id == name):
                t, el = _annotation_type(st.annotation)
    return t, el


def declared_member_accesses(src: str, relpath: str):
    """Return sorted [(relpath, kind, receiver_text, attr)] for every
    getattr/hasattr with a constant attr whose receiver resolves to a psh class
    that DECLARES that attr."""
    tree = ast.parse(src)
    parents = {}
    for node in ast.walk(tree):
        for ch in ast.iter_child_nodes(node):
            parents[ch] = node

    def enclosing(node, types):
        while node in parents:
            node = parents[node]
            if isinstance(node, types):
                return node
        return None

    out = []
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id in ("getattr", "hasattr") and len(n.args) >= 2
                and isinstance(n.args[1], ast.Constant)
                and isinstance(n.args[1].value, str)):
            continue
        attr = n.args[1].value
        recv = n.args[0]
        fn = enclosing(n, (ast.FunctionDef, ast.AsyncFunctionDef))

        rtype = None
        if isinstance(recv, ast.Name):
            if recv.id == "self":
                cd = enclosing(n, (ast.ClassDef,))
                if cd is not None:
                    rtype = cd.name
            else:
                rtype, _ = _name_type(fn, recv.id)
        elif isinstance(recv, ast.Subscript) and isinstance(recv.value, ast.Name):
            t, el = _name_type(fn, recv.value.id)
            if el:
                rtype = t
        elif (isinstance(recv, ast.Attribute) and isinstance(recv.value, ast.Name)
              and recv.value.id == "self"):
            rtype = _SELF_ATTR_TYPE.get(recv.attr)

        if rtype and rtype in MEMBERS and attr in MEMBERS[rtype]:
            out.append((relpath, n.func.id, ast.unparse(recv), attr))
    return out


def _scan_tree():
    found = []
    for path in sorted(PSH_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(ROOT).as_posix()
        found.extend(declared_member_accesses(path.read_text(), rel))
    return sorted(found)


# --- the frozen set: current provable declared-member accesses ---------------
#
# Each is defensive access to a member the receiver's class GUARANTEES.
# Replacing it with direct access (``x.f`` / dropping the hasattr guard's dead
# else-branch) is behavior-inert — deferred to a typed-access cleanup (recorded
# in the Q2 ledger's carry register). MAY ONLY SHRINK. All 26 are debt — the
# former "reviewed exception" (state.py ``hasattr(self, 'scope_manager')`` in the
# ``debug_scopes`` setter) was PROVEN unreachable-defensive dead code at Q2 B3
# (the setter has zero callers; scope_manager is assigned before options), so the
# dead guard was DELETED and this set shrank 27 -> 26.
FROZEN_DECLARED_MEMBER_ACCESSES = sorted([
    ("psh/builtins/base.py", "hasattr", "shell", "stdout"),
    ("psh/builtins/base.py", "hasattr", "shell", "stderr"),
    ("psh/builtins/base.py", "hasattr", "shell", "stderr"),
    ("psh/builtins/base.py", "hasattr", "shell", "stderr"),
    ("psh/builtins/print_builtin.py", "hasattr", "shell", "stdout"),
    ("psh/builtins/print_builtin.py", "hasattr", "shell", "stderr"),
    ("psh/builtins/read_builtin.py", "getattr", "shell", "stdin"),
    ("psh/executor/control_flow.py", "hasattr", "self.shell", "stdin"),
    ("psh/executor/core.py", "getattr", "node", "background"),
    ("psh/executor/job_control.py", "hasattr", "self.shell_state", "foreground_pgid"),
    ("psh/executor/job_control.py", "hasattr", "self.shell_state", "foreground_pgid"),
    ("psh/executor/subshell.py", "getattr", "self.state", "in_forked_child"),
    ("psh/parser/combinators/arrays.py", "getattr", "tokens[pos]", "adjacent_to_previous"),
    ("psh/parser/combinators/commands/redirections.py", "getattr", "tokens[pos]", "adjacent_to_previous"),
    ("psh/parser/combinators/commands/redirections.py", "getattr", "op_token", "var_fd"),
    ("psh/parser/combinators/commands/simple.py", "getattr", "tokens[pos]", "position"),
    ("psh/parser/combinators/expansions.py", "getattr", "token", "quote_type"),
    ("psh/parser/recursive_descent/parsers/redirections.py", "getattr", "token", "var_fd"),
    ("psh/parser/recursive_descent/parsers/redirections.py", "getattr", "token", "combined_redirect"),
    ("psh/parser/recursive_descent/parsers/redirections.py", "getattr", "token", "var_fd"),
    ("psh/parser/recursive_descent/support/word_builder.py", "getattr", "token", "parts"),
    ("psh/parser/visualization/ascii_tree.py", "getattr", "node", "line"),
    ("psh/parser/visualization/ast_formatter.py", "getattr", "node", "line"),
    ("psh/parser/visualization/dot_generator.py", "getattr", "node", "line"),
    ("psh/parser/visualization/sexp_renderer.py", "getattr", "node", "line"),
    ("psh/visitor/enhanced_validator_visitor.py", "getattr", "node", "array_assignments"),
])


# --- the ratchet -------------------------------------------------------------

def test_no_new_declared_member_access():
    """The live provable set equals the frozen set — no NEW declared-member
    defensive access, and any removed one has had its frozen entry pruned."""
    live = _scan_tree()
    new = sorted(set(live) - set(FROZEN_DECLARED_MEMBER_ACCESSES))
    assert not new, (
        "NEW defensive getattr/hasattr on a DECLARED member. The receiver's "
        "class always has this attribute — access it directly (or drop the "
        "hasattr guard's dead else-branch). If it is genuinely defensive (a "
        "construction-ordering / lazy-init window), add it to the frozen set "
        f"with that specific reason:\n  {new}")


def test_ratchet_only_shrinks():
    """Shrink-only: a frozen entry with NO live counterpart (site fixed/removed)
    must be pruned from the frozen set."""
    live = _scan_tree()
    from collections import Counter
    stale = Counter(FROZEN_DECLARED_MEMBER_ACCESSES) - Counter(live)
    assert not stale, (
        "frozen declared-member entries with no live counterpart — the site was "
        f"fixed or moved; prune them (the ratchet only shrinks):\n  {sorted(stale)}")


def test_detector_is_not_vacuous():
    """The resolver must actually resolve psh types and find real accesses."""
    assert len(MEMBERS) > 50, "member reflection collapsed — resolver is blind"
    assert "Token" in MEMBERS and "var_fd" in MEMBERS["Token"]
    assert _scan_tree(), "detector found nothing — it would never bite"


# --- synthetic offenders: prove the resolver bites --------------------------

def test_offender_self_field_access_is_flagged():
    """A dataclass defensively reading its OWN declared field is flagged."""
    src = (
        "import dataclasses\n"
        "@dataclasses.dataclass\n"
        "class Token:\n"
        "    var_fd: str = ''\n"
        "    def m(self):\n"
        "        return getattr(self, 'var_fd', None)\n"
    )
    hits = declared_member_accesses(src, "psh/fake.py")
    assert ("psh/fake.py", "getattr", "self", "var_fd") in hits


def test_offender_annotated_param_field_access_is_flagged():
    """getattr on a param annotated with a psh dataclass whose field it names."""
    src = (
        "def f(token: 'Token'):\n"
        "    return getattr(token, 'var_fd', None)\n"
    )
    hits = declared_member_accesses(src, "psh/fake.py")
    assert ("psh/fake.py", "getattr", "token", "var_fd") in hits


def test_offender_typed_container_element_is_flagged():
    """getattr on an element of a List[Token] annotated container is flagged
    (the tokens[pos] shape)."""
    src = (
        "from typing import List\n"
        "def f(tokens: 'List[Token]', pos: int):\n"
        "    return getattr(tokens[pos], 'position', 0)\n"
    )
    hits = declared_member_accesses(src, "psh/fake.py")
    assert ("psh/fake.py", "getattr", "tokens[pos]", "position") in hits


def test_scanner_ignores_dynamic_and_unknown_receivers():
    """A dynamic attr name, a module/unknown receiver, and a NON-declared attr
    are NOT flagged (no false positives)."""
    src = (
        "import os\n"
        "def f(token: 'Token', name):\n"
        "    a = getattr(token, name)\n"              # dynamic attr name
        "    b = getattr(os, 'sep', '/')\n"            # module receiver
        "    c = getattr(token, 'not_a_field', 0)\n"   # attr not declared on Token
        "    d = getattr(unknown_thing, 'value', 0)\n"  # unresolvable receiver
        "    return a, b, c, d\n"
    )
    assert declared_member_accesses(src, "psh/fake.py") == []
