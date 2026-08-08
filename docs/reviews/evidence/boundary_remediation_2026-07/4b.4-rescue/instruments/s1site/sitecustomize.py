"""INSTR06 support: apply the s1-toward-bash emulation inside a psh CHILD.

Python imports `sitecustomize` automatically at interpreter startup, so
putting this directory FIRST on PYTHONPATH makes `python -m psh` run with
the emulation active. This lets the SHELL-LEVEL census cells be re-measured
under the candidate ruling without editing production code.
"""
try:
    from psh.builtins.input_reader import InputCursor, Outcome
except Exception:                                    # not a psh run
    pass
else:
    _orig = InputCursor._read

    def _read_assigning_partial_at_timeout(self, **kw):
        res = _orig(self, **kw)
        if res.outcome is Outcome.TIMEOUT and self._decoder is not None:
            tail = self._decoder.decode(b'', final=True)
            self._decoder = None
            if tail:
                res.data = res.data + tail
        return res

    InputCursor._read = _read_assigning_partial_at_timeout
