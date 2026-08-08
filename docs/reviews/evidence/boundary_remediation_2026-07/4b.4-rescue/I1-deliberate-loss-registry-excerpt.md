### Deliberate-loss registry (SCOPED; discriminating probes in I1-probes/deliberate-loss-probes.txt)
Both are the ULTRA-RARE malformed-multibyte `-N`/`-n` count boundary; psh must
read one byte ahead to classify a malformed lead as a surrogate, and bash (C
locale) is byte-per-char and never looks ahead. The COMMON/valid cases MATCH
bash via the shared kernel offset (pinned: `test_valid_dup_alias_is_parity`,
`test_common_composition_matches_bash`).
- **(b) dup-cross-fd.** `exec 3<&0; read -N1 -u0 a; read -N1 -u3 b` on `\xc3A`:
  psh a=`\xc3` b=`\n` (the lookahead byte stranded in fd0's cursor); C bash
  a=`\xc3` b=`A`. FULL (share the cursor across the dup) would carry it psh-side.
  Pinned CURRENT: `test_malformed_dup_alias_documented_divergence`.
- **(c) temp-redirect frame.** `read -N1 a; read b < file; read -N1 c` on
  `\xc3A\n...`: the persistent fd-0 cursor's surplus leaks into the temp file
  read (b=`AF1`); C bash b=`F1`. The SAME persistence that fixes same-fd
  carryover (a) causes this; hooking the temp frame = FULL. Pinned CURRENT:
  `test_malformed_surplus_leaks_across_temp_frame`.
- **(d) builtin->external stranded byte (same family; the replaying-fd-view
  answer).** `read -N1 x; cat` on `\xc3A\n`: psh's cat sees `\n` (the
  lookahead byte A is in the cursor, invisible to the child); C bash's cat
  sees `A\n`. Probe: `I1-probes/replaying-fd-view-probe.txt`. **The §I1
  replaying-fd-view conditional is answered NO**: every VALID input composes
  builtin->external exactly via the kernel offset (never-over-read; probed
  MATCH), so the only cases a replaying view would serve are this malformed
  count-boundary family — ruled deliberate-loss under SCOPED. Not built.

### Byte-level matrix (branch tip) — I1-probes/
