# VoyageSkill authority and risk contract

- Version: 0.1.0
- Status: active
- Authority: D-0001

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

## Rule lifecycle

Rules move through `proposed`, `approved`, `applied`, `verified`, and `active`.
They may then become `deprecated`, `retired`, or `superseded`. Failed
verification requires revision or rollback. Every rule records its source,
scope, cost, expected result, verifier, expiry/retirement condition, and rollback.

## Audit blocks

An audit block must name evidence, minimum scope, forbidden transitions,
objective unblock conditions, review trigger, appeal authority, and independence
from the disputed action. Evidence-free concern creates an investigation item,
not an authoritative defect or project-wide block.
