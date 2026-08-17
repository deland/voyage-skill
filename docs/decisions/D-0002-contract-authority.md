# D-0002: Contract authority and minimal-kernel direction

- Status: active
- Decider: User
- Decided: 2026-08-17
- Scope: VoyageSkill v0.2 minimal-kernel development
- Supersedes: none

This decision fixes the authority and trust boundaries used while evolving the
v0.1 baseline:

1. The Python core validator and event replay are the normative runtime
   contract. JSON Schema files are versioned exchange contracts and must remain
   consistent with runtime-produced instances through executable tests.
2. Activating or replacing a source of truth requires a scoped, recorded User
   decision. Bootstrap templates are drafts; their presence does not make their
   claims true. The v0.1 generated active templates remain a legacy behavior
   until MK-101 implements bootstrap and activation.
3. The minimum durable work progression targeted by MK-103 is `draft`,
   `authorized`, `active`, `delivered`, `quality-passed`, `accepted`, and
   `closed`, with evidenced `rejected`, `blocked`, and `awaiting-user` side
   states. Unimplemented speculative states are not part of that target.
4. The minimum durable rule progression targeted by MK-103 is `proposed`,
   `approved`, `applied`, and `active`, followed by `retired` or `superseded`.
   Verification is the evidence-bearing transition from applied to active, not
   a second durable state.
5. Ledger hashes make recorded history tamper-evident. Project actor IDs and
   loop labels are assertions by the local caller; v0.x does not
   cryptographically authenticate principals and is not tamper-proof against a
   malicious process with write access.
6. High-risk and irreversible actions continue to require final, scoped User
   authorization. A runtime, schema, test, or agent assertion cannot replace it.

This decision authorizes the listed development contracts. It does not claim
that the MK-101 or MK-103 target behavior is implemented before those work
packages pass their own gates.
