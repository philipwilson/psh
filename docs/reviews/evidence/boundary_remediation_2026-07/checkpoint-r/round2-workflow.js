export const meta = {
  name: 'checkpoint-r-round2',
  description: 'Checkpoint R attack round: refute the round-1 clean bill (3 adversarial scopes)',
  phases: [
    { title: 'Attack', detail: 'cross-composition / verify-the-verifiers / coverage-gap closure' },
  ],
}

const SCHEMA = {
  type: 'object',
  required: ['scope', 'summary', 'verdicts', 'findings', 'not_checked', 'instruments_dir', 'worktree_removed'],
  properties: {
    scope: { type: 'string' },
    summary: { type: 'string', description: 'At most one page of prose: what you ran, headline result, anything load-bearing' },
    verdicts: { type: 'array', items: { type: 'object', required: ['item', 'verdict', 'evidence'], properties: {
      item: { type: 'string' },
      verdict: { type: 'string', enum: ['CONFIRMED', 'FAILED', 'PARTIAL', 'NOT-CHECKED'] },
      evidence: { type: 'string' } } } },
    findings: { type: 'array', items: { type: 'object', required: ['id', 'severity', 'claim', 'evidence', 'proof_shape'], properties: {
      id: { type: 'string' },
      severity: { type: 'string', enum: ['BLOCKER', 'REQUIRED-NIT', 'NOTE'] },
      claim: { type: 'string' },
      evidence: { type: 'string' },
      proof_shape: { type: 'string', enum: ['revert-proven', 'mutation-proven', 'by-elimination', 'characterization'] },
      instrument: { type: 'string' } } } },
    census: { type: 'object' },
    recommendations: { type: 'array', items: { type: 'string' } },
    not_checked: { type: 'array', items: { type: 'string' } },
    instruments_dir: { type: 'string' },
    worktree_removed: { type: 'boolean' },
  },
}

const CHARTER = '/Users/pwilson/src/psh/tmp/remediation-ledgers/briefs/checkpoint-r.md'
const CHARTER_MD5 = 'a08a9c1df086b1c128b8bce6772f1d57'
const DIGEST = '/Users/pwilson/src/psh/tmp/ckr-probes/ROUND1-DIGEST.md'
const DIGEST_MD5 = 'b0bb7dd7bbe53192bb265b9335f0cde6'

const COMMON = (slug) => [
  `You are a Checkpoint R ROUND-2 ATTACK agent for the psh Boundary Remediation Campaign. Round 1 (six scoped verifiers) returned a CLEAN BILL at ae871a16 / v0.773.0: zero BLOCKERs, zero REQUIRED-NITs, 23 NOTEs. Your job is to REFUTE it. Default skeptical; a clean bill that survives your attack is only then certified. Zero new findings IS a legitimate result — state plainly what you ran; never manufacture a finding (the campaign's standing score is zero false findings, and a false BLOCKER costs a full round).`,
  ``,
  `FIRST read BOTH files and verify md5s (\`md5 -q\`); STOP on mismatch:`,
  `1. ${CHARTER} (md5 ${CHARTER_MD5}) — its "Environment discipline", "Evidence discipline", and "Known-deviation awareness" sections BIND you (declared deviations behaving as declared are NOT findings; FLIP-PINS.md is authoritative).`,
  `2. ${DIGEST} (md5 ${DIGEST_MD5}) — the complete round-1 results you are attacking.`,
  ``,
  `Environment: instruments dir /Users/pwilson/src/psh/tmp/ckr-probes/${slug}/ (create it); scratch root /private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/${slug}/ (create it); own detached worktree via \`git -C /Users/pwilson/src/psh worktree add --detach <scratch>/wt ae871a16\` (retry up to 3x on lock, sleeping 2-5s); ALL measurement with cwd inside the worktree; import discriminator asserted BEFORE measurement (resolved psh.__file__ under the worktree AND __version__ == "0.773.0" — set PYTHONPATH to the worktree; cwd outranks PYTHONPATH under python -m); bash oracle /opt/homebrew/bin/bash (verify 5.2.26). Round-1 instruments in tmp/ckr-probes/{q1,q2,q3,q4,q5,qr}/ are READ-ONLY to you — copy anything you rerun into your own dir first, never edit theirs. VERIFICATION-ONLY: never edit committed files, never commit; synthetic offenders/mutations live ONLY in your own worktree and are reverted (show the revert). No heavy runs: no run_tests.py, no tree-wide pytest, no -n auto over tests/; --collect-only -q count FIRST for any pytest arg that is not a file/node ID. Remove your worktree at the end and report whether removal succeeded.`,
  ``,
].join('\n')

const ATTACKS = [
  {
    slug: 'atk-a',
    key: 'Attack-A cross-composition',
    body: [
      `SCOPE: COMPOSED probes across slot boundaries. Round 1 verified each slot's claims mostly inside its own boundary; the campaign's own verify rounds repeatedly found regressions at COMPOSITION cells (3.4's three semantics regressions were all composition cells; 4B.4's two regressions were interaction cells). Design fresh cells each of which exercises TWO OR MORE closed slots' machinery in one shell command, two-sided vs bash 5.2.26 (state the axis; REGRESSION vs the LEDGER claim, DIVERGENCE vs bash). Candidate compositions (extend with your own; aim for breadth over depth, ~8-15 composition families, several cells each):`,
      `- 4B.3 x 4B.4: history -a/-n/-w through dup'd fds and temp-frame redirects (e.g. history -w /dev/fd/3 spellings, exec dup rebinds around history file ops); read cursor behavior when HISTFILE reads happen through redirected stdin.`,
      `- 4B.2 x 2.3/procsub: split-multibyte payloads read through process substitution and command substitution; read -N across a procsub fd; decoder state across a subshell fork (I1 row (d) builtin-to-external stranding is DECLARED — as-declared is not a finding).`,
      `- 3.4 x 3.3: field-IR operands as prefix-assignment values ("${'${x:-"$@"}'}" in prefix position); refuse-before-evaluate with cmd-sub operands under readonly; prefix staging x RANDOM/dynamic specials x operand expansion.`,
      `- 3.1/3.2 x 3.3/3.4: extglob/negation patterns consuming expanded fields (\${v%%pat} with pattern from $@ or from a prefix-assigned var); case with multi-field operand patterns (first-field exclusion is DECLARED).`,
      `- 2.4 x 4A.2/4A.1: fatal substitution syntax (\`$(if\` family) composed with EXIT traps, exec redirections, and lease-holding states; child-status severing at fork boundaries composed with errexit.`,
      `- 2.5/2.6 x heredocs: analysis (--validate / psh -n) over scripts where directives (set -o posix / shopt extglob) sit inside or after heredocs; heredoc bodies containing the six-form scanner-balancing class.`,
      `- 2.1/2.2: security scanner + parser parity over composed redirect-target/subscript/procsub spellings on BOTH parsers (--parser rd|combinator).`,
      `- 4A.1 x 4B.4: failed exec releasing STD_FDS while InputCursor descriptions are live on dup'd fds.`,
      `Every cell: instrument file first, transcript beside it, proof shape named. Grade any mismatch honestly: is it a campaign REGRESSION (contradicts a LEDGER closure claim - BLOCKER), an unregistered pre-existing divergence (NOTE w/ base evidence at 0215279c if cheap to get), or a declared deviation (not a finding).`,
    ].join('\n'),
  },
  {
    slug: 'atk-b',
    key: 'Attack-B verify-the-verifiers',
    body: [
      `SCOPE: the round-1 EVIDENCE itself. Instrument discipline binds both directions — a round-1 instrument may have failed toward "all clear". Audit:`,
      `1. Reproduce >=2 headline cells per round-1 scope (12+ total) by rerunning their committed instruments (copied into your dir) in YOUR fresh worktree; diff outputs against their recorded transcripts.`,
      `2. Verify each scope's discriminator assertion actually exists in its transcripts (the p00/q?_00 files) and asserts the right two facts (worktree path + 0.773.0).`,
      `3. Census reproducibility: rerun the fn-length census (q1/p18_fn_census.py) — confirm 60 at tip and (if the instrument supports a base arg) 54 at 0215279c; spot-verify the Method-A incomplete-signature count (648) methodology by rerunning q5's instrument; spot-verify 3 of the 12 claimed new owner-params in q4's transcript against the actual code at ae871a16; confirm deferred-import 179 vs cap 200 from q4's instrument.`,
      `4. NAME-VS-BODY audit on >=5 guard tests round 1 cited as coverage (spread across scopes): read each body; does it assert the named property?`,
      `5. QR's %P zero-face claim: rerun ~20 iterations of \`time true\` in psh vs bash — is psh P=0.00 while bash is nonzero? Also verify the claimed os.times() quantum measurement instrument exists and is honest.`,
      `6. Re-plant 3 of q2's ten synthetic offenders (pick different boundaries than convenient — at least one whose guard is a generated battery) and confirm the guards still bite in your worktree; revert and show clean.`,
      `7. Hunt for classification dishonesty: any round-1 FAILED/PARTIAL verdict that should have been a BLOCKER, any NOTE that is really a REQUIRED-NIT or worse, any verdict whose evidence line does not support it, any acceptance citing an artifact that does not exist at ae871a16 (acceptances-are-claims).`,
      `Grade findings against ROUND 1 (a round-1 evidence defect = REQUIRED-NIT unless it hides a behavioral defect, then BLOCKER).`,
    ].join('\n'),
  },
  {
    slug: 'atk-c',
    key: 'Attack-C coverage-gap closure',
    body: [
      `SCOPE: the round-1 not_checked union + question-coverage audit. Close the load-bearing gaps:`,
      `1. MEDIUM-7's committed battery: locate the 4B.3 pin/conformance modules (tests/unit/builtins + tests/conformance history modules; collect-only count FIRST), run them module-scoped; report counts.`,
      `2. MEDIUM-2/4B.2: run the decoder-seam suite (tests/unit/builtins/test_input_decoder_seam_4b2.py) + the 4B.4 contract suite module-scoped; report counts.`,
      `3. PTY legs round 1 skipped — SANCTIONED for your scope ONLY, one module at a time, foreground, never in parallel with your other probes: tests/system/interactive/test_heredoc_detection_interactive_pty.py (MEDIUM-3), test_pty_shutdown_phases_4a2.py + test_pty_shutdown_route_f2.py (MEDIUM-1), test_pty_read_exact_timeout_4b2.py (4B.2 tty arm). collect-only first; if any module exceeds ~3 min or hangs, kill it, record, move on.`,
      `4. HIGH-2's generated sentinel battery: locate it, collect-only, run scoped.`,
      `5. MEDIUM-13's companion claim (state-guarded-assert census 1 -> 0 tree-wide): re-sweep with a fresh grep/AST instrument.`,
      `6. HIGH-1's 92-module migration census: reconcile tests/harness/oracle_migration_census.md against the tree (module count + spot 5 modules import shell_oracle and spawn nothing raw).`,
      `7. QUESTION-COVERAGE AUDIT: with the charter's five questions in one hand and the six round-1 reports in the other, name any FACE of any question that NO scope examined (e.g. Q2's charter listed nine boundary groups — read 2-3 wave slot ledgers' "deleted authority" claims and check whether any deleted boundary is OUTSIDE those nine; q2-F2 already flagged two guard-less-but-dead retirements).`,
      `8. q4-F4 (bg-job zombie until exit, pre-existing, UNREGISTERED): verify it is genuinely in no register (FLIP-PINS, LEDGER carries, known-deviation list, flake watch), confirm the bash-divergence with one fresh cell, and draft the register row the integrator should add (severity NOTE; this is a record gap, not a campaign regression).`,
      `Report every gap you close with counts + transcripts; anything still unclosed goes in not_checked with why.`,
    ].join('\n'),
  },
]

phase('Attack')
log('Checkpoint R round 2: dispatching 3 attack agents against the round-1 clean bill')
const results = await parallel(ATTACKS.map(a => () => agent(
  COMMON(a.slug) + '\n' + `Your scope key is "${a.key}" (slug ${a.slug}).\n\n` + a.body + '\n\nYour final structured output is data for the campaign integrator, not a human-facing message — return raw, complete results. Findings ids: ${a.slug}-F<n>.',
  { label: a.key, phase: 'Attack', schema: SCHEMA },
)))
const ok = results.filter(Boolean)
log(`Round 2 complete: ${ok.length}/3 attack scopes returned`)
return { returned: ok.length, results }