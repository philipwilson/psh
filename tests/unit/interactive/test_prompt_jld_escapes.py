"""PS1 \\j, \\l and \\D{format} escapes (reappraisal #17 L2).

bash-pinned via ${PS1@P} (tmp/probes-r17t2-interactive/): \\j is the
number of jobs the shell currently manages, \\l the basename of the
terminal device ('tty' when stdin is not a terminal — the case in this
in-process suite), \\D{format} is strftime(3) with an empty format
meaning the locale's time representation; \\D without {...} stays
literal.
"""

import datetime

from psh.executor.job_control import JobState
from psh.shell import Shell


def _expand(sh, prompt):
    return sh.interactive_manager.prompt_manager.expand_prompt(prompt)


def test_j_zero_jobs():
    sh = Shell(norc=True)
    assert _expand(sh, r'[\j]') == '[0]'


def test_j_counts_managed_jobs():
    sh = Shell(norc=True)
    job = sh.job_manager.create_job(999_999, 'sleep 40')
    job.notified = True
    try:
        assert _expand(sh, r'[\j]') == '[1]'
        job.state = JobState.STOPPED
        assert _expand(sh, r'[\j]') == '[1]'  # stopped jobs still count
    finally:
        sh.job_manager.jobs.clear()


def test_l_falls_back_to_tty_without_terminal():
    # bash prints the literal 'tty' when ttyname(stdin) fails; under
    # pytest stdin is not a terminal, making this deterministic. (The
    # real-device case is covered by the @P probe on a PTY.)
    sh = Shell(norc=True)
    result = _expand(sh, r'[\l]')
    assert result.startswith('[') and result.endswith(']')
    inner = result[1:-1]
    assert inner == 'tty' or inner.startswith('tty')  # ttysNNN on a tty


def test_D_with_strftime_format():
    sh = Shell(norc=True)
    year = datetime.datetime.now().strftime('%Y')
    assert _expand(sh, r'<\D{%Y}>') == f'<{year}>'


def test_D_empty_format_is_locale_time():
    # bash: \D{} renders strftime('%X') (locale time representation).
    sh = Shell(norc=True)
    before = datetime.datetime.now()
    result = _expand(sh, r'\D{}')
    after = datetime.datetime.now()
    assert result in (before.strftime('%X'), after.strftime('%X'))


def test_D_without_braces_stays_literal():
    sh = Shell(norc=True)
    assert _expand(sh, r'[\D]x') == r'[\D]x'


def test_D_unclosed_brace_formats_rest_of_string():
    # bash: '[\D{%Y]' -> '[' + strftime('%Y]') -> '[2026]'
    sh = Shell(norc=True)
    year = datetime.datetime.now().strftime('%Y')
    assert _expand(sh, r'[\D{%Y]') == f'[{year}]'


def test_D_format_output_protected_from_dollar_expansion():
    # Escape output must not be re-expanded (the existing @P policy).
    sh = Shell(norc=True)
    assert _expand(sh, r'\D{$(echo X)}') == '$(echo X)'
