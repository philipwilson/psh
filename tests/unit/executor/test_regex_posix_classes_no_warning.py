"""No Python FutureWarning may leak from the ``=~`` POSIX-class translation
(reappraisal #16 ledger item e).

Before the fix, ``[[ x =~ [[:punct:]] ]]`` compiled ``[[:punct:]]`` as a raw
Python regex, emitting ``FutureWarning: Possible nested set`` to stderr in
default mode. A subprocess is used so the real interpreter stderr is inspected
(warnings bypass in-process capture), and ``-W error::FutureWarning`` promotes
any residual warning to a hard error.
"""

import subprocess
import sys

import pytest

_CLASSES = ['alpha', 'digit', 'alnum', 'upper', 'lower', 'xdigit',
            'blank', 'space', 'punct', 'graph', 'print', 'cntrl']


def _run(script, warnings_error=False):
    cmd = [sys.executable]
    if warnings_error:
        cmd += ['-W', 'error::FutureWarning']
    cmd += ['-m', 'psh', '-c', script]
    return subprocess.run(cmd, capture_output=True, text=True)


class TestNoFutureWarning:
    @pytest.mark.parametrize("cls", _CLASSES)
    def test_class_no_warning(self, cls):
        r = _run(f'[[ h =~ [[:{cls}:]] ]]; echo $?')
        assert "FutureWarning" not in r.stderr
        assert "nested set" not in r.stderr

    @pytest.mark.parametrize("cls", _CLASSES)
    def test_grouped_class_no_warning(self, cls):
        r = _run(f'[[ ab1 =~ ([[:{cls}:]]+) ]]; echo $?')
        assert "FutureWarning" not in r.stderr
        assert "nested set" not in r.stderr

    @pytest.mark.parametrize("cls", _CLASSES)
    def test_class_warnings_as_errors(self, cls):
        # -W error::FutureWarning: a residual warning would make psh exit
        # nonzero with a traceback; a clean run means the class translated.
        r = _run(f'[[ h =~ [[:{cls}:]] ]]', warnings_error=True)
        assert "FutureWarning" not in r.stderr
        assert "Traceback" not in r.stderr
