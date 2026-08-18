---
name: voyage-skill
description: Operate long-running multi-agent software projects as verifiable runtime graphs with scoped sources of truth, immutable delivery anchors, independent execution/quality/governance/audit loops, resource leases, gates, append-only state, recovery, and User authorization. Use when Codex needs to initialize, resume, govern, validate, audit, or recover a VoyageSkill-managed project, coordinate shared files/accounts/ports/environments/sessions, or evolve project rules safely.
---

# VoyageSkill

Treat this file as a stable entry, never as project state.

## Discover

1. Locate the managed project root containing `.voyage/manifest.json`.
2. Read the truth registry named by the manifest.
3. Run `voyage truth status`; treat bootstrap and legacy-bootstrap projects as not authorized for work execution.
4. Read only the active, activation-verified sources needed for the current domain.
5. Treat `docs/research/`, chat memory, summaries, drafts, and worker claims as non-authoritative.
6. Stop and report a conflict when an active source cannot be resolved.

## Recover

Run these commands before resuming an existing project:

```bash
python3 <voyage-skill>/scripts/voyage.py --root <project> validate
python3 <voyage-skill>/scripts/voyage.py --root <project> truth status
python3 <voyage-skill>/scripts/voyage.py --root <project> evidence verify <evidence-id> --actor <principal>
python3 <voyage-skill>/scripts/voyage.py --root <project> recover
```

Use the recovery output to distinguish observed, declared, unknown, and
conflicting state. Re-probe volatile resources before dispatching work.
Do not authorize work until the reported project stage is `operational`; follow
the registered runbook for bootstrap activation or legacy migration.

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

## Operate

- Create work with scope, non-goals, risk, acceptance criteria, and required resources.
- Bind permissions by work scope; do not invent fixed permanent roles.
- Require a new immutable anchor for every delivery attempt.
- Record typed evidence before delivery and run `voyage evidence verify` before consuming volatile evidence.
- Keep execution and final quality signatures on the same delivery independent.
- Reference the same anchor from asynchronous review, test, merge, and deployment actions.
- Record complete gate counts, including failures, skips, and unknown results.
- Register and claim files, accounts, ports, environments, and sessions before use.
- Treat a registry entry as a policy definition, not proof that a resource is free.
- Stop high-risk or irreversible work until a referenced User authorization exists.
- Append events through the CLI; never rewrite ledger history manually.

## Govern and audit

- Prevent fast loops from modifying product scope, active truth, or mandatory gates.
- Let quality reject execution evidence; never override a failed mandatory gate with a summary.
- Let audit block only the smallest evidenced scope and require objective unblock conditions.
- Move rules through propose, approve, apply, verify, and active states.
- Keep proposer separate from approver, applier separate from verifier, and audit blocker separate from appeal resolver.
- Retire or supersede obsolete rules instead of accumulating permanent checks.

## Load authoritative detail

<!-- extension-loading:start -->
For an extension-related task, run `voyage extension status` first. Resolve the
active system truth through the manifest and truth registry, then read only its
extension contract section needed for the requested extension. Treat reserved
catalog entries as unavailable, and never infer an extension file path or load
extension detail for an unrelated core task.
<!-- extension-loading:end -->

- Resolve the truth registry from the managed project's manifest.
- Resolve the one active, activation-verified source for each required domain:
  `product`, `governance`, `system`, and `operations`.
- Resolve optional planning, decision, or extension sources only when the
  current task requires their registered domain.
- Never infer a source path from this Skill or from another project's layout.

Use `python3 <voyage-skill>/scripts/voyage.py --help` for deterministic commands.
