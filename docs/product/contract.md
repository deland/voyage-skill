# VoyageSkill product contract

- Version: 0.1.0
- Status: active
- Authority: D-0001

## Positioning

VoyageSkill is a project-level operating control system for long-running,
multi-agent software work. It represents work as a graph of principals, truth
sources, work items, resources, gates, channels, evidence, immutable anchors,
decisions, and external calibration points.

The Skill is a stable discovery and recovery entry. Versioned project documents
and an append-only ledger are authoritative for project rules and runtime facts.

## Outcomes

VoyageSkill must make a managed project:

- recoverable without prior conversation memory;
- verifiable against immutable deliveries and real readback;
- safe under shared file, account, port, environment, and session contention;
- governed by independent execution, quality, governance, and audit permissions;
- able to escalate high-risk actions to User authority;
- able to evolve and retire rules through independently verified changes;
- compressible for explicitly low-risk work without dropping anchors, evidence, or authorization boundaries.

## Minimum journeys

1. Initialize or adopt a repository and register its active truth sources.
2. Recover active work, blocks, leases, decisions, and unknowns in a fresh session.
3. Create, authorize, execute, deliver, independently validate, and accept a work item.
4. Prevent conflicting claims on registered resources.
5. Reject a delivery and require a new immutable anchor for its repair.
6. Block the minimum affected scope when audit evidence proves a systemic failure.
7. Propose, approve, apply, verify, supersede, and retire a rule.
8. Stop a high-risk action until a scoped User authorization is recorded.

## Non-goals

v0.1 does not provide fixed DevSwarm-style roles, a graphical project manager,
a distributed lock service, secret storage, autonomous production deployment,
cross-project federation, provider-specific orchestration, worker rankings, or
automatic permanent rule creation.

## v0.1 boundary

v0.1 consists of a concise Skill, normative project documents, JSON definitions,
an append-only hash-chained JSONL ledger, a deterministic Python CLI, resource
leases, gate evidence, recovery output, and tests for the minimum journeys.

The supported coordination boundary is one repository on one machine. Git may
transport immutable history but is not a realtime lock service.

Actor identity is a local caller assertion, not cryptographic authentication.
The trusted boundary is the OS account and worktree permissions. Ledger hashes
make later edits tamper-evident but not tamper-proof; protection against a
hostile same-account writer is out of scope for v0.x.
