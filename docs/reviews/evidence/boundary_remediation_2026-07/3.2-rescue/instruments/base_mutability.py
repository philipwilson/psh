#!/usr/bin/env python3
"""A2 — mutability census + DEMONSTRATED cache poisoning at base (MEDIUM-6 red arm).

Every demo is caller-visible: mutate an object obtained from a normal compile,
then show a LATER INDEPENDENT lookup (fresh compile call, or a fresh shell
command) returns the poisoned behavior.

Run: cd <worktree>/tmp/slot32 && PSH_ROOT=<wt> PYTHONPATH=<wt> python3 base_mutability.py
"""
import dataclasses
import os
import sys

PSH_ROOT = os.environ.get('PSH_ROOT', '/Users/pwilson/src/psh-r3-2')

import psh  # noqa: E402
import psh.expansion.pattern_engine as pe  # noqa: E402
from psh.shell import Shell  # noqa: E402

f = os.path.realpath(pe.__file__)
if not f.startswith(os.path.realpath(PSH_ROOT) + os.sep):
    sys.exit(f"DISCRIMINATOR FAIL: {f}")
print(f"# discriminator OK: {psh.__file__}  version={psh.version.__version__}")

C = pe.PatternCompiler.compile
FAILS = []


def check(name, condition, detail=''):
    status = 'POISONED' if condition else 'not-poisoned'
    print(f"  [{status:12}] {name}  {detail}")
    if not condition:
        FAILS.append(name)


print("\n" + "=" * 78)
print("A2-a  STATIC census: which attributes of the compiled representation are writable")
print("=" * 78)
for cls in (pe.Literal, pe.AnyChar, pe.Star, pe.Bracket, pe.Extglob, pe.Sequence):
    is_dc = dataclasses.is_dataclass(cls)
    frozen = getattr(getattr(cls, '__dataclass_params__', None), 'frozen', None)
    slots = getattr(cls, '__slots__', None)
    fields = [fld.name for fld in dataclasses.fields(cls)] if is_dc else []
    print(f"  {cls.__name__:10} dataclass={is_dc!s:5} frozen={frozen!s:5} "
          f"__slots__={slots!s:8} fields={fields}")
print(f"  MatchProfile frozen={pe.MatchProfile.__dataclass_params__.frozen} (already immutable)")
print(f"  CompiledPattern __slots__={pe.CompiledPattern.__slots__} "
      f"(slot 'root' is REBINDABLE)")
print("\n  caches in scope:")
print(f"    compile_cached          {pe.compile_cached.cache_info()}  maxsize=4096")
from psh.expansion.parameter_expansion import _sub_machinery_cached  # noqa: E402
print(f"    _sub_machinery_cached   {_sub_machinery_cached.cache_info()}  maxsize=512")

print("\n" + "=" * 78)
print("A2-b  DEMO 1 — Literal.char mutation poisons a later INDEPENDENT compile")
print("=" * 78)
a = C('abc')
print(f"  before: compile('abc').full_match('abc') = {C('abc').full_match('abc')}")
a.root.elements[0].char = 'z'          # honest-caller accident: node attr write
b = C('abc')                            # LATER INDEPENDENT lookup (cache hit)
check('Literal.char', b.full_match('abc') is False and b.full_match('zbc') is True,
      f"after: full_match('abc')={b.full_match('abc')} full_match('zbc')={b.full_match('zbc')}")
pe.compile_cached.cache_clear()

print("\n" + "=" * 78)
print("A2-c  DEMO 2 — Sequence.bash_quirk lazy bit flip changes the MATCHER ROUTE")
print("=" * 78)
p = '*!(a)'
subj = 'a'
truth = C(p).full_match(subj)
pe.compile_cached.cache_clear()
r = C(p).root
pe._seq_bash_quirk(r)                   # force the lazy bit
r.bash_quirk = False                    # honest-caller accident
poisoned = C(p).full_match(subj)        # LATER INDEPENDENT lookup
check('Sequence.bash_quirk', poisoned != truth,
      f"true(quirk)={truth} poisoned(non-quirk route)={poisoned} on {p!r} vs {subj!r}")
pe.compile_cached.cache_clear()

print("\n" + "=" * 78)
print("A2-d  DEMO 3 — Extglob.enclosed stamp flip changes end-of-string negation")
print("=" * 78)
p, subj = '*!(a)', ''
truth = C(p).full_match(subj)
pe.compile_cached.cache_clear()
r = C(p).root
eg = [e for e in r.elements if type(e) is pe.Extglob][0]
eg.enclosed = True                      # flip the parser stamp
poisoned = C(p).full_match(subj)
check('Extglob.enclosed', poisoned != truth,
      f"true={truth} poisoned={poisoned} on {p!r} vs {subj!r}")
pe.compile_cached.cache_clear()

print("\n" + "=" * 78)
print("A2-e  DEMO 4 — Sequence.elements REBIND (tuple is immutable, the slot is not)")
print("=" * 78)
truth = C('xy').full_match('xy')
pe.compile_cached.cache_clear()
C('xy').root.elements = (pe.Literal('q'),)
poisoned = C('xy').full_match('xy')
check('Sequence.elements rebind', truth is True and poisoned is False,
      f"true={truth} poisoned={poisoned}")
pe.compile_cached.cache_clear()

print("\n" + "=" * 78)
print("A2-f  DEMO 5 — Sequence.sub_fast flip changes the SUBSTITUTION dispatch")
print("=" * 78)
from psh.expansion import parameter_expansion as pex  # noqa: E402
pat = '+([[:space:]])'
_c, _w, _e, fast_ok_true = pex._sub_machinery_cached(pat, 'any', True)
pex._sub_machinery_cached.cache_clear()
pe.compile_cached.cache_clear()
root = C(pat).root
pe.sub_fast_eligible(root)
root.sub_fast = False                   # flip the lazy bit
_c2, _w2, _e2, fast_ok_poisoned = pex._sub_machinery_cached(pat, 'any', True)
check('Sequence.sub_fast', fast_ok_true != fast_ok_poisoned,
      f"true fast_ok={fast_ok_true} poisoned fast_ok={fast_ok_poisoned} "
      f"(dispatch: linear Path A vs _BashMatcher envelope)")
pex._sub_machinery_cached.cache_clear()
pe.compile_cached.cache_clear()

print("\n" + "=" * 78)
print("A2-g  DEMO 6 — poisoning is visible THROUGH THE SHELL (end-to-end, no engine API)")
print("=" * 78)
sh = Shell()
sh.run_command('shopt -s extglob')
sh.run_command('v=abc; r=${v//abc/HIT}')
before = sh.state.get_variable('r')
# The shell's own compile populated compile_cached; poison that cached node.
node = pe.compile_cached('abc', True).elements[0]
node.char = 'z'
sh.run_command('v=abc; r=${v//abc/HIT}')
after_abc = sh.state.get_variable('r')
sh.run_command('v=zbc; r=${v//abc/HIT}')
after_zbc = sh.state.get_variable('r')
check('end-to-end via Shell',
      before == 'HIT' and after_abc == 'abc' and after_zbc == 'HIT',
      f"before={before!r} after(v=abc)={after_abc!r} after(v=zbc)={after_zbc!r}")
pe.compile_cached.cache_clear()

print("\n" + "=" * 78)
print("A2-h  DEMO 7 — _sub_machinery_cached hands out the SAME CompiledPattern objects")
print("=" * 78)
t1 = pex._sub_machinery_cached('a*', 'any', True)
t2 = pex._sub_machinery_cached('a*', 'any', True)
check('_sub_machinery_cached aliasing',
      t1[0] is t2[0] and t1[1] is t2[1],
      f"compiled is compiled: {t1[0] is t2[0]}, wrapped is wrapped: {t1[1] is t2[1]} "
      f"(so a write through either poisons every later consumer)")
# and the CompiledPattern.root slot itself is rebindable
cp = t1[0]
cp.root = C('zzz').root
check('CompiledPattern.root rebind',
      pex._sub_machinery_cached('a*', 'any', True)[0].root is cp.root,
      "later cache hit returns the rebound root")
pex._sub_machinery_cached.cache_clear()
pe.compile_cached.cache_clear()

print("\n" + "=" * 78)
print(f"SUMMARY: {7 - len(FAILS)}/7 poisoning demos reproduced at base.")
if FAILS:
    print(f"  NOT reproduced: {FAILS}")
print("=" * 78)
