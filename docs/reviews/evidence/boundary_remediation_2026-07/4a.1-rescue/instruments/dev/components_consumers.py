"""Site-completeness sweep (ruling (a)): every consumer of the coordinator's
component/activation state in process_lease.py, derived from the AST — a
PROPERTY of the file, not an enumeration from memory.

Reports each function that reads `self._components` or `self._activations`
and whether it filters by per-lease `owner_ref`.  Run:
    python components_consumers.py <path-to-process_lease.py>
"""
import ast
import sys


def main(path):
    src = open(path).read()
    tree = ast.parse(src)
    rows = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        seg = ast.get_source_segment(src, node) or ""
        reads_comp = '_components' in seg
        reads_act = '_activations' in seg
        if not (reads_comp or reads_act):
            continue
        # A genuine PER-LEASE filter is `<lease>.owner_ref` — an attribute
        # access on something that is NOT the coordinator itself.
        # `self._owner_ref` is the coordinator's own field and proves nothing
        # about discrimination; counting it was this instrument's first-draft
        # error and it made every site look already-filtered.
        per_lease = any(
            isinstance(sub, ast.Attribute) and sub.attr == 'owner_ref'
            and not (isinstance(sub.value, ast.Name) and sub.value.id == 'self')
            for sub in ast.walk(node))
        rows.append({
            'func': node.name,
            'line': node.lineno,
            'components': reads_comp,
            'activations': reads_act,
            'owner_ref_filter': per_lease,
        })
    print(f"{'function':32s} {'line':>5s} {'comps':>6s} {'acts':>5s} {'owner_ref?':>10s}")
    for r in rows:
        print(f"{r['func']:32s} {r['line']:5d} {str(r['components']):>6s} "
              f"{str(r['activations']):>5s} {str(r['owner_ref_filter']):>10s}")
    comp_sites = [r for r in rows if r['components']]
    unfiltered = [r for r in comp_sites if not r['owner_ref_filter']]
    print(f"\nDERIVED: functions reading _components = {len(comp_sites)}")
    print(f"DERIVED: of those, WITHOUT any owner_ref filter = {len(unfiltered)}")
    print("UNFILTERED: " + ", ".join(f"{r['func']}:{r['line']}" for r in unfiltered))


if __name__ == '__main__':
    main(sys.argv[1])
