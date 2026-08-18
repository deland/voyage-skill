# VoyageSkill system graph contract

- Version: 0.1.0
- Status: active
- Authority: D-0001, D-0002

## Runtime contract authority

The Python core validator and event replay are the normative runtime contract.
JSON Schema files are the versioned exchange contract for manifests,
definitions, registries, and events. Executable consistency tests require all
runtime-produced and repository dogfood instances to satisfy that exchange
contract. If the two disagree, runtime behavior must fail safely and the
contract drift must be resolved in one tested change; a Schema file alone does
not silently alter runtime authority.

## Node types

The minimum graph contains `project`, `principal`, `loop-binding`,
`truth-source`, `decision`, `work-item`, `delivery`, `immutable-anchor`,
`evidence`, `gate`, `resource`, `lease`, `environment`, `channel`, `rule`,
`block`, and `external-anchor` nodes.

Every node has a stable ID, type, schema version, status, scope, authority,
provenance, risk, evidence references, and optional supersession reference.

## Edge types

The minimum graph supports `governs`, `depends-on`, `authorized-by`,
`bound-to-loop`, `assigned-to`, `delivered-via`, `acknowledged-by`, `claims`,
`releases`, `produces`, `anchored-at`, `validated-by`, `rejects`, `blocks`,
`unblocks`, `supersedes`, `retires`, `readback-of`, and `escalates-to`.

Every edge names its endpoints, preconditions, creating permission, required
evidence, invalidation conditions, and failure transition.

## Invariants

1. Async review, test, merge, and deployment reference an immutable anchor.
2. Execution cannot issue final quality approval for its own delivery.
3. Unsupported declarations cannot advance authoritative state.
4. A failed mandatory gate prevents acceptance and release.
5. Conflicting active resource leases cannot coexist.
6. High-risk action requires a scoped User authorization reference.
7. Repair creates a new delivery and anchor; old verdicts do not transfer.
8. Audit blocks carry minimum scope, evidence, unblock conditions, and appeal.
9. Ledger history is append-only; correction appends reversal or supersession.
10. Dispatch distinguishes sent, acknowledged, and started.

## Runtime state

Planned state records what governance intends. Recovery facts remain separate
from that intent and from one another.

<!-- recovery-facts:start -->
Read derived facts from exactly four buckets: `observed`, `declared`, `unknown`,
and `conflicts`. Require every fact to contain `subject`, `claim`,
`source_event`, `evidence_id`, `evidence_kind`, `verified_at`, `freshness`,
`conclusion`, `blocking_scope`, `next_safe_action`, and `required_loop`.
Treat only live-valid typed evidence or an adapted fresh probe as observed.
Treat replayed claims without qualifying observation as declared. Treat expired,
missing, tampered, legacy-unverified, or unprobed volatile facts as unknown.
Treat only deterministic contradictions in one scope as conflicts, remove their
participants from observed, and block only the reported scope.
<!-- recovery-facts:end -->

Authoritative transitions require observed evidence where the gate demands it.
Unknown and conflicting facts cannot satisfy such a gate.

<!-- work-states:start -->
Durable work states are exactly `draft`, `authorized`, `active`, `delivered`,
`quality-passed`, `accepted`, and `closed`. Side states are exactly `rejected`,
`blocked`, and `awaiting-user`.

The durable progression is draft → authorized → active → delivered →
quality-passed → accepted → closed. Rejection returns to a new execution and
delivery attempt. A block or User wait preserves the exact prior state and
restores it only through its authorized resolution event.
<!-- work-states:end -->

<!-- rule-states:start -->
Durable rule states are exactly `proposed`, `approved`, `applied`, `active`,
`retired`, and `superseded`. A successful `rule.verified` event moves applied
directly to active. `rule.verification-failed` leaves the durable state applied;
`rule.rolled-back` returns it to approved for revision and reapplication.
<!-- rule-states:end -->

## Ledger integrity

Each JSONL event contains an event ID, timestamp, principal, loop, type,
subject, risk, causal reference, payload, evidence, anchor, authorization,
previous event hash, and its own canonical SHA-256 hash. The current view is
derived by replay. Historical lines are never updated in place.

## Resource model

Resource definitions describe type, conflict key, concurrency mode, probe,
lease duration, permissions, cleanup, and gates. Supported minimum types are
file, account, port, environment, session, window, and quota.

Definitions state policy; live availability requires both ledger lease state and
a sufficiently fresh probe. Expired external leases require recovery probing and
do not prove release.

## Evidence matching

Evidence must match the claim: authorization proves permission; hashes prove
artifact identity; complete command output proves process result; runtime
readback proves environment state; User or real-user outcome proves product
result. No evidence type silently grants authority outside its domain.
