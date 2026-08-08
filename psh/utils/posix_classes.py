"""The ASCII POSIX character-class table — one copy, owned below both readers.

``[[:alpha:]]`` and friends need a concrete character set whenever the shell
resolves a class without asking libc. Two subsystems need that same table:

* ``core/locale_service.py`` — the C/OTHER-mode answer for
  ``posix_class_ranges`` / ``_ascii_in_class`` (in a UTF-8 locale the service
  sweeps ``iswctype`` instead and never consults this table);
* ``expansion/glob.py`` — the ``fnmatch`` reference oracle's slash-free variant.

The table used to live in ``expansion/glob.py``, which put it ABOVE its other
reader: ``core`` had to reach up into ``expansion`` through two function-body
imports to get at a private name (``from ..expansion.glob import
_POSIX_CLASSES``). Deferring those imports hid a layering inversion rather than
fixing it — core is a near-leaf and must not depend on the expansion machinery.
Remediation 5B.1 moved the data here, to ``psh.utils`` (a true leaf, and one of
the three packages ``core`` may import at module level), so both readers import
DOWNWARD and neither owns the other's copy.

Pure data: this module imports nothing and must keep importing nothing.
"""

#: POSIX character classes -> the character ranges to substitute *inside* an
#: existing bracket expression. Each range is written so it embeds safely both
#: in a Python ``re`` character class AND in stdlib ``fnmatch``: no leading
#: ``!``/``^`` (fnmatch reads those as negation) and no bare ``]``/``\`` (which
#: would close the class or escape). punct/graph/print/cntrl therefore appear as
#: reordered ranges rather than literal metacharacter lists.
POSIX_CLASSES = {
    'alpha': 'a-zA-Z',
    'digit': '0-9',
    'alnum': 'a-zA-Z0-9',
    'upper': 'A-Z',
    'lower': 'a-z',
    'xdigit': '0-9A-Fa-f',
    'blank': ' \t',
    'space': ' \t\n\r\x0b\x0c',
    # 0x21-0x2f, 0x3a-0x40, 0x5b-0x60, 0x7b-0x7e (': ' first so no leading '!').
    'punct': ':-@!-/[-`{-~',
    'graph': '"-~!',            # 0x21-0x7e ('!' moved to the end)
    'print': ' -~',             # 0x20-0x7e
    'cntrl': '\x00-\x1f\x7f',   # 0x00-0x1f and 0x7f (literal control bytes)
}
