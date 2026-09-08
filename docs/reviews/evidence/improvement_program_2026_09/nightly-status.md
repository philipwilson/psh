# Linux nightly status at program launch (Wave 0 baseline fact)

- **Recorded:** 2026-09-06, Wave 0.1 (package D), read-only from
  `gh run list --workflow nightly.yml` and `gh run view <id> --log-failed`
  (active gh account `philipwilson`).
- **Finding:** `nightly.yml` ("Nightly Full Suite", two jobs: *Full Parallel Suite +
  Bash Golden Comparison* and *Full Conformance Suite*) has FAILED on **every scheduled
  run since 2026-08-10** — 28 consecutive red runs, all at head `6459f1a6` (the
  v0.779.0 merge, which is also the program's launch base). The program text (§1, §6)
  names only the 2026-09-01 → 2026-09-06 window (runs 33465565622 … 34008477403); the
  streak is longer, with the SAME failure census on its first day and its last:
  - last green: **2026-08-09**, run 31292685243 @ `4c333a78` (the Ceremony C branch tip
    before the #543 merge); 2026-08-08 run 31237400812 @ `e3924ed3` also green;
  - first red: **2026-08-10**, run 31353065020 @ `6459f1a6` — `25514 passed, 7 failed,
    1683 skipped, 10 xfailed`, the seven nodes listed below;
  - latest: **2026-09-06**, run 34008477403 @ `6459f1a6` — identical census
    (`Combined across 3 phase(s): 25514 passed, 7 failed, 1683 skipped, 10 xfailed`;
    conformance job `7 failed, 3372 passed, 2 skipped, 8 xfailed in 1028.86s`).
- **The seven red nodes (both jobs, identical set every run):**
  `tests/conformance/bash/test_printf_float_format_conformance.py::`
  `TestPrintfFloatAltFlag::test_alt_hex_float`,
  `TestPrintfFloatPadding::test_zero_pad_after_prefix`,
  `TestPrintfHexFloatPrecision::test_precision_round_up_and_carry`,
  `::test_precision_rounds`, `::test_precision_signs_and_extremes`,
  `::test_precision_zero_pads`, `::test_uppercase` — every one a `%a`/`%A` cell.
- **Why:** the module shipped in v0.779.0 (rider 5R, `printf %a/%A precision + '#'
  flag`), gated on macOS against Homebrew bash. On the runner the oracle is Ubuntu 24.04's
  system **bash 5.2.21(1)-release (x86_64-pc-linux-gnu)** (`Show bash version` step;
  `nightly.yml` sets no `BASH_PATH`), and x86-64 glibc formats bash's `long double`
  `%a` in the x87 explicit-integer-bit form. Exact strings from run 34008477403
  (identical on 2026-08-10):

  | cell | bash 5.2.21 on x86-64 glibc | psh (same runner) |
  |---|---|---|
  | `printf '%.2a\n' 3.14` | `0xc.8fp-2` | `0x1.92p+1` |
  | `printf '%.2a\n' 0.1` | `0xc.cdp-7` | `0x1.9ap-4` |
  | `printf '%.20a\n' 3.14` | `0xc.8f5c28f5c28f5c300000p-2` | `0x1.91eb851eb851f0000000p+1` |
  | `printf '%.2a\n' -3.14` | `-0xc.8fp-2` | `-0x1.92p+1` |
  | `printf '%.2A\n' 3.14` | `0XC.8FP-2` | `0X1.92P+1` |
  | `printf '%#a\n' 2` | `0x8.p-2` | `0x1.p+1` |
  | `printf '%020.2a\n' 3.14` | `0x00000000000c.8fp-2` | `0x000000000001.92p+1` |

  Same value, different normalisation of the leading hex digit (x87 80-bit `long
  double` keeps the integer bit explicit, so glibc prints `0xc.…p-2` where a 64-bit
  `double` prints `0x1.…p+1`). Platform, not psh (Park **P-6**); the module docstring's
  "Every cell here is libc-STABLE: glibc (Linux nightly) and macOS libc …" claim is
  false for these seven and is corrected by 0.1.
- **Nobody looked** for 28 days: the local gate is THE release gate and the backstop
  went dark from the day v0.779.0 merged — the same lesson the 2026-07 campaign recorded
  at its launch (verify with run RESULTS, not config). D11 makes the nightly a
  wave-close criterion so this cannot recur silently.

## Policy (program §6 0.1 item 4, D1, D5, D11)

1. **Pin the oracle.** Both nightly jobs build bash **5.3.15** (GNU tarball 5.3 +
   patches 001–015) into a cached prefix (key `bash-5.3.15-${{ runner.os }}-${{
   runner.arch }}`), export `BASH_PATH`, and FAIL a dedicated step unless
   `$BASH_PATH -c 'echo $BASH_VERSION'` starts with `5.3.15`; the "Show bash version"
   step also prints `printf '%a\n' 1` and `$MACHTYPE` so the platform form is visible in
   every log. This is package B's workflow change; run once via `workflow_dispatch` at
   the 0.3 tree and recorded here.
2. **Classify, never leave red.** The `%a`/`%A` cells are classified by TWO predicates
   probed on the ORACLE, never an OS or version literal: `oracle_feature('x87_long_double')`
   (`printf '%a\n' 1` prints the explicit-integer-bit form; 7 methods, 21 cells) and
   `oracle_feature('long_double_wider_than_double')` (`printf '%a\n' 0.1` carries more than
   13 fraction digits or a leading digit other than 1; the 2 full-precision cells `%.20a`
   and `%A` of 3.14, which also differ on aarch64 glibc binary128 — package B's verifier
   proved this in real containers). Expected skips: x86-64 glibc 9 methods, aarch64 glibc
   2, macOS 0; three collateral cells that match everywhere stay unmarked. Predicate probed
   literal (D5). Expected steady state: SKIPPED with the x87 reason on Linux, RUN on
   macOS; D5 version-skip count 0 on both hosts.
3. **Intended coverage change:** the pinned nightly **no longer exercises Ubuntu's
   system bash 5.2.21**. That is deliberate — bash 5.2 is a historical coordinate, not an
   oracle (program header), and the nightly's job is to run the SAME 5.3.15 on Linux so
   platform deltas are the only difference between the two hosts. Anyone wanting a 5.2
   observation must build one explicitly; nothing in the tree claims 5.2 parity.
4. **Reconciliation rule (D11):** a wave does not close until the first scheduled
   nightly after its last merge is green on the pinned 5.3.15, with the phase censuses
   reconciled against the local gate by an EXPLAINED platform delta written below.

## Run log (append per observation)

| date | run | head | jobs | census | delta explanation |
|---|---|---|---|---|---|
| 2026-08-10 | 31353065020 | `6459f1a6` | both RED | 25514 passed / 7 failed / 1683 skipped / 10 xfailed | first red at the launch base: 7 `%a` x87 rows vs unpinned bash 5.2.21 |
| 2026-09-06 | 34008477403 | `6459f1a6` | both RED | 25514 passed / 7 failed / 1683 skipped / 10 xfailed | identical census, 28th consecutive red |
| 2026-09-07 | 34094247398 | `4a865c68` (release tree + first attestation) | conformance GREEN, full suite RED (1 node) | full suite `25801 passed / 1 failed / 1728 skipped / 10 xfailed` (phase 1 `23142 passed / 1 failed / 1691 skipped / 8 xfailed`, phase 1b `1132 / 1 / 2`, phase 2 golden compare `1527 / 36`); conformance `3439 passed / 10 skipped / 8 xfailed` | first run on the built **5.3.15** (`BASH_VERSION=5.3.15(1)-release MACHTYPE=x86_64-pc-linux-gnu printf-%a-of-1=0x8p-3`; cache miss, built in the job). The ONE red node is the golden row `w0_2_trap_P_unset_prints_nothing_ignored_prints_empty_line`, whose expected stdout was rendered through `od -c` (BSD column layout on macOS, GNU on Linux) — a portability defect in the ROW, not in psh (phase 2 compared psh to bash on the same host and passed); fixed at `6ce05e5e` (awk brackets). Platform delta vs the local attest (`23187 / 1647 / 8`): +44 skips = 9 `%a` methods (7 x87 + 2 wide long double, exactly package B's prediction) + 24 `test_print_vs_zsh` (zsh not installed) + 6 mypy-absent (`test_mypy_untyped_defs_coverage:264`, `test_expansion_host_witness_5c1` ×5) + 5 shallow-checkout git-range tooling tests; `test_advanced_redirection.py:414` skips on both hosts. Conformance delta `3448 / 1` → `3439 / 10` = the same 9 `%a` methods. |
| 2026-09-07 | 34098251725 | `c7f3db06` (final attestation commit) | both GREEN | full suite `25802 passed / 1728 skipped / 10 xfailed` (phase 1 `23143 / 1691 / 8`, phase 1b `1132 / 1 / 2`, phase 2 golden compare `1527 / 36`); conformance `3439 passed / 10 skipped / 8 xfailed`; benchmark tier `16 passed / 1 xfailed`; RD-vs-combinator differential `2 passed` | re-dispatch after the row fix and re-attestation (attest attempt 3 at `6ce05e5e`: `24319 / 1648 / 10`). Oracle restored from the cache key `bash-5.3.15-Linux-X64-…` and verified `5.3.15(1)-release` before any phase. Phase 1 is exactly the local attest minus the 44 explained skips (`23187 − 44 = 23143`); conformance is the local `3448 / 1` minus/plus the 9 `%a` methods. **Wave 0 exit criterion (§6) met on the dispatch runs**; merged to main as `ccc0e694` and auto-tagged v0.780.0. |
| (first scheduled after Wave 0 merges) | PENDING — the next scheduled run executes at `ccc0e694`, the same tree as `c7f3db06`; expected census identical to run 34098251725 | | | | D11 reconciliation rule: append the observation here when it lands |

## Nightly watch — slot 1.13 write-side process substitution (v0.792.0)

The macOS gate CANNOT prove these rows. macOS `/dev/fd/N` is `fdesc` and behaves like
`dup(N)` (the same open file description; a widening mode such as `O_RDWR` on a write-only
end is refused with `EACCES`), while Linux's `/dev/fd` is `/proc/self/fd`, where opening a
pipe's entry creates a NEW description on the same pipe object and an `O_RDONLY` open of a
WRITE end yields the read end. Every write-side row therefore exercises a kernel path the
local gate never reaches. **The first scheduled nightly after this merge must be green on
these 38 node ids** (D11 reconciliation rule):

- `tests/integration/redirection/test_process_sub_late_consumer.py::test_process_substitution_matches_bash[<case>-{c,file,stdin}]`
  — 27, cases `late_open_write_side`, `write_side_bytes`, `write_side_late_body`,
  `append_to_write_side`, `tee_to_write_side`, `external_consumer_opens_the_path`,
  `external_consumer_redirects_low_fds`, `both_directions_one_command`, `exec_write_side`.
- same file — 3: `test_substitution_loop_leaves_the_fd_table_unchanged[census_write_side-{c,file,stdin}]`.
- `tests/integration/redirection/test_process_sub_closed_fds.py` — 5:
  `test_write_side_procsub_closed_fds_matches_bash[<4 closure prefixes>]` and
  `test_write_side_delivers_with_stdin_closed`.
- `tests/behavioral/test_golden_behavior.py::test_golden[…]` — 2:
  `c082_write_side_body_reading_late_still_receives_the_bytes`,
  `c091_write_side_substitution_loop_leaves_the_fd_table_unchanged` (watch their
  `test_golden_bash_comparison[…]` twins too if the `--compare-bash` leg runs — 40).
- `tests/conformance/bash/test_bash_compatibility.py::TestBashCommandSubstitution::test_output_process_substitution` — 1.

Second line of the same watch, a DISTINCT Linux risk the 38 do not cover: the six
`path_numbers_match_bash{,_with_high_fds_taken}-{c,file,stdin}` nodes compare descriptor
numbers to bash WITHOUT normalising, and the nightly is their first Linux exposure. They are
not reopen surface, but they are the rows most likely to surprise if Linux bash allocates
differently.
