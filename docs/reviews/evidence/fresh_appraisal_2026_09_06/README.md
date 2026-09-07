# Fresh Appraisal Evidence

Review: [fresh_appraisal_2026-09-06.md](../../fresh_appraisal_2026-09-06.md).

- `probes.py`: reproducible shell comparisons and direct boundary probes.
- `observations.jsonl`: captured observations at v0.779.0 on 2026-09-06, including oracle/runtime identification.
- [validation.md](validation.md): commands, gate results, and environment qualifications.
- [canonical-tests.txt](canonical-tests.txt): the full two-phase test transcript, including every failure.

Run from the repository root with the existing development dependencies:

```sh
python docs/reviews/evidence/fresh_appraisal_2026_09_06/probes.py
python docs/reviews/evidence/fresh_appraisal_2026_09_06/probes.py differential --filter path_scope
python docs/reviews/evidence/fresh_appraisal_2026_09_06/probes.py resources
```

Sections: `differential`, `formatting`, `resources`, `interactive`, `analysis`, and `performance`; the default runs all sections. The existing shell-oracle harness resolves Bash and isolates shell working directories. Differential PSH cases enable `PSH_STRICT_ERRORS=1`.

This is an observation tool, not a passing regression suite: reproduced defects do not make the runner exit nonzero. `stdout_status_equal` excludes stderr and filesystem side effects; inspect the retained raw outcomes. There are no timeout-as-success comparisons. Security-analysis inputs are analyzed, never executed. Fault injection is restored after each probe, and descriptors deliberately exposed by the resource test are closed by its own cleanup.

The interactive cases call actual decoder/layout/completion methods without a real terminal. The performance section reports three CPU-time samples per size and their median; these are local microbenchmarks, not portable thresholds.
