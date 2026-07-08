"""Meta-test: docs/reviews/README.md indexes every review file.

The reviews index had rotted — it named an older ground-up appraisal as the
latest while five newer reviews sat unlisted (finding D5 of the 2026-07-06
tests/docs appraisal). This test makes the index self-correcting: every
``*.md`` in ``docs/reviews/`` (except the index itself) must be linked from the
index, so a newly added review can't silently go unlisted.

When this fails, add a one-line row for the new file to
``docs/reviews/README.md`` under the appropriate section.
"""

import os
import re

HERE = os.path.dirname(__file__)
REPO_ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
REVIEWS_DIR = os.path.join(REPO_ROOT, 'docs', 'reviews')
INDEX = os.path.join(REVIEWS_DIR, 'README.md')

# A markdown link target: the "(target)" that follows a "[text]". Anchoring on
# "](" avoids mistaking a parenthesized inline link for a bare "(path)".
_LINK_RE = re.compile(r'\]\(([^)]+?)\)')


def _linked_targets(index_text):
    """Set of raw link targets (paths, anchors stripped) in the index."""
    return {m.group(1).split('#', 1)[0] for m in _LINK_RE.finditer(index_text)}


def _linked_basenames(index_text):
    """Set of review-file basenames linked from the index text."""
    return {os.path.basename(t) for t in _linked_targets(index_text)
            if t.endswith('.md')}


def _review_files():
    return [name for name in os.listdir(REVIEWS_DIR)
            if name.endswith('.md') and name != 'README.md']


def test_every_review_file_is_indexed():
    linked = _linked_basenames(open(INDEX).read())
    missing = sorted(f for f in _review_files() if f not in linked)
    # Show the exact index-row format so a new review (or a batch copied in at
    # integration time) can be added mechanically.
    rows = "\n".join(
        f"| [{f[:-3]}]({f}) | <one-line description> |" for f in missing)
    assert not missing, (
        "Review files not linked from docs/reviews/README.md (finding D5): "
        f"{missing}. Add a one-line row for each under the appropriate section "
        f"of the index (Live / Completed / Historical). Row format:\n{rows}")


def test_index_links_resolve():
    """Every .md link in the index must resolve (relative to the reviews dir),
    including the cross-directory links (../../CHANGELOG.md, ../learning_path.md)."""
    targets = [t for t in _linked_targets(open(INDEX).read())
               if t.endswith('.md')]
    broken = sorted(
        t for t in targets
        if not os.path.exists(os.path.normpath(os.path.join(REVIEWS_DIR, t))))
    assert not broken, (
        f"docs/reviews/README.md links to nonexistent files: {broken}.")


def test_linked_basenames_detects_links():
    """Self-test of the link parser (so the guard can't silently go vacuous)."""
    sample = ("See [x](foo_2026-01-01.md) and [y](bar.md#section) but not "
              "code.md, and a wrapped ([#9](baz.md)) link.")
    found = _linked_basenames(sample)
    assert 'foo_2026-01-01.md' in found
    assert 'bar.md' in found            # anchor stripped
    assert 'baz.md' in found            # parenthesized inline link handled
    assert 'code.md' not in found       # bare text, not a link
    # The parser must not swallow the outer paren into the target.
    assert '[#9](baz.md' not in _linked_targets(sample)
