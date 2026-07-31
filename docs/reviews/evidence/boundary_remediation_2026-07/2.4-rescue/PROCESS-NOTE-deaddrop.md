---
name: agent-message-deaddrop
description: "Multi-agent rulings can silently miss a working agent's turns; use a polled file dead-drop instead of trusting the message channel"
metadata: 
  node_type: memory
  type: project
  originSessionId: 05736dde-f3cd-4b98-98df-9708e107bca4
  modified: 2026-07-31T03:18:24.545Z
---

In the psh remediation campaign (slot 2.4, 2026-07-31) the integrator's GO for a
stage-gated change was sent FIVE times over the agent message channel and none
of the transmissions reached the dev's working turns — the dev sent four status
messages in a row, each composed before a ruling it never saw, and the slot
stalled. The fix that worked: a durable dead-drop file,
`<worktree>/tmp/remediation-ledgers/INTEGRATOR-INBOX.md`, which the integrator
mirrors every ruling into and the dev reads at the START of every turn.

**Why:** agent-to-agent messages are delivered on the recipient's turn
boundaries, so a long working turn (a probe battery, a gate run) can swallow a
grant entirely. Silence from a supervising agent is therefore NOT evidence that
no ruling was issued, and a stage-gated agent that only waits will stall
indefinitely.

**How to apply:** when work is gated on another agent's approval, (1) poll an
agreed file at the start of each turn rather than relying on message delivery,
(2) keep making progress on everything the gate does not cover, and (3) prepare
the gated change so it can land in one step — measuring it in a throwaway git
worktree is legitimate evidence-gathering, not implementation, and it turns the
approval into a decision about consequences rather than about an argument.

**Sibling lesson (same slot, other direction):** an IDLE agent session also
misses the completion wake of its OWN background tasks (dev-2-4 stalled twice
waiting on gates it had launched). Cure: never end a turn with a heavy run in
flight — run it as one foreground call with a generous timeout when it fits
(~7-min psh gate fits in the 600s Bash ceiling), else await it in-turn with a
bounded poll loop; the supervisor arms an independent watch as backstop.

**A third face of the same asymmetry (added 2026-07-31, slot 2.4 round 7):** a
foreground command that hits the harness time limit is MOVED TO THE BACKGROUND,
not stopped. Starting the next run then means running both. Three concurrent
pytest runs over one tree produced 20 spurious failures in the signal/trap
conformance family, which passed 68/68 when re-run in isolation. Before
starting a heavy run, check that no earlier one is still executing (`pgrep -f
pytest`), and wait on it — "my call returned" is not "the run finished".

Related: [[psh-remediation-campaign-plan]], [[psh-adversarial-verify-systemic]].
