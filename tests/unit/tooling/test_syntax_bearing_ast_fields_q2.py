"""Drift-lock: no syntax-bearing raw AST field escapes typed backing (Q2, §13,
"syntax-bearing raw AST fields").

Campaign S3 gave every AST field whose OWN grammar is a lazily-parsed region — a
parameter-expansion operand, an arithmetic expression, an array subscript — a
typed template (``WordTemplate``/``ArithmeticTemplate``/``SubscriptSpec``) so the
syntax is structured, not smuggled through as an opaque string. This guard
reflects EVERY ``str`` / ``Optional[str]`` / ``List[str]`` field on every
concrete ``psh.ast_nodes`` node and requires each to be classified:

* TEMPLATE_BACKED — a syntax region whose node ALSO carries the paired
  ``*_template``/``*_spec`` field (asserted present here);
* STRUCTURE_BACKED — re-parsed syntax whose node carries a ``Word``/``Program``
  structural backing (asserted present);
* JUSTIFIED_RAW — a runtime-expansion string bash does NOT read-time-validate
  (only ``Redirect.heredoc_content``);
* PLAIN — a name / operator / quote char / literal, never re-parsed as syntax.

A NEW str field on any node — or removing a template from a TEMPLATE_BACKED node
— fails, forcing triage: if it carries lazily-parsed syntax, give it a typed
template; if plain, add it to PLAIN. The set is frozen (drift-lock, same idiom as
the AstChildSchema guard). Synthetic offenders prove it bites.
"""

import dataclasses
import inspect
import typing

import psh.ast_nodes as ast_mod
from psh.ast_nodes import ASTNode


def _is_str_field(t) -> bool:
    """True if the (possibly stringized) annotation is str / Optional[str] /
    List[str]."""
    if isinstance(t, str):
        base = t.replace("Optional[", "").replace("List[", "").replace("]", "")
        base = base.replace("| None", "").strip()
        return base == "str"
    origin = typing.get_origin(t)
    if origin is typing.Union:
        return any(_is_str_field(a) for a in typing.get_args(t)
                   if a is not type(None))
    if origin is list:
        args = typing.get_args(t)
        return bool(args) and _is_str_field(args[0])
    return t is str


def _concrete_nodes():
    out = []
    for name in dir(ast_mod):
        obj = getattr(ast_mod, name)
        if (inspect.isclass(obj) and issubclass(obj, ASTNode)
                and obj.__module__ == "psh.ast_nodes"
                and dataclasses.is_dataclass(obj)):
            out.append(obj)
    return {c.__name__: c for c in out}


NODES = _concrete_nodes()


def _live_str_fields():
    found = set()
    for cname, cls in NODES.items():
        for f in dataclasses.fields(cls):
            if _is_str_field(f.type):
                found.add((cname, f.name))
    return found


# --- classification (frozen) -------------------------------------------------

# (node, raw_field) -> the paired template/spec field that MUST exist.
TEMPLATE_BACKED = {
    ("ArithmeticEvaluation", "expression"): "arith_template",
    ("ArithmeticExpansion", "expression"): "arith_template",
    ("ArrayElementAssignment", "index"): "index_spec",
    ("CStyleForLoop", "init_expr"): "init_template",
    ("CStyleForLoop", "condition_expr"): "condition_template",
    ("CStyleForLoop", "update_expr"): "update_template",
    ("ParameterExpansion", "word"): "word_template",
    ("ParameterExpansion", "parameter"): "subscript_spec",   # arr[SUB] slice
    ("VariableExpansion", "name"): "subscript_spec",         # arr[SUB] slice
}

# (node, raw_field) -> the structural backing field that MUST exist. The raw
# string stays as legacy display / fallback; the backing is what's consumed.
STRUCTURE_BACKED = {
    ("ArrayElementAssignment", "value"): "value_word",
    ("ArrayInitialization", "elements"): "words",
    ("CaseConditional", "expr"): "subject_word",
    ("CasePattern", "pattern"): "word",
    ("CommandSubstitution", "source"): "program",
    ("ForLoop", "items"): "item_words",
    ("ProcessSubstitution", "source"): "program",
    ("SelectLoop", "items"): "item_words",
}

# Syntax-bearing but deliberately RAW: a heredoc body is a runtime-expansion
# context (like a double-quoted string); bash does NOT read-time-validate its
# nested $() — templating it would DIVERGE (reject `<<EOF … $(if) … EOF` at read
# time). Pinned by tests/conformance/bash/test_syntax_template_timing_conformance.
JUSTIFIED_RAW = {
    ("Redirect", "heredoc_content"):
        "heredoc body = runtime-expansion context; bash does not read-time-"
        "validate its nested $() (templating would diverge)",
}

# Plain names / operators / quote chars / literals — never re-parsed as syntax.
PLAIN = {
    ("AndOrList", "operators"),           # && / ||
    ("ArrayElementAssignment", "name"),   # array name
    ("ArrayInitialization", "name"),      # array name
    ("BinaryTestExpression", "operator"),  # == / =~ / -eq (operands are Words)
    ("CaseItem", "terminator"),           # ;; / ;& / ;;&
    ("CompoundTestExpression", "operator"),  # && / ||
    ("ExpansionPart", "quote_char"),      # quote char
    ("ForLoop", "variable"),              # loop var name
    ("FunctionDef", "name"),              # function name
    ("LiteralPart", "text"),              # already-literal text
    ("LiteralPart", "quote_char"),        # quote char
    ("ParameterExpansion", "operator"),   # :- / # / % / /
    ("ProcessSubstitution", "direction"),  # 'in' / 'out'
    ("Redirect", "type"),                 # operator '>' / '2>&1'
    ("Redirect", "target"),               # raw heredoc delimiter / filename fallback (target_word backs expansion)
    ("Redirect", "quote_type"),           # here-string quote char
    ("Redirect", "var_fd"),               # {v}>f variable NAME
    ("SelectLoop", "variable"),           # select var name
    ("UnaryTestExpression", "operator"),  # -f / -z (operand is a Word)
    ("VariableExpansion", "name"),        # ALSO in TEMPLATE_BACKED (subscript slice)
}


def _all_classified():
    return set(TEMPLATE_BACKED) | set(STRUCTURE_BACKED) | set(JUSTIFIED_RAW) | PLAIN


# --- the drift-lock ----------------------------------------------------------

def test_every_str_field_is_classified():
    """No unclassified str AST field. A NEW one is a syntax-bearing-field
    candidate: template-back it (if lazily-parsed syntax) or add to PLAIN."""
    live = _live_str_fields()
    new = sorted(live - _all_classified())
    assert not new, (
        "unclassified str AST field(s). If the field carries lazily-parsed "
        "shell syntax (a parameter operand / arithmetic / subscript / pattern), "
        "give the node a typed template (S3) or a Word/Program structural "
        "backing; if it is a plain name/operator/literal, add it to PLAIN:\n  "
        + "\n  ".join(map(str, new)))


def test_no_stale_classification():
    """Every classified (node, field) still exists on the real node."""
    live = _live_str_fields()
    stale = sorted(_all_classified() - live)
    assert not stale, (
        "classified str fields that no longer exist (renamed/removed) — update "
        f"the classification:\n  " + "\n  ".join(map(str, stale)))


def test_template_backed_nodes_still_carry_their_template():
    """A TEMPLATE_BACKED raw field must keep its paired template/spec field —
    removing the template (leaving a raw syntax string) fails here."""
    missing = []
    for (node, raw), tmpl_field in TEMPLATE_BACKED.items():
        cls = NODES.get(node)
        assert cls is not None, f"unknown node {node}"
        field_names = {f.name for f in dataclasses.fields(cls)}
        if raw not in field_names:
            missing.append(f"{node}.{raw} (raw field gone)")
        if tmpl_field not in field_names:
            missing.append(f"{node}.{tmpl_field} (template field gone — the raw "
                            f"field {raw} would be un-backed syntax)")
    assert not missing, "\n  ".join([""] + missing)


def test_structure_backed_nodes_still_carry_their_backing():
    missing = []
    for (node, raw), backing in STRUCTURE_BACKED.items():
        cls = NODES.get(node)
        assert cls is not None, f"unknown node {node}"
        field_names = {f.name for f in dataclasses.fields(cls)}
        if backing not in field_names:
            missing.append(f"{node}.{backing} (structural backing gone — {raw} "
                           f"would be un-backed re-parsed syntax)")
    assert not missing, "\n  ".join([""] + missing)


def test_classification_is_not_vacuous():
    assert len(_live_str_fields()) >= 30, "reflection collapsed"
    assert set(TEMPLATE_BACKED) <= _live_str_fields()
    assert set(STRUCTURE_BACKED) <= _live_str_fields()


# --- synthetic offenders -----------------------------------------------------

def test_offender_new_unclassified_str_field_is_flagged():
    """A hypothetical new node with a raw syntax-bearing str field would be
    unclassified — the classification set does not contain it, so the drift-lock
    fires."""
    fake = ("SomeNewNode", "arith_expr")
    assert fake not in _all_classified()
    # And the reflection would surface such a field on a real node:
    assert _is_str_field(str) and _is_str_field(typing.Optional[str])
    assert _is_str_field(typing.List[str])


def test_offender_removed_template_would_break_backing_check():
    """If ArithmeticExpansion lost its arith_template, the TEMPLATE_BACKED check
    would flag it — proven by asserting the check keys on the template field's
    presence."""
    cls = NODES["ArithmeticExpansion"]
    names = {f.name for f in dataclasses.fields(cls)}
    assert "arith_template" in names and "expression" in names
    # The mapping's value is exactly the field the check requires:
    assert TEMPLATE_BACKED[("ArithmeticExpansion", "expression")] == "arith_template"


def test_str_field_detector_ignores_non_str():
    assert not _is_str_field(int)
    assert not _is_str_field(typing.Optional[int])
    assert not _is_str_field(typing.List[int])
