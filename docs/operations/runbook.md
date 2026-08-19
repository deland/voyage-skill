# VoyageSkill operations and recovery runbook

- Version: 0.2.0
- Status: active
- Authority: D-0001, D-0002

## Cold start

1. Locate `.voyage/manifest.json` and resolve the project root.
2. Read the manifest's truth registry.
3. Validate active source existence and ledger hash continuity.
4. Replay work, rule, gate, block, decision, and lease events.
5. Probe volatile resources before trusting their availability.
6. Report observed, declared, unknown, and conflicting state separately.
7. Continue only actions whose scope, permission, resources, and gates are clear.

Commands:

```bash
python3 <voyage-skill>/scripts/voyage.py --root <project> validate
python3 <voyage-skill>/scripts/voyage.py --root <project> truth status
python3 <voyage-skill>/scripts/voyage.py --root <project> recover
```

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

## CLI command reference

This marked section is generated from argparse. Run
`python3 scripts/voyage-reference.py --check docs/operations/runbook.md` in CI;
use `--print` to inspect or `--write` to update it after an intentional CLI
change.

<!-- voyage-cli-reference:start -->
| Command |
| --- |
| `voyage audit check` |
| `voyage event record` |
| `voyage evidence record` |
| `voyage evidence show` |
| `voyage evidence verify` |
| `voyage extension disable` |
| `voyage extension enable` |
| `voyage extension list` |
| `voyage extension status` |
| `voyage gate record` |
| `voyage graph check` |
| `voyage graph derive` |
| `voyage graph path` |
| `voyage init` |
| `voyage recover` |
| `voyage resource claim` |
| `voyage resource list` |
| `voyage resource recover` |
| `voyage resource register` |
| `voyage resource release` |
| `voyage risk policy` |
| `voyage risk status` |
| `voyage rule apply` |
| `voyage rule approve` |
| `voyage rule propose` |
| `voyage rule retire` |
| `voyage rule rollback` |
| `voyage rule supersede` |
| `voyage rule verify` |
| `voyage rule verify-fail` |
| `voyage status` |
| `voyage truth activate` |
| `voyage truth list` |
| `voyage truth migrate` |
| `voyage truth status` |
| `voyage validate` |
| `voyage work accept` |
| `voyage work authorize` |
| `voyage work await-user` |
| `voyage work block` |
| `voyage work close` |
| `voyage work create` |
| `voyage work deliver` |
| `voyage work quality` |
| `voyage work resume` |
| `voyage work start` |
| `voyage work unblock` |
<!-- voyage-cli-reference:end -->

## Distribution operations

Use either the **source-checkout Skill bundle** or an **installable CLI artifact**.
From a checkout, invoke `python3 <voyage-skill>/scripts/voyage.py`;
from an installed artifact, invoke `voyage`. Both must expose the same command
contract and version. Build tools are explicit build prerequisites, not runtime
dependencies of the installed CLI.

Construct and verify candidate artifacts outside the source tree. Preserve the
source commit, artifact digest, interpreter, complete test totals, and raw
command output. Never treat a wheel, archive, generated report, or successful
test as project truth.

Build one exact commit with a fixed non-negative timestamp into a new external
directory, then install the reported wheel without an index or dependency
resolution:

```bash
python3 scripts/voyage-build.py --source . --output <external-new-directory> --revision <full-commit> --source-date-epoch <epoch>
python3 -m venv <external-venv>
<external-venv>/bin/python -m pip install --no-index --no-deps <reported-wheel>
<external-venv>/bin/voyage --version
<external-venv>/bin/voyage --help
```

The builder reads package and source files from the commit, verifies wheel
RECORD hashes and the console entry point, emits wheel/source SHA-256 values,
and rejects an output directory inside the checkout before mutation. Rebuild
with the same commit and epoch to compare byte-identical digests. Treat a
missing Git commit, non-repository source, existing output directory, changed
digest, missing RECORD, or wrong entry point as a failed candidate.

Stop after local verification. Uploading, tagging, signing, or creating any
remote release requires separate scoped User authorization; PLAN-0002 does not
grant publication authority.

## Bootstrap and truth activation

`voyage init` creates a `bootstrap` project. Generated product, governance,
system, and operations contracts remain draft and contain explicit TODO fields.
Review and edit them before recording any activation decision.

If init is interrupted, `.voyage/init-state.json` records the exact project ID,
truth-registry mode/path, completed phase, and next action. Rerun the identical
`voyage init` command; do not edit the marker or switch arguments. Resume is
idempotent, never duplicates `project.initialized`, and removes the marker only
after a valid bootstrap readback. An adopted registry remains user-owned and is
never overwritten during retry.

Inspect the exact sources and gaps:

```bash
voyage --root <project> truth list
voyage --root <project> truth status
```

Both `truth status` and `recover` read the persisted project ID, truth-registry
path, and current ledger head; use those fields to confirm that a new process
has reopened the intended project. `status --full` retains the independent
quality verdict, actor, exact delivery anchor, typed evidence IDs, complete
counts, and source event alongside the effective mandatory-gate result.

Record a User-loop `decision.recorded` event whose payload scope contains the
project ID, action `truth.activate`, and exact source IDs. Then activate each
source through governance:

```bash
voyage --root <project> truth activate <source-id> --decision <decision-id> --actor <governance-principal>
```

When replacing an active source in the same domain, add `--supersedes
<old-source-id>`. Cross-domain replacement and activation without matching User
scope are invalid. The project becomes operational only after product,
governance, system, and operations are active and each has ledger activation
evidence. Work authorization is blocked before then.

For a v0.1 manifest with no project stage, first inspect its active sources,
record a User decision scoped to action `truth.migrate` and the exact project,
then run:

```bash
voyage --root <project> truth migrate --decision <decision-id> --actor <governance-principal>
```

Migration appends confirmation evidence and adds the operational stage; it does
not rewrite earlier ledger events. Do not use migration to bypass a new
bootstrap project's per-source activation.

## Extension operations

<!-- extension-operations:start -->
New projects start with no enabled extension. Inspect the catalog and current
state with `voyage extension list` and `voyage extension status`.

Before enable, record a User decision whose scope contains action
`extension.enable`, the exact `project_id`, an `extensions` array containing the
target ID, and an `extension_versions` object mapping that ID to the requested
catalog version. Then run:

```bash
voyage --root <project> extension enable <id> --version <version> --decision <decision-id> --actor <governance-principal>
```

Disable uses a separate User decision with action `extension.disable` and the
same exact project, ID, and version scope, followed by `voyage extension
disable`. Both transitions append history; neither rewrites past events or
removes the core independent-quality gate. A `reserved` extension cannot be
enabled. Projects created before the explicit marker report
`legacy-compatible`: replay their old extension events without inventing enable
history, then require the explicit lifecycle for future governed adoption.
<!-- extension-operations:end -->

## Derived graph operations

<!-- derived-graph-operations:start -->
First inspect `voyage extension status`. If `derived-graph` is not enabled,
record an exact User decision for `extension.enable`, project ID, extension ID,
and version 1.0.0, then run the normal `extension enable` command. A
legacy-compatible project does not infer graph access from old history.

Use `voyage graph derive` for the deterministic versioned node/edge view,
`voyage graph check` for sorted integrity findings, and `voyage graph path
<from> <to>` for a directed deterministic shortest path. A clean check and a
found path exit 0. Consistency findings or known disconnected endpoints exit 1
with JSON on stdout. Access, unknown endpoint, and usage errors exit 2 through
the standard error channel.

The commands are read-only: they append no event and create no cache, index, or
generated graph file. `graph check` can report a hash-consistent damaged work
dependency as `dangling-reference` or `dependency-cycle` even when normal
replay cannot form an authoritative state. Never use that diagnostic partial
view as project truth. Disable through the governed extension lifecycle when
the query capability is no longer needed.
<!-- derived-graph-operations:end -->

## Full-ledger benchmark

<!-- ledger-performance-operations:start -->
Run the disposable diagnostic outside normal project operations:

```bash
python3 scripts/voyage-benchmark.py
```

It measures load, full hash validation, and full replay at 1,000, 10,000, and
100,000 events without reading or writing a managed project. Version 1 retains
full replay while the 100,000-event median remains below 2.0 seconds and the
ledger remains below 256 MiB. Smaller custom samples are calibration only and
return insufficient data for the snapshot decision.

Crossing either threshold does not create a snapshot. Open a separate
User-approved work item first. Any future derived snapshot must cite the exact
ledger-head hash, be disposable, and leave full-chain validation as the
authority. v0.x provides no snapshot, checkpoint, compaction, or incremental
index command.
<!-- ledger-performance-operations:end -->

## Platform capability recovery

<!-- platform-operations:start -->
Inspect `runtime_capabilities` in `voyage recover` before permitting writes.
VoyageSkill v0.x supports ledger append only with the Unix `fcntl` advisory
lock backend. Read-only validate, recover, and graph inspection remain usable
when the backend is absent, but every append must stop before mutation.

A Windows locking adapter is not implemented. Keep the project read-only and
move writes to a supported Unix worktree or an external serialized writer.
Never disable locking, use Git as a realtime lock, or claim multi-host write
coordination.
<!-- platform-operations:end -->

## Risk policy operations

<!-- risk-operations:start -->
Read the versioned matrix with `voyage risk policy` and inspect one derived work
assessment with `voyage risk status <work>`. Supply classification evidence and
the relevant domain, unknown/disputed, and environment-change flags when
creating work; the ledger stores the canonical `risk_assessment` and escalation
reasons.

For Strict work, record separate User decisions scoped to the exact project,
work, and actions `work.authorize` and `work.start`. Attach a fresh
`runtime-readback` to start. Before `resource.claim`, retain a valid typed probe
and cite a decision also scoped to the exact resource. After delivery and
independent quality, record `voyage audit check` (`audit.checked`) on the current immutable anchor
and attach a separate fresh post-action readback to acceptance.

Light probes conflict-prone resources; Standard probes every declared resource;
Strict adds the exact decision and retains the pre-action readback. An
environment change requires a post-action readback in every mode. Failed policy
checks append nothing. The legacy work without the version-1 marker continues its
historical replay path and must not be rewritten to fabricate evidence.
<!-- risk-operations:end -->

## Typed evidence protocol

Prepare a version-1 JSON evidence document, then store and verify it:

```bash
voyage --root <project> evidence record --file <evidence.json> --actor <principal>
voyage --root <project> evidence show sha256:<digest>
voyage --root <project> evidence verify sha256:<digest> --actor <principal>
```

The body is stored at `.voyage/evidence/sha256/<digest>.json`; the ledger stores
the stable `sha256:<digest>` ID and an append-only `evidence.verified` result.
Every document has `kind`, `version`, `claim`, `locator`, `observed_at`, and
`producer`. Supported kinds are `git-commit`, `artifact-digest`,
`command-result`, `runtime-readback`, and `user-decision`.

Git commits must use a full readable commit SHA. Artifact and raw command-output
digests are recomputed from project-contained files. Command results include
argv, cwd, exit code, complete pass/fail/skip/unknown counts, and unfiltered
stdout/stderr artifacts. A `runtime-readback` is valid only inside its declared
freshness interval; expiry produces `unknown`, never pass. User decisions are
rechecked against the current User-loop event, exact action/project/source
scope, and revocation state.

Delivery, independent quality, and gate events consume typed IDs and revalidate
the underlying fact at use time. Existing free-form ledger references remain
readable as `legacy-unverified`, but cannot satisfy a newly appended delivery,
quality, or gate transition. Record or re-verify typed evidence explicitly;
never rename a legacy string to a `sha256:` ID or infer trust from old session
memory.

## Work protocol

1. Create work with scope, acceptance, non-goals, risk, dependencies, and resources.
2. Record governance authorization; strict risk includes a User decision reference.
3. Probe and claim resources.
4. Record execution start, delivery, immutable anchor, and self-test evidence.
5. Bind independent quality to the exact delivery anchor.
6. Record complete gate counts and readback evidence.
7. Reject failures; create a new anchor for repair.
8. Accept only when independent quality and every mandatory gate pass.
9. Release resources and close with final evidence.

## Resource protocol

- Register resource policy through `voyage resource register` under governance authority.
- Claim a registered resource before mutation.
- Enforce local conflict policies through the CLI.
- Store credential references only; never write secret values to definitions or ledger.
- Treat expiry as `recovery-required` for external or stateful resources.
- Probe the actual port, account, environment, or session before reassignment.
- Record abnormal recovery and cleanup as evidence-bearing events.

The canonical event subject for claim, release, and recover is the resource ID,
which must match `payload.resource_id`; the lease ID is
`payload.lease_id`. CLI release/recover accepts a lease ID, resolves the real
resource ID from replayed state, and writes that resource as the event subject.

## Gate protocol

Record total, passed, failed, skipped, and unknown counts. A gate passes only
when failed and unknown are zero and its skip policy is satisfied. Preserve
actual exit status; do not infer success from filtered text.

For environment changes, separately read back command result, health, target
artifact, configuration, data/migration level, identity/permission path, key
user path, and operational signals.

## Escalation

Stop in a safe state and create `awaiting-user` when an action is strict risk,
irreversible, outside authority, based on conflicting truth, or missing required
evidence. Present the smallest decision: proposed action, scope, evidence, risk,
reversal, cost, and exact authorization needed.

Record the User response as a `decision.recorded` event. Resume only through a
governance event that references that decision ID; a non-empty note or an
unrecorded chat claim is not authorization.

## Audit and rules

Use audit rejection for systemic execution, quality, or governance failure.
Block only affected objects. A rule proposal never changes active behavior until
independently approved and applied; application does not prove effectiveness.
Verify through an independent check or later real delivery, then activate.

Review active rules for duplication, cost, trigger relevance, and retirement.

## Incident recovery

1. Freeze only the affected transition or resource.
2. Preserve ledger, command output, process identity, artifact hashes, and readback.
3. Classify the earliest failed loop or system object.
4. Restore to a known immutable anchor or safe external state.
5. Re-probe resources and invalidate conclusions tied to changed anchors.
6. Append recovery events; never rewrite the incident history.
7. Propose a rule only if the existing system could not reasonably prevent it.
