"""M8 mutation harness: each lock must fail for its OWN reason.

cp-based instrument (never `git checkout` over uncommitted work). Restores from
the backup and drops the target's __pycache__ entries afterwards; the restore
is idempotence-checked by hashing the file before mutating and after restoring.
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]

MUTATIONS = [
    # (id, target, old, new, the lock that MUST catch it)
    ('M8-1-reflatten', 'psh/expansion/operands.py',
     "                    builder.splice_values(values, True)\n"
     "                    saw_producer = True",
     "                    builder.emit(' '.join(values), True)\n"
     "                    saw_producer = True",
     'test_m8_lock_operand_at_is_not_flattened'),
    ('M8-2-assign-preserves', 'psh/expansion/operators.py',
     "expanded_default = self._expand_operand(operand, quote_ctx).as_scalar()",
     "expanded_default = ' '.join(\n"
     "            f.text for f in self._expand_operand(operand, quote_ctx).fields[:1])",
     'test_m8_lock_assignment_still_projects'),
    ('M8-4-view-branch-off', 'psh/expansion/operands.py',
     "                fields = self.expand_to_fields(",
     "                fields = None and self.expand_to_fields(",
     'test_m8_lock_view_operand_content_is_a_producer'),
    ('M8-5-redirect-arity', 'psh/expansion/operands.py',
     "        if text.startswith('$@', i):\n            return list(self.state.positional_params), i + 2",
     "        if text.startswith('$@', i):\n            return [' '.join(self.state.positional_params)], i + 2",
     'test_m8_lock_redirect_target_arity'),
    ('M8-3-empty-collapse', 'psh/expansion/operands.py',
     "            return [ExpandedField([_run('', empty_protected)])]",
     "            return [ExpandedField([_run('', True)])]",
     'test_m8_lock_empty_field_distinction_survives'),
]

TESTS = 'tests/conformance/bash/test_operand_field_ir_conformance.py'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def drop_pycache(target):
    for pyc in (target.parent / '__pycache__').glob(f'{target.stem}.*'):
        pyc.unlink()


def run_lock(lock):
    r = subprocess.run(
        [sys.executable, '-m', 'pytest', f'{TESTS}::{lock}', '-q',
         '--no-header'],
        cwd=ROOT, capture_output=True, text=True, timeout=180)
    return r.returncode, r.stdout


def main():
    print(f"tree: {ROOT}")
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()
    print(f"HEAD: {head}\n")
    for mid, rel, old, new, lock in MUTATIONS:
        target = ROOT / rel
        backup = target.with_suffix('.py.m8bak')
        before = sha(target)
        shutil.copy2(target, backup)
        src = target.read_text()
        if src.count(old) != 1:
            print(f"[{mid}] SKIP: anchor found {src.count(old)}x in {rel}")
            backup.unlink()
            continue
        target.write_text(src.replace(old, new))
        drop_pycache(target)
        try:
            rc, out = run_lock(lock)
            verdict = 'CAUGHT (lock failed as required)' if rc != 0 else \
                      '*** NOT CAUGHT — THE LOCK IS VACUOUS ***'
            tail = [ln for ln in out.splitlines()
                    if ln.startswith(('E  ', 'FAILED', '1 failed', '1 passed'))]
            print(f"[{mid}] mutating {rel}\n    lock {lock}\n    -> {verdict}")
            for ln in tail[:4]:
                print(f"       {ln}")
        finally:
            shutil.copy2(backup, target)
            backup.unlink()
            drop_pycache(target)
            after = sha(target)
            assert after == before, f"RESTORE FAILED for {rel}"
            print(f"    restored, sha match: {after[:12]}")
        print()


if __name__ == '__main__':
    main()
