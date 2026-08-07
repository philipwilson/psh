# Instrument defect: i5_rider_matrix.py used the shell under test as the byte producer

**Found by:** dev-4b-2, 2026-08-07, during Phase A of slot 4B.2.
**Superseded by:** `i6_rider_matrix_v2.py`. The defective run's output is KEPT at
`i5_rider_matrix_base.txt` so the record shows what was measured and why it was
discarded (D-3.4 lesson 1: instruments are the weakest part of the work).

## The defect

`i5` drove each cell with a pipeline whose LEFT side was written in the shell
under test:

```
{ printf 'a\303'; sleep 2; } | { read -t 1 -N 2 x; printf 'rc=%s v=%q\n' "$?" "$x"; }
```

Two separate confounds:

1. **The producer is the shell under test.** bash's `printf '\303'` emits the
   single byte `C3`; psh's emits the CHARACTER U+00C3, i.e. the two bytes
   `C3 83`. So the bash cell and the psh cell consumed DIFFERENT INPUT. The
   `read` behaviour they appeared to compare was partly a `printf` difference.
2. **The value was compared through `printf %q`.** `%q` renders a non-UTF-8
   byte differently in the two shells (`$'a\303'` vs `a\Ã`), so a rendering
   difference reads as a value difference.

Symptom in the discarded run: `n_mb_split` reported `bash rc=142 v=$'a\303'`
vs `psh rc=0 v=a\Ã` and would have been written up as a `read -n` divergence.
It is not — with an identical byte stream (i6) that cell is
`bash rc=142 bytes=61c3` vs `psh rc=142 bytes=61`, a REAL but COMPLETELY
DIFFERENT divergence (rc agrees; the stranded partial byte is what differs).

A third confound the same shape would have hidden: with a producer that EXITS,
psh's `-N` terminates at EOF, so the A5 hang is invisible. The true hang needs
a producer that HOLDS the descriptor open past the deadline.

## The fix (i6)

* bytes are produced by a **separate python process** writing to a **FIFO** on a
  scripted timeline — both shells consume the identical byte stream;
* the assigned value is compared as **raw bytes** via the external
  `od -An -tx1`, not `printf %q`;
* the producer can **hold the FIFO open** (`hold=` seconds) so a cell can
  distinguish "blocks until EOF" from "honors the deadline";
* every shell runs in its own session under a bounded process-GROUP kill, and
  the producer group is swept after every cell, so no orphan outlives a cell.

## Lesson (offered for the campaign bank)

**An A/B probe must not let either side under test generate the stimulus.**
When both arms are shells and the stimulus is written in shell, the probe is
comparing two different experiments. Generate the stimulus from a third
process, and compare observables in a representation neither arm controls
(raw bytes through an external tool, not the shell's own quoting).
