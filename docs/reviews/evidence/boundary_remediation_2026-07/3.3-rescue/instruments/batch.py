"""Batched cell runner: many cells per shell invocation (psh startup is ~0.3s).

Each cell runs in its own SUBSHELL so a fatal `:?` aborts only that cell and
`set --` / `:=` stores stay isolated. The observer is a field COUNTER, so
"zero fields" and "one empty field" are distinguishable — the representation
question this slot turns on.
"""
import sys

from harness import PSH_ROOT, bash_version, header, run_bash, run_psh  # noqa: F401

# The observer. n=<count> then one [text] per field. Defined once per batch.
PRELUDE = r"""
count() { printf 'n=%d' "$#"; for a in "$@"; do printf ' [%s]' "$a"; done; printf '\n'; }
"""


def build_script(cells):
    """cells: list of (id, body). body must print its own observation."""
    out = [PRELUDE]
    for cid, body in cells:
        out.append(f"printf 'CELL {cid}\\n'")
        out.append(f"( {body} ) 2>&1")
        out.append("printf 'RC %d\\n' \"$?\"")
    return '\n'.join(out) + '\n'


def parse(text):
    """Split marked output into {cell_id: (body_lines, rc)}."""
    res = {}
    cur = None
    buf = []
    for line in text.splitlines():
        if line.startswith('CELL '):
            cur = line[5:].strip()
            buf = []
        elif line.startswith('RC ') and cur is not None:
            res[cur] = ('\n'.join(buf), line[3:].strip())
            cur = None
        elif cur is not None:
            buf.append(line)
    return res


def run_matrix(cells, title, out, chunk=120, extra_env=None, parser=None):
    """Run every cell in both shells; print a both-sides table. Returns rows."""
    bmap, pmap = {}, {}
    for i in range(0, len(cells), chunk):
        part = cells[i:i + chunk]
        script = build_script(part)
        b = run_bash(script, extra_env)
        p = run_psh(script, extra_env, parser)
        bmap.update(parse(b.stdout))
        pmap.update(parse(p.stdout))
        if len(parse(p.stdout)) != len(part):
            print(f"!! psh lost cells in chunk {i}: got "
                  f"{len(parse(p.stdout))}/{len(part)}; stderr="
                  f"{p.stderr[:400]!r}", file=out)
    rows = []
    print(f"\n=== {title} ===", file=out)
    for cid, body in cells:
        bo = bmap.get(cid, ('<MISSING>', '?'))
        po = pmap.get(cid, ('<MISSING>', '?'))
        same = bo == po
        rows.append((cid, body, bo, po, same))
        print(f"[{'SAME' if same else 'DIFF'}] {cid} :: {body}", file=out)
        print(f"    bash: {bo[0]!r} rc={bo[1]}", file=out)
        print(f"    psh : {po[0]!r} rc={po[1]}", file=out)
    nd = sum(1 for r in rows if not r[4])
    print(f"--- {title}: {len(rows)} cells | DIFF {nd} | SAME {len(rows) - nd} ---",
          file=out)
    return rows
