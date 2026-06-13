"""Lock the hot-path boundary: runtime never reads legacy AST fields.

Safety net for Tier A2 of the lexer/parser/AST architecture review
(``docs/reviews/lexer_parser_ast_architecture_review_2026-06-13.md``).
A2 derives/deletes the legacy parallel fields on several AST nodes. That
cleanup is only safe if the runtime path (executor + expansion) already
reads the canonical ``Word``-based fields exclusively and never the
legacy quote/type sidecars.

This static-source meta-test scans ``psh/executor/`` and ``psh/expansion/``
and asserts that NONE of the legacy quote/type attribute accesses appear
there. Verified 2026-06-13 (grep over both packages found zero hits for
all five):

| Locked attribute        | Only legitimate readers                        |
|-------------------------|------------------------------------------------|
| .element_types          | formatter_visitor / validator_visitor          |
| .element_quote_types    | formatter_visitor / validator_visitor          |
| .value_type             | formatter_visitor                              |
| .value_quote_type       | formatter_visitor                              |
| .item_quote_types       | (no readers anywhere)                          |

Why only these five (and not ``.elements`` / ``.items`` / ``.value`` /
``.pattern``): those are still read in the runtime for LEGITIMATE,
non-quote reasons and are NOT being dropped by A2:
- ``node.elements`` -- executor/array.py iterates it in parallel with
  ``node.words`` (the count basis for the consistency check).
- ``node.items`` -- CaseConditional.items is the CaseItem list, and
  control_flow.py uses ForLoop.items as the literal fallback when
  item_words is None (manually built ASTs).
- ``node.value`` -- only ``var_obj.value`` (runtime Variable objects);
  ArrayElementAssignment.value appears solely in an error message repr.
- ``node.pattern`` -- CasePattern.pattern is read for the match string.

So this test locks exactly the fields A2 will delete, proving the
runtime path is already Word-only.
"""

from pathlib import Path

import psh

# The legacy quote/type fields A2 will drop. Each must be absent from the
# runtime packages (executor + expansion) for the cleanup to be safe.
LOCKED_LEGACY_ATTRS = [
    '.element_types',
    '.element_quote_types',
    '.value_type',
    '.value_quote_type',
    '.item_quote_types',
]

PSH_ROOT = Path(psh.__file__).resolve().parent
RUNTIME_PACKAGES = [PSH_ROOT / 'executor', PSH_ROOT / 'expansion']


def _runtime_sources():
    for pkg in RUNTIME_PACKAGES:
        assert pkg.is_dir(), f"expected runtime package dir: {pkg}"
        yield from sorted(pkg.rglob('*.py'))


def test_runtime_packages_never_read_locked_legacy_fields():
    """No legacy quote/type attribute access in executor/ or expansion/."""
    offenders = {}
    for path in _runtime_sources():
        text = path.read_text(encoding='utf-8')
        for lineno, line in enumerate(text.splitlines(), start=1):
            for attr in LOCKED_LEGACY_ATTRS:
                if attr in line:
                    offenders.setdefault(attr, []).append(
                        f"{path.relative_to(PSH_ROOT)}:{lineno}: {line.strip()}"
                    )
    assert not offenders, (
        "Runtime path reads a legacy AST field that A2 plans to delete; "
        "switch it to the canonical Word field:\n"
        + "\n".join(
            f"  {attr}\n    " + "\n    ".join(hits)
            for attr, hits in offenders.items()
        )
    )


def test_locked_attr_list_is_nonempty_and_specific():
    """Guard against an empty/typo'd lock list silently passing."""
    assert len(LOCKED_LEGACY_ATTRS) == 5
    assert all(a.startswith('.') for a in LOCKED_LEGACY_ATTRS)
