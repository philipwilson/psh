"""INSTR07 v2 — CLOSE design emulation, REDIRECT-SCOPED, with tripwires.

v1 was invalid and is recorded as instrument defect ID-3: it pushed/popped
the WHOLE fd map on EVERY builtin frame, so a plain `read` with no redirect
lost its cursor at pop — destroying the I1 same-fd must-hold and "fixing"
the temp-frame face by DESTROYING the surplus rather than scoping it. Its
dup half never fired at all (no tripwire, so silence looked like a result).

v2:
  * temp-frame hook fires ONLY for fds the command actually redirects, and
    PRESERVES the outer binding (push aside intact, restore intact);
  * dup hook goes where the drop currently happens —
    `_rebind_input_cursors_after_exec` — turning `exec 3<&0` from
    "drop fd 3's cursor" into "fd 3 ALIASES fd 0's description";
  * both hooks announce themselves on stderr (PSH_CLOSE_TRACE=1), so a hook
    that never runs cannot be mistaken for a design that does not work.
"""
import os
import sys

TRACE = os.environ.get('PSH_CLOSE_TRACE') == '1'


def _t(msg):
    if TRACE:
        print(f"[CLOSE-EMU] {msg}", file=sys.stderr)


try:
    from psh.io_redirect.input_cursor import InputCursorRegistry
    from psh.io_redirect.manager import IOManager
    from psh.executor.command import CommandExecutor
except Exception as e:                                   # not a psh run
    _t(f"import failed: {e}")
else:
    def _reg_of(obj):
        st = getattr(obj, 'state', None)
        if st is None:
            st = getattr(getattr(obj, 'shell', None), 'state', None)
        return getattr(st, 'input_cursors', None)

    # ---- temp-frame isolation (REDIRECT-SCOPED) -------------------------
    _INPUT_TYPES = {'<', '<<', '<<<', '<<-', '<&'}

    def _target_fds(command):
        fds = set()
        for r in getattr(command, 'redirects', None) or []:
            fd = getattr(r, 'fd', None)
            if fd is None:
                fd = 0 if getattr(r, 'type', None) in _INPUT_TYPES else 1
            fds.add(fd)
        return fds

    _orig_setup = IOManager.setup_builtin_redirections
    _orig_restore = IOManager.restore_builtin_redirections

    def _setup(self, command):
        fds = _target_fds(command)
        reg = _reg_of(self)
        saved = None
        if fds and reg is not None:
            # Set aside the OUTER binding for each redirected fd and remove
            # it, so the frame's read gets its OWN description/cursor.
            saved = {fd: reg._fd_to_desc.pop(fd, None) for fd in fds}
            _t(f"frame ENTER fds={sorted(fds)} saved={saved}")
        frame = _orig_setup(self, command)
        if saved is not None:
            self._close_emu_stack = getattr(self, '_close_emu_stack', [])
            self._close_emu_stack.append(saved)
        return frame

    def _restore(self, frame):
        try:
            return _orig_restore(self, frame)
        finally:
            stack = getattr(self, '_close_emu_stack', None)
            reg = _reg_of(self)
            if stack and reg is not None:
                saved = stack.pop()
                for fd, desc in saved.items():
                    # Drop whatever the frame bound, restore the outer one.
                    inner = reg._fd_to_desc.pop(fd, None)
                    if inner is not None:
                        reg._desc_to_cursor.pop(inner, None)
                    if desc is not None:
                        reg._fd_to_desc[fd] = desc
                _t(f"frame LEAVE restored={saved}")

    IOManager.setup_builtin_redirections = _setup
    IOManager.restore_builtin_redirections = _restore

    # ---- dup aliasing ---------------------------------------------------
    def _bind_dup(self, new_fd, old_fd):
        """Alias new_fd onto old_fd's description.

        DESIGN FINDING (v2 tripwire): the registry is populated LAZILY —
        at `exec 3<&0` time fd 0 usually has NO description yet, because
        nothing has read from it. So the alias cannot simply copy an
        existing entry; the source description must be MATERIALIZED first.
        """
        desc = self._fd_to_desc.get(old_fd)
        if desc is None:
            desc = OpenDescription(f"fd{old_fd}")     # materialize
            self._fd_to_desc[old_fd] = desc
        self._fd_to_desc[new_fd] = desc
        return True

    InputCursorRegistry.bind_dup = _bind_dup

    # Second half of the same finding: `cursor_for_fd` currently OVERWRITES
    # an existing description when no cursor is attached to it yet, which
    # would silently destroy the alias the dup just created. A real
    # implementation must REUSE the description it finds.
    from psh.io_redirect.input_cursor import OpenDescription, make_reader

    def _cursor_for_fd(self, io_ctx, fd):
        desc = self._fd_to_desc.get(fd)
        if desc is not None:
            cursor = self._desc_to_cursor.get(desc)
            if cursor is not None:
                return cursor
        cursor = make_reader(io_ctx, fd)
        if cursor.fd is None:
            return cursor
        if desc is None:                      # <- REUSE, do not overwrite
            desc = OpenDescription(f"fd{fd}")
            self._fd_to_desc[fd] = desc
        self._desc_to_cursor[desc] = cursor
        return cursor

    InputCursorRegistry.cursor_for_fd = _cursor_for_fd

    _orig_rebind = CommandExecutor._rebind_input_cursors_after_exec

    def _rebind(self, redirects):
        reg = self.state.input_cursors
        handled = set()
        for r in redirects:
            _t(f"exec redirect: type={getattr(r,'type',None)!r} "
               f"fd={getattr(r,'fd',None)!r} dup_fd={getattr(r,'dup_fd',None)!r} "
               f"target={getattr(r,'target',None)!r}")
            src = getattr(r, 'dup_fd', None)
            dst = getattr(r, 'fd', None)
            if src is None and getattr(r, 'type', None) == '<&':
                tgt = getattr(r, 'target', None)
                if tgt is not None and str(tgt).isdigit():
                    src = int(tgt)
            if src is not None and dst is not None:
                ok = reg.bind_dup(dst, src)
                _t(f"  -> bind_dup({dst} <- {src}) = {ok}")
                handled.add(id(r))
        rest = [r for r in redirects if id(r) not in handled]
        return _orig_rebind(self, rest)

    CommandExecutor._rebind_input_cursors_after_exec = _rebind
    _t("hooks installed")
