import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psh.version
assert psh.version.__version__ == '0.750.0', psh.version.__version__
from psh.shell import Shell

print("=== Claim B part 1 (precise): readonly + export bypass, env not updated ===")
sh = Shell()
sh.run_command("export RO=original; readonly RO")
lk = sh.state.scope_manager.lookup('RO')
print("binding.is_readonly:", lk.binding.is_readonly, "; binding.is_exported:", lk.binding.is_exported)
print("env['RO'] before:", repr(sh.state.env.get('RO')))

lk.binding.value = 'HACKED'   # mutate live cell through the read view

print("after binding.value='HACKED':")
print("   binding.is_readonly still:", lk.binding.is_readonly, "(cell still readonly, value changed anyway)")
print("   shell read $RO:", repr(sh.state.get_variable('RO')), " <-- changed")
print("   exported env['RO']:", repr(sh.state.env.get('RO')), " <-- STALE: still 'original'")

# Confirm a child process would inherit the STALE exported value, not 'HACKED'.
rc = sh.run_command("printf 'child sees RO=%s\\n' \"$(bash -c 'echo $RO')\"")
