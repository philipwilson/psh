"""Put the conformance directory on sys.path for every conformance test.

The conformance suite's shared modules — ``conformance_framework`` (the
``ConformanceTest`` base + ``find_bash``) and ``_assert_analysis`` (the shared
AST guard helpers) — live in THIS directory and are imported with bare names
(``from conformance_framework import ConformanceTest``). pytest imports this
conftest before any test module in the tree, so a single sys.path insert here
makes those bare imports resolve everywhere under tests/conformance/ — replacing
the ``sys.path.insert(0, .../conformance)`` stanza that used to head ~80 files
(the single most-repeated stanza in the test tree; reappraisal-#19 tests-infra
M6).

Files that are ALSO meant to be run standalone (``python test_foo.py``, guarded
by an ``if __name__ == '__main__'`` block) keep their own insert, since this
conftest only runs under pytest.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
