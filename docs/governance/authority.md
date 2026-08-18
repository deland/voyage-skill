# VoyageSkill authority and risk contract

- Version: 0.1.0
- Status: active
- Authority: D-0001, D-0002

## Permission loops

The four loops are scoped permissions, not permanent job titles.

| Loop | Authority | Prohibited |
| --- | --- | --- |
| Execution | Implement authorized work, claim resources, self-test, and create immutable deliveries | Final-approve its own delivery; change scope, active truth, mandatory gates, or User authorization |
| Quality | Independently review, test, read back, pass, or reject an exact delivery anchor | Modify the delivery under review; reuse a verdict for a new anchor; waive mandatory failures |
| Governance | Define scope, risk, resources, gates, bindings, dependency and integration order | Replace quality evidence; silently edit delivery; lower a gate after seeing results; authorize high risk |
| Audit | Inspect all loops, propose systemic changes, and block the smallest evidenced scope | Approve and verify its own rule change; resolve an appeal against itself; create unbounded blocks |

User is outside the loops and is the final authority for product direction,
high-risk conflict, irreversible action, exception, and audit appeal.

## Identity and trust boundary

Ledger hashes and immutable references make local history tamper-evident, not
tamper-proof. Actor IDs, loop labels, and recorded signatures are assertions by
the local caller and are not cryptographically authenticated in v0.x. An actor
with direct write access is inside the local trust boundary; VoyageSkill detects
unsupported transitions and historical mutation but does not provide principal
authentication against that actor.

Actor and loop values are a caller assertion. The trusted boundary is the OS
account and worktree permissions. Protection against a hostile same-account
writer is out of scope; use an external cryptographic identity and serialized
write boundary before allowing mutually untrusted callers.

## Required separation

- Delivery executor and final quality signer must differ.
- Rule proposer and approver must differ.
- Rule applier and effectiveness verifier must differ.
- Audit blocker and final appeal resolver must differ.
- No loop may replace a required User authorization.

## Risk modes

### Light

Use only when impact is small, fully reversible, and free of high-risk shared
resources. Apply a pre-approved governance template. Keep immutable delivery,
evidence, execution/quality separation, and authorization boundaries.

### Standard

Use by default. Require explicit work scope, registered resources, independent
quality, mandatory gates, ledger events, and recovery evidence. Run audit on
events or periodic triggers.

### Strict

Use for production, persistent data, security, credentials, permissions,
material cost, public external writes, gate relaxation, or irreversible action.
Keep all loop permissions separate, require full gates and real readback, and
record User authorization before execution.

Unclear risk, missing evidence, disagreement, or classification conflict always
selects the stricter mode.

<!-- executable-risk-policy:start -->
Executable policy version 1 orders modes as `light`, `standard`, then `strict`.
Every mode keeps immutable anchors, independent quality, append-only ledger
integrity, truth-defined mandatory gates, loop separation, and User authority.

`light` requires valid typed classification evidence; without it the effective
mode becomes `standard`. `standard` probes every declared resource and applies
project-defined mode gates. `strict` requires action-scoped User decisions,
fresh runtime readback before and after execution, matching risk-domain gates,
typed resource probes, and an independent audit checkpoint on the current
delivery anchor.

Unknown or disputed classification and the domains `credentials`,
`gate-relaxation`, `irreversible`, `material-cost`, `permissions`,
`persistent-data`, `production`, `public-external-write`, and `security` select
`strict`. A required resource can only maintain or increase the effective mode.
Legacy work without the version-1 assessment marker keeps historical replay
behavior; it does not gain fabricated classification evidence.
<!-- executable-risk-policy:end -->

## Rule lifecycle

<!-- rule-states:start -->
Durable rule states are exactly `proposed`, `approved`, `applied`, `active`,
`retired`, and `superseded`. `rule.verified` is the evidence event that moves an
applied rule directly to active; it is not a separate durable state.

`rule.verification-failed` keeps the rule applied but non-active and records the
independent failure. Governance then uses `rule.rolled-back` to return it to
approved before revision and reapplication.
<!-- rule-states:end -->

Every rule records its source, scope, cost, expected result, verifier,
expiry/retirement condition, and rollback evidence.

## Audit blocks

An audit block must name evidence, minimum scope, forbidden transitions,
objective unblock conditions, review trigger, appeal authority, and independence
from the disputed action. Evidence-free concern creates an investigation item,
not an authoritative defect or project-wide block.
