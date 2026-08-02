"""Smoke: signature cell + harness validation (timing check before the big matrix)."""
import sys
import time

from batch import run_matrix
from harness import header

CELLS = [
    ('sig-q',   'unset x; set -- a b; count "${x:-"$@"}"'),
    ('sig-u',   'unset x; set -- a b; count ${x:-"$@"}'),
    ('sig-plus', 'x=set; set -- a b; count "${x:+"$@"}"'),
    ('sig-sp',  'unset x; set -- "a 1" b; count "${x:-"$@"}"'),
    ('base-at', 'set -- a b; count "$@"'),
    ('empty-dq', 'unset x; count "${x:-""}"'),
    ('empty-u',  'unset x; count ${x:-""}'),
    ('empty-op-q', 'unset x; count "${x:-}"'),
    ('empty-op-u', 'unset x; count ${x:-}'),
]

if __name__ == '__main__':
    t0 = time.time()
    header(sys.stdout, tree_note='slot 3.3 worktree, base d0f7d929')
    run_matrix(CELLS, 'SMOKE', sys.stdout)
    print(f"\nelapsed: {time.time() - t0:.1f}s for {len(CELLS)} cells")
