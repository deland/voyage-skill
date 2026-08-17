from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from .core import (
    VoyageError,
    activate_truth,
    active_leases,
    append_event,
    current_state,
    initialize_project,
    load_evidence,
    load_json,
    migrate_legacy_project,
    new_lease_expiry,
    probe_port,
    project_paths,
    register_resource,
    recovery_snapshot,
    record_evidence,
    record_evidence_verification,
    SUPPORTED_EVENT_TYPES,
    truth_status,
    validate_project,
)


CLI_EVENT_TYPES = frozenset(SUPPORTED_EVENT_TYPES)


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def common_actor(parser: argparse.ArgumentParser, *, loop: str | None = None) -> None:
    parser.add_argument("--actor", required=True, help="Stable project principal ID")
    if loop is None:
        parser.add_argument("--loop", required=True, choices=["execution", "quality", "governance", "audit", "user", "system"])
    parser.set_defaults(fixed_loop=loop)


def common_evidence(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--evidence", action="append", default=[], help="Evidence reference; repeat as needed")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="voyage", description="VoyageSkill deterministic project control")
    parser.add_argument("--root", default=".", help="Managed project root")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Initialize a managed project")
    init.add_argument("--project-id", required=True)
    init.add_argument("--truth-registry", help="Adopt an existing project-relative truth registry instead of creating templates")

    sub.add_parser("validate", help="Validate truth, definitions, ledger, and state transitions")
    status = sub.add_parser("status", help="Show the derived project state")
    status.add_argument("--full", action="store_true", help="Include complete derived state")
    sub.add_parser("recover", help="Show a cold-start recovery snapshot")

    evidence = sub.add_parser("evidence", help="Record and revalidate typed evidence")
    evidence_sub = evidence.add_subparsers(dest="evidence_command", required=True)
    evidence_record = evidence_sub.add_parser("record", help="Store a versioned evidence JSON document and append verification")
    evidence_record.add_argument("--file", required=True, help="JSON evidence document")
    common_actor(evidence_record, loop="system")
    evidence_show = evidence_sub.add_parser("show", help="Read one content-addressed evidence document")
    evidence_show.add_argument("evidence_id")
    evidence_verify = evidence_sub.add_parser("verify", help="Re-read real state and append a fresh verification result")
    evidence_verify.add_argument("evidence_id")
    common_actor(evidence_verify, loop="system")

    truth = sub.add_parser("truth", help="Inspect and activate registered sources of truth")
    truth_sub = truth.add_subparsers(dest="truth_command", required=True)
    truth_sub.add_parser("list", help="List registered truth sources and activation evidence")
    truth_sub.add_parser("status", help="Show bootstrap stage, gaps, and next safe action")
    activate = truth_sub.add_parser("activate", help="Activate one exact truth source through a scoped User decision")
    activate.add_argument("source_id")
    activate.add_argument("--decision", required=True, help="Recorded User decision ID covering this source")
    activate.add_argument("--supersedes", help="Existing active source in the same domain")
    common_actor(activate, loop="governance")
    migrate = truth_sub.add_parser("migrate", help="Confirm a v0.1 legacy project through a scoped User decision")
    migrate.add_argument("--decision", required=True, help="Recorded User decision ID covering truth.migrate")
    common_actor(migrate, loop="governance")

    work = sub.add_parser("work", help="Operate work items")
    work_sub = work.add_subparsers(dest="work_command", required=True)

    create = work_sub.add_parser("create")
    create.add_argument("work_id")
    create.add_argument("--title", required=True)
    create.add_argument("--scope", required=True)
    create.add_argument("--acceptance", action="append", required=True)
    create.add_argument("--non-goal", action="append", default=[])
    create.add_argument("--dependency", action="append", default=[])
    create.add_argument("--resource", action="append", default=[])
    create.add_argument("--risk", choices=["light", "standard", "strict"], default="standard")
    common_actor(create, loop="governance")

    authorize = work_sub.add_parser("authorize")
    authorize.add_argument("work_id")
    authorize.add_argument("--authorization", help="Required User decision reference for strict risk")
    common_actor(authorize, loop="governance")

    start = work_sub.add_parser("start")
    start.add_argument("work_id")
    common_actor(start, loop="execution")

    deliver = work_sub.add_parser("deliver")
    deliver.add_argument("work_id")
    deliver.add_argument("--anchor", required=True, help="Immutable commit, tag, digest, or exact diff reference")
    common_evidence(deliver)
    common_actor(deliver, loop="execution")

    quality = work_sub.add_parser("quality")
    quality.add_argument("work_id")
    quality.add_argument("--verdict", required=True, choices=["pass", "reject"])
    quality.add_argument("--anchor", required=True)
    quality.add_argument("--total", type=int, default=1)
    quality.add_argument("--passed", type=int)
    quality.add_argument("--failed", type=int)
    quality.add_argument("--skipped", type=int, default=0)
    quality.add_argument("--unknown", type=int, default=0)
    common_evidence(quality)
    common_actor(quality, loop="quality")

    accept = work_sub.add_parser("accept")
    accept.add_argument("work_id")
    common_actor(accept, loop="governance")

    close = work_sub.add_parser("close")
    close.add_argument("work_id")
    common_actor(close, loop="governance")

    block = work_sub.add_parser("block")
    block.add_argument("work_id")
    block.add_argument("--block-id")
    block.add_argument("--reason", required=True)
    block.add_argument("--scope", required=True)
    block.add_argument("--unblock-condition", required=True)
    block.add_argument("--appeal-to", required=True)
    common_evidence(block)
    common_actor(block)

    unblock = work_sub.add_parser("unblock")
    unblock.add_argument("work_id")
    common_evidence(unblock)
    common_actor(unblock)

    await_user = work_sub.add_parser("await-user")
    await_user.add_argument("work_id")
    await_user.add_argument("--decision", required=True)
    common_actor(await_user)

    resume = work_sub.add_parser("resume")
    resume.add_argument("work_id")
    resume.add_argument("--authorization", required=True, help="Recorded User decision ID")
    common_actor(resume, loop="governance")

    gate = sub.add_parser("gate", help="Record complete gate results")
    gate_sub = gate.add_subparsers(dest="gate_command", required=True)
    gate_record = gate_sub.add_parser("record")
    gate_record.add_argument("gate_id")
    gate_record.add_argument("--work", required=True)
    gate_record.add_argument("--anchor", required=True)
    gate_record.add_argument("--total", required=True, type=int)
    gate_record.add_argument("--passed", required=True, type=int)
    gate_record.add_argument("--failed", required=True, type=int)
    gate_record.add_argument("--skipped", required=True, type=int)
    gate_record.add_argument("--unknown", required=True, type=int)
    common_evidence(gate_record)
    common_actor(gate_record, loop="quality")

    resource = sub.add_parser("resource", help="Operate registered resource leases")
    resource_sub = resource.add_subparsers(dest="resource_command", required=True)
    register = resource_sub.add_parser("register")
    register.add_argument("resource_id")
    register.add_argument("--type", required=True, choices=["file", "account", "port", "environment", "session", "window", "quota"], dest="resource_type")
    register.add_argument("--mode", required=True, choices=["exclusive", "shared-read", "serialized", "rebuildable"])
    register.add_argument("--conflict-key")
    register.add_argument("--risk", choices=["light", "standard", "strict"], default="standard")
    register.add_argument("--probe-json", help="Probe definition as a JSON object")
    common_actor(register, loop="governance")
    claim = resource_sub.add_parser("claim")
    claim.add_argument("resource_id")
    claim.add_argument("--work", required=True)
    claim.add_argument("--lease-id")
    claim.add_argument("--ttl-minutes", type=int, default=60)
    common_evidence(claim)
    common_actor(claim, loop="execution")
    for name in ("release", "recover"):
        item = resource_sub.add_parser(name)
        item.add_argument("lease_id")
        common_evidence(item)
        common_actor(item)
    resource_sub.add_parser("list")

    rule = sub.add_parser("rule", help="Operate the rule lifecycle")
    rule_sub = rule.add_subparsers(dest="rule_command", required=True)
    propose = rule_sub.add_parser("propose")
    propose.add_argument("rule_id")
    propose.add_argument("--scope", required=True)
    propose.add_argument("--source", required=True)
    propose.add_argument("--cost", required=True)
    propose.add_argument("--verification", required=True)
    propose.add_argument("--retirement", required=True)
    common_actor(propose, loop="audit")
    approve = rule_sub.add_parser("approve")
    approve.add_argument("rule_id")
    common_actor(approve)
    apply_rule = rule_sub.add_parser("apply")
    apply_rule.add_argument("rule_id")
    common_evidence(apply_rule)
    common_actor(apply_rule, loop="governance")
    verify_rule = rule_sub.add_parser("verify")
    verify_rule.add_argument("rule_id")
    common_evidence(verify_rule)
    common_actor(verify_rule)
    verify_fail = rule_sub.add_parser("verify-fail")
    verify_fail.add_argument("rule_id")
    verify_fail.add_argument("--reason", required=True)
    common_evidence(verify_fail)
    common_actor(verify_fail)
    rollback = rule_sub.add_parser("rollback")
    rollback.add_argument("rule_id")
    common_evidence(rollback)
    common_actor(rollback, loop="governance")
    retire = rule_sub.add_parser("retire")
    retire.add_argument("rule_id")
    common_evidence(retire)
    common_actor(retire)
    supersede = rule_sub.add_parser("supersede")
    supersede.add_argument("rule_id")
    supersede.add_argument("--by", required=True, dest="replacement")
    common_evidence(supersede)
    common_actor(supersede)

    event = sub.add_parser("event", help="Record a non-transition observation or decision")
    event_sub = event.add_subparsers(dest="event_command", required=True)
    record = event_sub.add_parser("record")
    record.add_argument("--type", required=True, choices=[
        "decision.recorded", "decision.revoked", "observation.recorded", "channel.sent",
        "channel.acknowledged", "channel.started", "environment.readback", "audit.finding",
    ])
    record.add_argument("--subject", required=True)
    record.add_argument("--risk", choices=["light", "standard", "strict"], default="standard")
    record.add_argument("--payload-json", default="{}")
    record.add_argument("--anchor")
    record.add_argument("--authorization")
    common_evidence(record)
    common_actor(record)

    return parser


def handle_evidence(paths, args) -> None:
    if args.evidence_command == "record":
        document = load_json(Path(args.file).expanduser().resolve())
        emit(record_evidence(paths, document, actor=args.actor))
    elif args.evidence_command == "show":
        emit({"evidence_id": args.evidence_id, "document": load_evidence(paths, args.evidence_id)})
    elif args.evidence_command == "verify":
        emit(record_evidence_verification(paths, args.evidence_id, actor=args.actor))


def append_from_args(paths, args, *, event_type: str, subject: str, risk: str = "standard", payload=None, anchor=None, authorization=None):
    loop = args.fixed_loop if getattr(args, "fixed_loop", None) else args.loop
    event = append_event(
        paths,
        actor=args.actor,
        loop=loop,
        event_type=event_type,
        subject=subject,
        risk=risk,
        payload=payload,
        evidence=getattr(args, "evidence", []),
        anchor=anchor,
        authorization=authorization,
    )
    emit({"recorded": event["event_id"], "type": event_type, "subject": subject, "hash": event["hash"]})


def handle_work(paths, args) -> None:
    command = args.work_command
    if command == "create":
        append_from_args(
            paths, args, event_type="work.created", subject=args.work_id, risk=args.risk,
            payload={
                "title": args.title,
                "scope": args.scope,
                "acceptance": args.acceptance,
                "non_goals": args.non_goal,
                "dependencies": args.dependency,
                "required_resources": args.resource,
            },
        )
    elif command == "authorize":
        append_from_args(paths, args, event_type="work.authorized", subject=args.work_id, authorization=args.authorization)
    elif command == "start":
        append_from_args(paths, args, event_type="work.started", subject=args.work_id)
    elif command == "deliver":
        append_from_args(paths, args, event_type="work.delivered", subject=args.work_id, anchor=args.anchor)
    elif command == "quality":
        passed = args.passed if args.passed is not None else (args.total if args.verdict == "pass" else 0)
        failed = args.failed if args.failed is not None else (args.total if args.verdict == "reject" else 0)
        counts = {"total": args.total, "passed": passed, "failed": failed, "skipped": args.skipped, "unknown": args.unknown}
        if sum(counts[key] for key in ("passed", "failed", "skipped", "unknown")) != counts["total"]:
            raise VoyageError("quality counts do not add up")
        if args.verdict == "pass" and (failed or args.unknown or args.skipped):
            raise VoyageError("passing independent quality cannot contain failed, skipped, or unknown checks")
        append_from_args(
            paths, args, event_type=f"quality.{'passed' if args.verdict == 'pass' else 'rejected'}",
            subject=args.work_id, payload={"counts": counts}, anchor=args.anchor,
        )
    elif command == "accept":
        append_from_args(paths, args, event_type="work.accepted", subject=args.work_id)
    elif command == "close":
        append_from_args(paths, args, event_type="work.closed", subject=args.work_id)
    elif command == "block":
        append_from_args(
            paths, args, event_type="work.blocked", subject=args.work_id,
            payload={
                "block_id": args.block_id,
                "reason": args.reason,
                "scope": args.scope,
                "unblock_condition": args.unblock_condition,
                "appeal_to": args.appeal_to,
            },
        )
    elif command == "unblock":
        append_from_args(paths, args, event_type="work.unblocked", subject=args.work_id)
    elif command == "await-user":
        append_from_args(paths, args, event_type="work.awaiting-user", subject=args.work_id, payload={"decision": args.decision})
    elif command == "resume":
        append_from_args(paths, args, event_type="work.user-authorized", subject=args.work_id, authorization=args.authorization)


def handle_resource(paths, args) -> None:
    if args.resource_command == "list":
        emit({"definitions": load_json(paths.resources).get("resources", []), "active_leases": active_leases(current_state(paths))})
        return
    if args.resource_command == "register":
        probe = None
        if args.probe_json:
            try:
                probe = json.loads(args.probe_json)
            except json.JSONDecodeError as exc:
                raise VoyageError(f"invalid --probe-json: {exc}") from exc
            if not isinstance(probe, dict):
                raise VoyageError("--probe-json must be a JSON object")
        event = register_resource(
            paths,
            actor=args.actor,
            resource_id=args.resource_id,
            resource_type=args.resource_type,
            mode=args.mode,
            conflict_key=args.conflict_key,
            risk=args.risk,
            probe=probe,
        )
        emit({"registered": args.resource_id, "event": event["event_id"], "hash": event["hash"]})
        return
    if args.resource_command == "claim":
        definitions = {item["id"]: item for item in load_json(paths.resources).get("resources", []) if isinstance(item, dict) and item.get("id")}
        definition = definitions.get(args.resource_id)
        if definition is None:
            raise VoyageError(f"unknown resource: {args.resource_id}")
        if definition.get("type") == "port":
            try:
                port = int(definition.get("conflict_key", args.resource_id))
            except (TypeError, ValueError) as exc:
                raise VoyageError(f"port resource {args.resource_id} requires numeric conflict_key") from exc
            if probe_port(port):
                raise VoyageError(f"port {port} is already in use")
        lease_id = args.lease_id or f"lease-{uuid.uuid4().hex[:12]}"
        append_from_args(
            paths, args, event_type="resource.claimed", subject=args.resource_id,
            payload={
                "resource_id": args.resource_id,
                "lease_id": lease_id,
                "work_id": args.work,
                "expires_at": new_lease_expiry(args.ttl_minutes),
            },
        )
    elif args.resource_command in {"release", "recover"}:
        lease = current_state(paths)["leases"].get(args.lease_id)
        if lease is None or not lease.get("active"):
            raise VoyageError(f"active lease not found: {args.lease_id}")
        append_from_args(
            paths, args,
            event_type="resource.recovered" if args.resource_command == "recover" else "resource.released",
            subject=lease["resource_id"],
            payload={"resource_id": lease["resource_id"], "lease_id": args.lease_id},
        )


def handle_rule(paths, args) -> None:
    command = args.rule_command
    if command == "propose":
        append_from_args(
            paths, args, event_type="rule.proposed", subject=args.rule_id,
            payload={"scope": args.scope, "source": args.source, "cost": args.cost, "verification": args.verification, "retirement": args.retirement},
        )
    elif command == "approve":
        append_from_args(paths, args, event_type="rule.approved", subject=args.rule_id)
    elif command == "apply":
        append_from_args(paths, args, event_type="rule.applied", subject=args.rule_id)
    elif command == "verify":
        append_from_args(paths, args, event_type="rule.verified", subject=args.rule_id)
    elif command == "verify-fail":
        append_from_args(paths, args, event_type="rule.verification-failed", subject=args.rule_id, payload={"reason": args.reason})
    elif command == "rollback":
        append_from_args(paths, args, event_type="rule.rolled-back", subject=args.rule_id)
    elif command == "retire":
        append_from_args(paths, args, event_type="rule.retired", subject=args.rule_id)
    elif command == "supersede":
        append_from_args(paths, args, event_type="rule.superseded", subject=args.rule_id, payload={"replacement": args.replacement})


def handle_truth(paths, args) -> None:
    if args.truth_command == "list":
        status = truth_status(paths)
        emit({"project_stage": status["project_stage"], "sources": status["sources"]})
    elif args.truth_command == "status":
        emit(truth_status(paths))
    elif args.truth_command == "activate":
        event = activate_truth(
            paths,
            actor=args.actor,
            source_id=args.source_id,
            decision_id=args.decision,
            supersedes=args.supersedes,
        )
        emit({
            "activated": args.source_id,
            "event": event["event_id"],
            "decision": args.decision,
            "project_stage": truth_status(paths)["project_stage"],
        })
    elif args.truth_command == "migrate":
        event = migrate_legacy_project(paths, actor=args.actor, decision_id=args.decision)
        emit({
            "migrated": event["subject"],
            "event": event["event_id"],
            "decision": args.decision,
            "project_stage": truth_status(paths)["project_stage"],
        })


def run(args: argparse.Namespace) -> int:
    if args.command == "init":
        paths = initialize_project(args.root, args.project_id, args.truth_registry)
        emit({"initialized": str(paths.root), "manifest": str(paths.manifest), "project_stage": "bootstrap"})
        return 0

    paths = project_paths(args.root)
    if args.command == "validate":
        errors = validate_project(paths)
        emit({"valid": not errors, "errors": errors})
        return 0 if not errors else 1
    if args.command == "status":
        state = current_state(paths)
        emit(state if args.full else {
            "works": {key: value["status"] for key, value in state["works"].items()},
            "active_leases": active_leases(state),
            "rules": {key: value["status"] for key, value in state["rules"].items()},
            "active_blocks": [key for key, value in state["blocks"].items() if value["active"]],
            "ledger_head": state["last_event"],
        })
        return 0
    if args.command == "recover":
        errors = validate_project(paths)
        if errors:
            raise VoyageError("cannot recover invalid project: " + "; ".join(errors))
        emit(recovery_snapshot(paths))
        return 0
    if args.command == "evidence":
        handle_evidence(paths, args)
    elif args.command == "work":
        handle_work(paths, args)
    elif args.command == "truth":
        handle_truth(paths, args)
    elif args.command == "gate":
        append_from_args(
            paths, args, event_type="gate.recorded", subject=args.work,
            payload={
                "gate_id": args.gate_id,
                "counts": {"total": args.total, "passed": args.passed, "failed": args.failed, "skipped": args.skipped, "unknown": args.unknown},
            },
            anchor=args.anchor,
        )
    elif args.command == "resource":
        handle_resource(paths, args)
    elif args.command == "rule":
        handle_rule(paths, args)
    elif args.command == "event":
        try:
            payload = json.loads(args.payload_json)
        except json.JSONDecodeError as exc:
            raise VoyageError(f"invalid --payload-json: {exc}") from exc
        if not isinstance(payload, dict):
            raise VoyageError("--payload-json must be a JSON object")
        append_from_args(
            paths, args, event_type=args.type, subject=args.subject, risk=args.risk,
            payload=payload, anchor=args.anchor, authorization=args.authorization,
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except VoyageError as exc:
        print(f"voyage: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
