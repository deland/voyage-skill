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

## CLI command reference

This marked section is generated from argparse. Run
`python3 scripts/voyage-reference.py --check docs/operations/runbook.md` in CI;
use `--print` to inspect or `--write` to update it after an intentional CLI
change.

<!-- voyage-cli-reference:start -->
| Command |
| --- |
| `voyage event record` |
| `voyage evidence record` |
| `voyage evidence show` |
| `voyage evidence verify` |
| `voyage gate record` |
| `voyage init` |
| `voyage recover` |
| `voyage resource claim` |
| `voyage resource list` |
| `voyage resource recover` |
| `voyage resource register` |
| `voyage resource release` |
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

## Bootstrap and truth activation

`voyage init` creates a `bootstrap` project. Generated product, governance,
system, and operations contracts remain draft and contain explicit TODO fields.
Review and edit them before recording any activation decision.

Inspect the exact sources and gaps:

```bash
voyage --root <project> truth list
voyage --root <project> truth status
```

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
