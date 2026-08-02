#!/usr/bin/env python3
"""Equivalence-proof ARM runner (slot 3.2).

Runs in ONE tree and emits a deterministic result record per cell across
EVERY relation and consumer operator. The prover runs this twice — once in a
detached base worktree, once in the tip worktree — as SEPARATE PROCESSES, so
the two arms share no module object, no lru cache and no matcher memo. That
is structural forcing: arm A cannot be laundered into arm B through a cached
decider (slot 3.1 D-3b hit exactly that failure in-process).

  python3 equiv_arm.py <cells.jsonl> <out.jsonl>

Env:
  PSH_ROOT           tree this arm MUST import from (discriminator, hard abort)
  SLOT32_INJECT      M6 self-test: perturb exactly one relation's result so
                     the prover is forced to detect a difference. If the
                     prover passes with this set, the PROVER is broken.
"""
import json
import os
import sys

PSH_ROOT = os.environ['PSH_ROOT']
INJECT = os.environ.get('SLOT32_INJECT', '')

import psh  # noqa: E402
import psh.expansion.pattern_engine as pe  # noqa: E402
from psh.expansion import parameter_expansion as px  # noqa: E402
from psh.shell import Shell  # noqa: E402

_real = os.path.realpath(PSH_ROOT) + os.sep
for mod, name in ((psh, 'psh'), (pe, 'pattern_engine'), (px, 'parameter_expansion')):
    f = os.path.realpath(mod.__file__)
    if not f.startswith(_real):
        sys.exit(f"DISCRIMINATOR FAIL: {name} from {f}, expected under {PSH_ROOT}")

sh = Shell()
sh.run_command('shopt -s extglob')
ops = px.ParameterExpansionOps(sh)


def record(pattern, subject):
    """Every relation + consumer operator for one (pattern, subject) cell."""
    out = {}
    try:
        cp = pe.PatternCompiler.compile(pattern, extglob=True)
        root = cp.root
        n = len(subject)
        # --- the five engine relations, STRING profile
        out['full'] = cp.full_match(subject, pe.STRING)
        out['ends'] = sorted(cp.matching_ends(subject, 0, pe.STRING))
        out['starts'] = sorted(cp.matching_starts(subject, n, pe.STRING))
        out['span'] = [cp.span_at(subject, p, pe.STRING) for p in range(n + 1)]
        spanner = cp.spanner(subject, pe.STRING)
        out['spanner'] = [spanner(p) for p in range(n + 1)]
        out['spans'] = list(cp.matching_spans(subject, pe.STRING))
        # --- routing/derived facts (must not drift either)
        # R1(a)(iv) equivalence guard: the tip DERIVES these at construction,
        # the base computed them LAZILY on first query. Read through the same
        # function names on both arms, so any disagreement between the eager
        # and lazy derivations shows up as a per-cell diff rather than as a
        # claim in a docstring.
        out['quirk'] = pe._seq_bash_quirk(root)
        out['hasx'] = pe._seq_has_extglob(root)
        out['subfast'] = pe.sub_fast_eligible(root)
        # `_seq_nullable` exists at BASE (a recursive walk) and was RETIRED at
        # tip once the bit moved to construction time. Read whichever the arm
        # provides, so this guard keeps comparing the same SEMANTIC quantity
        # across the deletion instead of turning a retired NAME into a fake
        # disagreement.
        def _nullable(seq):
            fn = getattr(pe, '_seq_nullable', None)
            return fn(seq) if fn is not None else seq.nullable

        out['nullable'] = _nullable(root)
        out['alt_bits'] = [
            [pe._seq_bash_quirk(a), pe._seq_has_extglob(a),
             pe.sub_fast_eligible(a), _nullable(a)]
            for e in root.elements if type(e) is pe.Extglob for a in e.alts]
        out['unparse'] = pe.unparse(root)
        out['structure'] = repr(pe.structure(root))
        # --- pathname profile (for_pathname is a separate transition set)
        out['full_fp'] = cp.full_match(subject, pe.PATHNAME)
        out['ends_fp'] = sorted(cp.matching_ends(subject, 0, pe.PATHNAME))
        # --- case-insensitive profile
        out['full_ic'] = cp.full_match(subject, pe.STRING_IC)
        # --- free-function API (live via extglob.py consumers)
        out['reach'] = sorted(pe.reachable_ends(root, subject))
        out['fullmatch'] = pe.fullmatch(root, subject)
        out['match_at'] = pe.match_at(root, subject, 0)
        # --- the four substitution operators
        out['sub_first'] = ops.substitute_first(subject, pattern, 'Z')
        out['sub_all'] = ops.substitute_all(subject, pattern, 'Z')
        out['sub_beg'] = ops.substitute_prefix(subject, pattern, 'Z')
        out['sub_end'] = ops.substitute_suffix(subject, pattern, 'Z')
        # --- the four removal operators
        out['rm_sp'] = ops.remove_shortest_prefix(subject, pattern)
        out['rm_lp'] = ops.remove_longest_prefix(subject, pattern)
        out['rm_ss'] = ops.remove_shortest_suffix(subject, pattern)
        out['rm_ls'] = ops.remove_longest_suffix(subject, pattern)
    except RecursionError:
        out['exc'] = 'RecursionError'
    except Exception as e:                      # noqa: BLE001 - recorded, compared
        out['exc'] = f"{type(e).__name__}: {e}"
    return out


def main():
    cells_path, out_path = sys.argv[1], sys.argv[2]
    n = 0
    with open(cells_path) as fin, open(out_path, 'w') as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            pattern, subject = json.loads(line)
            rec = record(pattern, subject)
            if INJECT and n == 0:
                # M6: perturb exactly one cell so the prover MUST notice.
                rec['full'] = not rec.get('full', False)
            fout.write(json.dumps([pattern, subject, rec], sort_keys=True) + '\n')
            n += 1
    sys.stderr.write(f"arm ok: {n} cells from {psh.__file__}\n")


main()
