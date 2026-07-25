"""Ownership of the live lazy SCRIPT_FILE descriptor (campaign I2, #20 H14).

The lazy reader keeps the script descriptor OPEN for the script's lifetime,
relocated to a high CLOEXEC slot and owned by the source. It must not be
inheritable by children, must not perturb `{v}` numbering, and must not be
clobbered by a user redirect — bash owns its fd 255 the same way. All cases
are bash-compared.

Permanent-fd / exec redirection -> subprocess (this dir is auto-marked serial).
"""
from shell_oracle import is_comparable, run_bash, run_psh


def _cmp(tmp_path, script, stdin=None):
    (tmp_path / "psh").mkdir(exist_ok=True)
    (tmp_path / "bash").mkdir(exist_ok=True)
    pp = tmp_path / "psh" / "s.sh"
    pp.write_text(script)
    bp = tmp_path / "bash" / "s.sh"
    bp.write_text(script)
    # No caller passes `stdin` today (so nothing currently flows through the
    # data path), but the pre-migration helper used subprocess `input=`, i.e. a
    # PIPE. Carry the conditional idiom anyway so a future caller that DOES
    # supply data gets fd 0 of the kind this module's siblings assume, rather
    # than a silently seekable file.
    mode = 'pipe' if stdin is not None else 'file'
    psh = run_psh([str(pp)], cwd=str(tmp_path / "psh"), stdin_data=stdin,
                  stdin_mode=mode)
    assert is_comparable(psh), psh
    bash = run_bash([str(bp)], cwd=str(tmp_path / "bash"), stdin_data=stdin,
                    stdin_mode=mode)
    assert is_comparable(bash), bash
    return psh, bash


def test_external_child_does_not_inherit_script_fd(tmp_path):
    # A forked+exec'd child (external sh) must not see the script descriptor
    # (CLOEXEC). Neither shell lists any open high fd.
    script = ('echo START\n'
              '/bin/sh -c \'for fd in 250 255 256 260; do '
              ': <&$fd 2>/dev/null && echo "open:$fd"; done\'\n'
              'echo END\n')
    psh, bash = _cmp(tmp_path, script)
    assert psh.stdout == bash.stdout == "START\nEND\n"


def test_exec_image_does_not_inherit_script_fd(tmp_path):
    # `exec` replacing the image: the new image must not inherit the script fd.
    script = ('echo BEFORE\n'
              'exec /bin/sh -c \'for fd in 250 255 256; do '
              ': <&$fd 2>/dev/null && echo "open:$fd"; done; echo AFTER\'\n')
    psh, bash = _cmp(tmp_path, script)
    assert psh.stdout == bash.stdout == "BEFORE\nAFTER\n"


def test_named_fd_still_allocates_10(tmp_path):
    # The live script fd (relocated high) must not perturb `{v}` numbering.
    script = 'exec {a}>/dev/null {b}>/dev/null\necho "$a $b"\n'
    psh, bash = _cmp(tmp_path, script)
    assert psh.stdout == bash.stdout == "10 11\n"


def test_exec_redirect_to_reserved_fd_relocates_not_clobbers(tmp_path):
    # A PERMANENT `exec` to the reserved fd (bash's 255) must relocate the
    # script source, not clobber it: the script keeps running AND sees an
    # append (probe O1).
    script = ('echo A\nexec 255>/dev/null\n'
              'echo "echo APPENDED" >> "$0"\necho B\n')
    psh, bash = _cmp(tmp_path, script)
    assert psh.stdout == bash.stdout == "A\nB\nAPPENDED\n"
    assert psh.returncode == bash.returncode == 0


def test_exec_close_reserved_fd_relocates(tmp_path):
    # Permanent CLOSE of the reserved fd also relocates (bash-parity).
    script = ('echo A\nexec 255<&-\n'
              'echo "echo APPX" >> "$0"\necho B\n')
    psh, bash = _cmp(tmp_path, script)
    assert psh.stdout == bash.stdout == "A\nB\nAPPX\n"


def test_temp_redirect_to_reserved_fd_is_safe(tmp_path):
    # A TEMPORARY redirect to the reserved fd number save/restores it; the
    # script keeps reading afterward (no relocation needed — bash-parity).
    script = ('echo A\n: 255>/dev/null\necho B\n'
              'echo "echo APP2" >> "$0"\necho C\n')
    psh, bash = _cmp(tmp_path, script)
    assert psh.stdout == bash.stdout


def test_close_fd3_swap_idiom_under_lazy(tmp_path):
    # The classic stdout/stderr swap still works with a live script fd (the
    # relocation test's core case, here bash-compared end to end).
    script = 'exec 3>&1 1>&2 2>&3 3>&-\necho to-stderr\necho to-stdout\n'
    psh, bash = _cmp(tmp_path, script)
    assert psh.returncode == bash.returncode == 0
    assert psh.stdout == bash.stdout
    assert psh.stderr == bash.stderr
