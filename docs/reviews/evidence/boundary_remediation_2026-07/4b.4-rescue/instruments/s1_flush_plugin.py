"""INSTR05 plugin — EMULATE the s1-toward-bash disposition, without editing
production code.

bash assigns a stranded partial multibyte to the read that timed out; psh
holds it on the cursor. This plugin makes psh behave like bash: on a TIMEOUT
outcome, finalize the incremental decoder and append the resulting
surrogate(s) to the timed-out read's data.

It is loaded with `-p s1_flush_plugin` (PYTHONPATH points at tmp/w4b4), so
the tree under test is NEVER modified — no mutation to apply, no revert to
forget, and `git status` stays clean throughout. PYTHONDONTWRITEBYTECODE is
set by the driver (4B.2 lesson 2).

PURPOSE: measure what the s1-toward-bash ruling would COST in already-shipped
4B.2 pins. This is a cost instrument, not a proposed implementation.
"""
from psh.builtins.input_reader import InputCursor, Outcome

_orig_read = InputCursor._read


def _read_assigning_partial_at_timeout(self, **kw):
    res = _orig_read(self, **kw)
    if res.outcome is Outcome.TIMEOUT and self._decoder is not None:
        tail = self._decoder.decode(b'', final=True)
        self._decoder = None          # decoder is now clean, like bash's state
        if tail:
            res.data = res.data + tail
    return res


InputCursor._read = _read_assigning_partial_at_timeout
print("[s1_flush_plugin] ACTIVE: partial multibyte is ASSIGNED at timeout "
      "(bash-alike), decoder finalized.")
