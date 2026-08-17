from __future__ import annotations

import hashlib
from pathlib import Path

import voyage_skill.core as core


REQUIRED_DOMAINS = ("product", "governance", "system", "operations")

REVIEWED_CONTRACTS = {
    "product": """# Product contract

- Status: draft
- Version: 1

## Goals

Deliver the explicitly authorized test outcome.

## Non-goals

Do not perform external or irreversible actions.

## Acceptance boundary

Accept only independently verified work.
""",
    "governance": """# Governance contract

- Status: draft
- Version: 1

## User authority

User retains final authority for high-risk and irreversible actions.

## Loop authority

Execution, quality, governance, and audit remain independent.

## Risk boundary

Unknown risk selects the stricter mode.
""",
    "system": """# System contract

- Status: draft
- Version: 1

## Sources of truth

The manifest and registered active sources define project truth.

## Mandatory gates

Independent quality is mandatory.

## Runtime boundary

State is derived from commands, immutable anchors, and readback.
""",
    "operations": """# Operations runbook

- Status: draft
- Version: 1

## Recovery

Validate and recover before resuming work.

## Validation

Record complete pass, fail, skip, and unknown counts.

## Escalation

Escalate missing authority and high-risk decisions to User.
""",
}


def reviewed_contracts(paths: core.ProjectPaths) -> None:
    registry = core.load_json(paths.truth_registry)
    for source in registry["sources"]:
        domain = source.get("domain")
        if domain in REVIEWED_CONTRACTS:
            (paths.root / source["path"]).write_text(REVIEWED_CONTRACTS[domain], encoding="utf-8")


def record_scoped_decision(
    paths: core.ProjectPaths,
    decision_id: str,
    *,
    action: str,
    sources: list[str] | None = None,
    project_id: str | None = None,
    loop: str = "user",
) -> dict:
    manifest = core.load_json(paths.manifest)
    return core.append_event(
        paths,
        actor="user",
        loop=loop,
        event_type="decision.recorded",
        subject=decision_id,
        risk="standard",
        payload={
            "decision": action,
            "scope": {
                "actions": [action],
                "project_id": project_id or manifest["project_id"],
                "truth_sources": sources or ["*"],
            },
        },
    )


def activate_all_truth(paths: core.ProjectPaths, decision_id: str = "USER-BOOTSTRAP") -> None:
    registry = core.load_json(paths.truth_registry)
    source_ids = [source["id"] for source in registry["sources"] if source.get("domain") in REQUIRED_DOMAINS]
    record_scoped_decision(paths, decision_id, action="truth.activate", sources=source_ids)
    for source_id in source_ids:
        core.activate_truth(paths, actor="gov", source_id=source_id, decision_id=decision_id)


def operational_project(root: Path, project_id: str = "example") -> core.ProjectPaths:
    paths = core.initialize_project(root, project_id)
    reviewed_contracts(paths)
    activate_all_truth(paths)
    return paths


def legacy_project(root: Path, project_id: str = "legacy") -> core.ProjectPaths:
    paths = core.initialize_project(root, project_id)
    manifest = core.load_json(paths.manifest)
    manifest.pop("project_stage", None)
    core.atomic_write_json(paths.manifest, manifest)

    registry = core.load_json(paths.truth_registry)
    for source in registry["sources"]:
        if source.get("domain") in REQUIRED_DOMAINS:
            source["status"] = "active"
            source["authority"] = "legacy-v0.1"
    core.atomic_write_json(paths.truth_registry, registry)

    reviewed_contracts(paths)
    for source in registry["sources"]:
        if source.get("domain") in REQUIRED_DOMAINS:
            path = paths.root / source["path"]
            path.write_text(path.read_text(encoding="utf-8").replace("- Status: draft", "- Status: active"), encoding="utf-8")

    events = core.load_events(paths.ledger)
    previous = None
    for event in events:
        if event.get("type") == "project.initialized":
            event.get("payload", {}).pop("project_stage", None)
        event["prev_hash"] = previous
        body = {key: value for key, value in event.items() if key != "hash"}
        event["hash"] = core.content_hash(body)
        previous = event["hash"]
    paths.ledger.write_text("".join(core.canonical_json(event) + "\n" for event in events), encoding="utf-8")
    return paths


def typed_artifact_anchor(
    paths: core.ProjectPaths,
    *,
    name: str = "delivery",
    content: bytes | None = None,
    producer: str = "dev",
) -> str:
    body = content if content is not None else f"artifact:{name}\n".encode("utf-8")
    relative = f".voyage/test-artifacts/{name}.bin"
    target = paths.root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)
    result = core.record_evidence(
        paths,
        {
            "kind": "artifact-digest",
            "version": 1,
            "claim": "delivery-artifact",
            "locator": {"path": relative, "algorithm": "sha256", "digest": hashlib.sha256(body).hexdigest()},
            "observed_at": core.utc_now(),
            "producer": producer,
        },
        actor=producer,
    )
    return result["evidence_id"]


def typed_command_evidence(
    paths: core.ProjectPaths,
    *,
    name: str = "command",
    producer: str = "tester",
) -> str:
    stdout_body = f"{name}: 1 passed\n".encode("utf-8")
    stderr_body = b""
    base = f".voyage/test-artifacts/{name}"
    stdout_path = paths.root / f"{base}.stdout"
    stderr_path = paths.root / f"{base}.stderr"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_bytes(stdout_body)
    stderr_path.write_bytes(stderr_body)
    result = core.record_evidence(
        paths,
        {
            "kind": "command-result",
            "version": 1,
            "claim": "command-passed",
            "locator": {
                "argv": ["fixture", name],
                "cwd": ".",
                "exit_code": 0,
                "stdout": {"path": f"{base}.stdout", "bytes": len(stdout_body), "sha256": hashlib.sha256(stdout_body).hexdigest()},
                "stderr": {"path": f"{base}.stderr", "bytes": 0, "sha256": hashlib.sha256(stderr_body).hexdigest()},
                "counts": {"total": 1, "passed": 1, "failed": 0, "skipped": 0, "unknown": 0},
            },
            "observed_at": core.utc_now(),
            "producer": producer,
        },
        actor=producer,
    )
    return result["evidence_id"]


def find_typed_evidence(paths: core.ProjectPaths, *, kind: str, producer: str) -> str:
    for path in sorted((paths.evidence / "sha256").glob("*.json")):
        document = core.load_json(path)
        if document.get("kind") == kind and document.get("producer") == producer:
            return f"sha256:{path.stem}"
    raise AssertionError(f"fixture evidence not found: kind={kind} producer={producer}")
