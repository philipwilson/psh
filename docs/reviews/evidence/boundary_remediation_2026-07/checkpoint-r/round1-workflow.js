export const meta = {
  name: 'checkpoint-r-round1',
  description: 'Checkpoint R round 1: six independent scoped verifiers over psh v0.773.0 (ae871a16)',
  phases: [
    { title: 'Appraise', detail: 'Q1 discriminators / Q2 resurrection / Q3 representations / Q4 new debt / Q5 wave-5 census / QR queue' },
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
      evidence: { type: 'string', description: 'one line, with instrument path where a probe ran' } } } },
    findings: { type: 'array', items: { type: 'object', required: ['id', 'severity', 'claim', 'evidence', 'proof_shape'], properties: {
      id: { type: 'string', description: '<scope>-F<n>' },
      severity: { type: 'string', enum: ['BLOCKER', 'REQUIRED-NIT', 'NOTE'] },
      claim: { type: 'string' },
      evidence: { type: 'string' },
      proof_shape: { type: 'string', enum: ['revert-proven', 'mutation-proven', 'by-elimination', 'characterization'] },
      instrument: { type: 'string' } } } },
    census: { type: 'object', description: 'scope-specific numbers, each with the instrument that generated it' },
    recommendations: { type: 'array', items: { type: 'string' } },
    not_checked: { type: 'array', items: { type: 'string' }, description: 'everything in your charter scope you did NOT check, with why' },
    instruments_dir: { type: 'string' },
    worktree_removed: { type: 'boolean' },
  },
}

const CHARTER = '/Users/pwilson/src/psh/tmp/remediation-ledgers/briefs/checkpoint-r.md'
const MD5 = 'a08a9c1df086b1c128b8bce6772f1d57'

const SCOPES = [
  { slug: 'q1', key: 'Q1-discriminators', section: 'Q1-discriminators — do the #22 HIGH + user-visible MEDIUM discriminators pass?' },
  { slug: 'q2', key: 'Q2-resurrection', section: 'Q2-resurrection — did anything recreate a deleted boundary?' },
  { slug: 'q3', key: 'Q3-representations', section: 'Q3-representations — transitively immutable and authority-timed?' },
  { slug: 'q4', key: 'Q4-new-debt', section: 'Q4-new-debt — did the campaign itself introduce debt?' },
  { slug: 'q5', key: 'Q5-wave5-census', section: 'Q5-wave5-census — is Wave 5 (5B+5C) still the right backlog?' },
  { slug: 'qr', key: 'QR-queue', section: 'QR-queue — Checkpoint-R-queued rows + no-defer audit' },
]

function prompt(s) {
  return [
    `You are the Checkpoint R "${s.key}" verifier for the psh Boundary Remediation Campaign (an independent whole-tree appraisal at v0.773.0).`,
    ``,
    `FIRST: read ${CHARTER} IN FULL and verify its md5 is ${MD5} (\`md5 -q\`). If the md5 differs, STOP and report the mismatch as your only output.`,
    ``,
    `Your charter is the section titled "${s.section}". EVERY rule in the charter's "Environment discipline" and "Evidence discipline" sections binds you, as does "Known-deviation awareness" (declared deviations behaving as declared are NOT findings). You are VERIFICATION-ONLY: never edit committed files, never commit, never run heavy suites (no run_tests.py, no tree-wide pytest, no -n auto over tests/; --collect-only -q count FIRST for any pytest arg that is not a file/node ID).`,
    ``,
    `Your scope slug is "${s.slug}":`,
    `- Instruments dir (main repo, already exists): /Users/pwilson/src/psh/tmp/ckr-probes/${s.slug}/ — every probe is a FILE here before it runs; transcripts saved alongside.`,
    `- Scratch root (create it): /private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/${s.slug}/`,
    `- Detached worktree: \`git -C /Users/pwilson/src/psh worktree add --detach <scratch>/wt ae871a16\` (if it fails on a lock held by a sibling, sleep 2-5s and retry, up to 3 times). ALL measurement runs with cwd inside the worktree; assert the import discriminator (resolved psh.__file__ under the worktree AND __version__ == "0.773.0") BEFORE any measurement and record the assertion output. At the end remove the worktree and report whether removal succeeded.`,
    ``,
    `Execute your charter section COMPLETELY. Every item in it gets a verdict; anything skipped goes in not_checked with the reason. Findings carry named proof shapes. Your final structured output is data for the campaign integrator, not a human-facing message — return raw, complete results.`,
  ].join('\n')
}

phase('Appraise')
log('Checkpoint R round 1: dispatching 6 scoped verifiers at ae871a16 (v0.773.0)')
const results = await parallel(SCOPES.map(s => () => agent(prompt(s), { label: s.key, phase: 'Appraise', schema: SCHEMA })))
const ok = results.filter(Boolean)
log(`Round 1 complete: ${ok.length}/6 scopes returned`)
return { returned: ok.length, results }