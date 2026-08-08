"""INSTR13 — are these two behaviours actually load-bearing, or did I claim
more than the code does?

Two M8 arms came back NOT CAUGHT. That is either a pin gap (fix the pin) or
an over-claim in my own docstrings (fix the claim). Distinguish, don't paper.

Q1: pop_frame's restore-BEFORE-release order — is there any state where
    releasing first destroys a live cursor?
Q2: scope_fd on a named-fd allocation — what is observably different without
    it?
"""
import os
import sys

REPO = "/Users/pwilson/src/psh-r4b-4"
sys.path.insert(0, REPO)
import psh  # noqa: E402
assert psh.__file__ == REPO + "/psh/__init__.py"
from psh.io_redirect.input_cursor import InputCursorRegistry  # noqa: E402


class Ctx:
    def __init__(self, s): self.stdin = s


ctx = Ctx(open(os.devnull))


def pipe(data=b"x\n"):
    r, w = os.pipe()
    os.write(w, data)
    os.close(w)
    return r


print("Q1 — does release-before-restore destroy a live cursor?")
print("     Case: the SAME fd is scoped by the frame AND its outer binding is")
print("     an alias shared with another fd.")
r = pipe()
try:
    reg = InputCursorRegistry()
    reg.bind_dup(9, r)                 # fd r and fd 9 share one description
    outer = reg.cursor_for_fd(ctx, r)  # cursor lives on that description
    saved = reg.push_frame([r])        # frame scopes fd r itself
    inner = reg.cursor_for_fd(ctx, r)
    # Simulate RELEASE-FIRST: release the frame's binding before restoring.
    dropped = reg._fd_to_desc.pop(r, None)
    reg._release(dropped)              # <- the wrong order
    for fd, d in saved.items():
        if d is not None:
            reg._fd_to_desc[fd] = d
    after = reg.cursor_for_fd(ctx, r)
    print(f"     outer preserved under release-first? {after is outer}")
    print(f"     (fd 9 still names the outer description: "
          f"{reg._fd_to_desc.get(9) is saved[r]})")
finally:
    os.close(r)

print()
print("Q2 — what does scope_fd change for a named-fd allocation?")
r = pipe()
try:
    reg = InputCursorRegistry()
    saved = reg.push_frame([0])        # a frame is open
    reg.scope_fd(11)                   # allocator scopes its new fd
    reg.bind_dup(11, r)
    reg.cursor_for_fd(ctx, 11)
    reg.pop_frame(saved)
    print(f"     WITH scope_fd    -> fd 11 still bound after pop: "
          f"{11 in reg._fd_to_desc}")

    reg2 = InputCursorRegistry()
    saved2 = reg2.push_frame([0])
    reg2.bind_dup(11, r)               # no scope_fd
    reg2.cursor_for_fd(ctx, 11)
    reg2.pop_frame(saved2)
    print(f"     WITHOUT scope_fd -> fd 11 still bound after pop: "
          f"{11 in reg2._fd_to_desc}")
finally:
    os.close(r)
