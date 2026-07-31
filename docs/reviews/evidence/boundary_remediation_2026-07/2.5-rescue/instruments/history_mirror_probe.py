#!/usr/bin/env python3
"""R4-C(3): the OBSERVABLE consequence of the history-expansion mirror scanner.

`psh/interactive/history_expansion.py#_scan_line_markers_ctx` is a hand-written
MIRROR of the regex heredoc scanner. It still misdetects the MEDIUM-3 spelling,
and it runs ON the session path (command_accumulator._preprocess, feed step 1)
to decide `heredoc_body_spans` -- the regions where history expansion is
SUPPRESSED (bash does not bang-expand inside a here-document body).

So the question this probe answers is not "does the mirror misdetect" (it does,
shown structurally below) but "what does a user SEE". The misdetection can only
matter where the accumulated buffer spans lines AND contains the escaped
spelling, so the case is built to make that happen:

    if true; then
    echo \\<<EOF
    echo !!            <- is this history-expanded, or suppressed as body text?
    fi

Structural, not PTY: history expansion is a text transform on the accumulated
buffer, so the honest instrument is the transform itself. Run at BASE and TIP.

Usage: python3 history_mirror_probe.py
"""
import subprocess
import sys

sys.path.insert(0, "/Users/pwilson/src/psh-r2-5")

from psh.interactive.history_expansion import (          # noqa: E402
    _scan_line_markers_ctx,
    heredoc_body_spans,
)

print("SHA:", subprocess.run(["git", "rev-parse", "HEAD"],
                             cwd="/Users/pwilson/src/psh-r2-5",
                             capture_output=True, text=True).stdout.strip())

print("\n=== 1. The mirror's grammar, directly ===")
for line in (r"echo \<<EOF", "cat <<EOF", "echo '<<EOF'"):
    specs = _scan_line_markers_ctx(line, [], 0)
    got = specs[0] if isinstance(specs, tuple) else specs
    print(f"  {line!r:22} -> mirror specs: {[getattr(s, 'cooked', s) for s in got]}")

print("\n=== 2. heredoc_body_spans over a multi-line buffer ===")
BUF = "if true; then\necho \\<<EOF\necho !!\nfi"
print("  buffer:", repr(BUF))
spans = heredoc_body_spans(BUF)
print("  suppressed-body spans:", spans)
lines = BUF.split("\n")
for i, ln in enumerate(lines):
    inside = any(lo <= i <= hi for lo, hi in spans) if spans else False
    print(f"    line {i}: {ln!r:22} history-suppressed={inside}")

print("\n=== 3. The same buffer WITHOUT the escape (a real heredoc) ===")
REAL = "if true; then\ncat <<EOF\necho !!\nfi"
print("  buffer:", repr(REAL))
print("  suppressed-body spans:", heredoc_body_spans(REAL))
