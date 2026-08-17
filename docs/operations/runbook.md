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
