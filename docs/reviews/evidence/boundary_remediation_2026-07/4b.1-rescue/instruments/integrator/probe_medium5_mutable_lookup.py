"""Brief-time evidence probe for slot 4B.1 (MEDIUM-5), at base 4f2facaf.

Run as a subprocess from the repo root. Three legs:
  1. _MISSING poisoning: mutate the shared missing singleton -> every
     future miss (any name, any shell in-process) reads as SET; observable
     end-to-end through ${x+w}.
  2. Readonly bypass: lookup(name).binding is the LIVE Variable cell;
     assigning .value skips ReadonlyVariableError and changes shell reads.
  3. Export/observer desync: the same write skips the variable_changed
     observer, so state.env keeps the old value (shell reads vs child env
     disagree).
"""
import psh
print("DISCRIMINATOR:", psh.__file__)
from psh.shell import Shell  # noqa: E402
from psh.core.variable_lookup import LookupStatus  # noqa: E402

sh = Shell(norc=True)
sm = sh.state.scope_manager

# --- Leg 1: _MISSING poisoning -------------------------------------------
before = sh.run_and_capture = None  # (no helper; use run_command + $? out)
r = sm.lookup('DEFINITELY_UNSET_A')
print("leg1 pre: status", r.status.name, "| ${u+SET} expands:",
      sm.lookup('DEFINITELY_UNSET_B').is_set)
r.status = LookupStatus.VALUE          # mutating the SHARED singleton
r.value = 'POISON'
r2 = sm.lookup('COMPLETELY_DIFFERENT_UNSET_NAME')
print("leg1 post-mutation, DIFFERENT name:", r2.status.name, repr(r2.value),
      "| is_set:", r2.is_set)
rc = sh.run_command('x=${SOME_OTHER_UNSET+FIRED}; echo "plus-expansion:<$x>"')
# restore so later legs are honest
r.status = LookupStatus.MISSING
r.value = None
print("leg1 restored:", sm.lookup('DEFINITELY_UNSET_C').status.name)

# --- Leg 2: readonly bypass via .binding.value ---------------------------
sh.run_command('readonly RO_PROBE=original')
rc_normal = sh.run_command('RO_PROBE=blocked 2>/dev/null')
print("leg2 normal write path rc:", rc_normal, "(refused)")
lk = sm.lookup('RO_PROBE')
lk.binding.value = 'hacked-past-readonly'   # no error raised
sh.run_command('echo "leg2 shell read after binding write: <$RO_PROBE>"')

# --- Leg 3: exported-env desync ------------------------------------------
sh.run_command('export EX_PROBE=one')
lk2 = sm.lookup('EX_PROBE')
lk2.binding.value = 'two'
print("leg3 shell read:", sh.state.get_variable('EX_PROBE'),
      "| state.env:", sh.state.env.get('EX_PROBE'), "(DESYNC)")
sh.close()
