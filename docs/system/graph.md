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

## Permanent kernel contract

<!-- kernel-contract:start -->
The permanent kernel contains node types `project`, `principal`, `loop-binding`,
`truth-source`, `decision`, `work-item`, `delivery`, `immutable-anchor`,
`evidence`, `gate`, `resource`, `lease`, `rule`, `block`, and `external-anchor`.

Its edge types are `governs`, `depends-on`, `authorized-by`, `bound-to-loop`,
`assigned-to`, `delivered-via`, `claims`, `releases`, `produces`, `anchored-at`,
`validated-by`, `rejects`, `blocks`, `unblocks`, `supersedes`, `retires`, and
`escalates-to`. Its scoped permission loops are `execution`, `quality`,
`governance`, and `audit`.

The kernel always retains truth and User decisions, work and immutable
delivery, typed evidence and independent quality, resources and leases, gates,
append-only recovery, four-loop authority, minimum-scope blocks, and the
minimal rule safety chain.
<!-- kernel-contract:end -->

Every node has a stable ID, type, schema version, status, scope, authority,
provenance, risk, evidence references, and optional supersession reference.

## Optional extension contract

<!-- extension-contract:start -->
The immutable version-1 catalog contains `advanced-audit`, `channel-tracking`,
`environment-control`, `quota-cost`, `advanced-rules`, and `derived-graph`.
`advanced-audit`, `channel-tracking`, and `environment-control` are available;
`derived-graph` is also available as a read-only projection extension. The
`quota-cost` and `advanced-rules` entries remain reserved and cannot be enabled
before their behavior is implemented.

`advanced-audit` gates `audit.finding`. `channel-tracking` adds node `channel`,
edge `acknowledged-by`, and its sent/acknowledged/started events.
`environment-control` adds node `environment`, edge `readback-of`, and
`environment.readback`. These additions do not remove a kernel type or gate.
Environment resources and runtime-readback evidence remain usable kernel types;
the optional extension controls the advanced environment workflow event.

Enable or disable only through append-only events bound to an exact User
decision and catalog version. Disabled history remains replayable. Projects
without the explicit initialization marker remain legacy-compatible and do not
gain invented extension state.
<!-- extension-contract:end -->

## Derived runtime graph

<!-- derived-graph-contract:start -->
Derived graph exchange `schema_version` 1 is available only after the
`derived-graph` extension is explicitly enabled. It is a read-only disposable
view derived from the manifest-resolved truth registry, ledger, graph,
resources, gates, and content-addressed evidence. It is not a source of truth.
Identical registered input produces the same `source_fingerprints`, sorted
`nodes`, sorted `edges`, and overall fingerprint; no wall-clock or session field
is included.

Every node records its namespaced ID, effective type, status, scope, authority,
risk, evidence, provenance, supersession, and deterministic attributes. Every
edge records its content-derived ID, effective type, source, target, status,
authority, evidence, provenance, and deterministic attributes. The projection
covers project truth, loop bindings, principals, decisions, work dependencies,
all delivery attempts, immutable anchors, evidence, gates, resources, leases,
rules, blocks, appeal targets, and explicit external anchors.

Consistency issue codes are `duplicate-node-id`, `duplicate-edge-id`,
`unknown-node-type`, `unknown-edge-type`, `dangling-edge`,
`dangling-reference`, `dependency-cycle`, `invalid-anchor`,
`orphan-active-node`, `unresolvable-block`, and `project-invalid`. Checking may
diagnose hash-consistent damaged dependency payloads without treating a partial
view as valid. Paths are directed deterministic shortest paths.

There is no graph database, no cache or persisted index, no graph UI, and no
writable graph API. Disabling the extension removes query access without
altering the ledger or deleting extension history.
<!-- derived-graph-contract:end -->

Every edge names its endpoints, preconditions, creating permission, required
evidence, invalidation conditions, and failure transition.

## Executable risk enforcement

<!-- risk-enforcement:start -->
New work records a version-1 `risk_assessment` containing requested and
effective mode, risk domains, environment-change intent, classification
unknown/disputed flags, typed classification evidence, and escalation reasons.
Effective risk is monotonic across the request, required resource risks, and
the high-risk domain set.

Optional gate definitions may add `risk_modes` and `risk_domains`. A mandatory
gate always applies; a mode gate applies to its named effective mode; a domain
gate applies to matching Strict work. No risk policy can remove a mandatory
gate.

Strict `work.authorize`, `work.start`, and `resource.claim` transitions require
a recorded User decision scoped to the exact action, project, work, and, for a
claim, resource. Strict start consumes a fresh `runtime-readback`; acceptance
consumes a separate fresh post-action readback and requires `audit.checked` on
the current delivery anchor. Light and Standard require post-action readback
only when `risk_assessment` declares an environment change.

Resource probe references remain on the lease. The legacy work without the policy
marker replays under its historical transition rules and never receives an
invented assessment.
<!-- risk-enforcement:end -->

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
