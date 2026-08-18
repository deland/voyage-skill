from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import socket
import subprocess
import tempfile
import uuid
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator


SCHEMA_VERSION = "0.1.0"
LOOPS = {"execution", "quality", "governance", "audit", "user", "system"}
RISK_MODE_ORDER = ("light", "standard", "strict")
RISK_LEVELS = set(RISK_MODE_ORDER)
RISK_POLICY_VERSION = 1
DERIVED_GRAPH_SCHEMA_VERSION = 1
STRICT_RISK_DOMAINS = (
    "credentials", "gate-relaxation", "irreversible", "material-cost",
    "permissions", "persistent-data", "production", "public-external-write",
    "security",
)
RISK_POLICIES = {
    "light": {
        "immutable_anchor": True,
        "independent_quality": True,
        "append_only_ledger": True,
        "extra_gates": "mandatory-core-minimum",
        "audit": "event-triggered",
        "runtime_readback": "after-environment-change",
        "user_authorization": "on-escalation-to-strict",
        "resource_probe": "conflict-prone-resources",
    },
    "standard": {
        "immutable_anchor": True,
        "independent_quality": True,
        "append_only_ledger": True,
        "extra_gates": "project-defined-mode-gates",
        "audit": "periodic-or-event-triggered",
        "runtime_readback": "after-environment-change",
        "user_authorization": "on-escalation-to-strict",
        "resource_probe": "all-declared-resources",
    },
    "strict": {
        "immutable_anchor": True,
        "independent_quality": True,
        "append_only_ledger": True,
        "extra_gates": "matching-risk-domain-full-set",
        "audit": "mandatory-current-anchor-checkpoint",
        "runtime_readback": "fresh-before-and-after-action",
        "user_authorization": "each-strict-execution-action",
        "resource_probe": "fresh-before-action-and-retained",
    },
}
PROBE_EVIDENCE_KINDS = {"command-result", "runtime-readback"}
STATEFUL_RESOURCE_TYPES = {"account", "environment", "session", "window", "quota"}
ALLOWED_RESOURCE_TYPES = {"file", "account", "port", "environment", "session", "window", "quota"}
ALLOWED_RESOURCE_MODES = {"exclusive", "shared-read", "serialized", "rebuildable"}
REQUIRED_TRUTH_DOMAINS = ("product", "governance", "system", "operations")
KERNEL_LOOPS = ("audit", "execution", "governance", "quality")
KERNEL_NODE_TYPES = (
    "project", "principal", "loop-binding", "truth-source", "decision",
    "work-item", "delivery", "immutable-anchor", "evidence", "gate",
    "resource", "lease", "rule", "block", "external-anchor",
)
KERNEL_EDGE_TYPES = (
    "governs", "depends-on", "authorized-by", "bound-to-loop", "assigned-to",
    "delivered-via", "claims", "releases", "produces", "anchored-at",
    "validated-by", "rejects", "blocks", "unblocks", "supersedes", "retires",
    "escalates-to",
)
EXTENSION_CATALOG = {
    "advanced-audit": {
        "id": "advanced-audit", "version": "1.0.0", "availability": "available",
        "event_types": ("audit.finding",), "node_types": (), "edge_types": (), "gates": (),
    },
    "channel-tracking": {
        "id": "channel-tracking", "version": "1.0.0", "availability": "available",
        "event_types": ("channel.sent", "channel.acknowledged", "channel.started"),
        "node_types": ("channel",), "edge_types": ("acknowledged-by",), "gates": (),
    },
    "environment-control": {
        "id": "environment-control", "version": "1.0.0", "availability": "available",
        "event_types": ("environment.readback",), "node_types": ("environment",),
        "edge_types": ("readback-of",), "gates": (),
    },
    "quota-cost": {
        "id": "quota-cost", "version": "1.0.0", "availability": "reserved",
        "event_types": (), "node_types": (), "edge_types": (), "gates": (),
    },
    "advanced-rules": {
        "id": "advanced-rules", "version": "1.0.0", "availability": "reserved",
        "event_types": (), "node_types": (), "edge_types": (), "gates": (),
    },
    "derived-graph": {
        "id": "derived-graph", "version": "1.0.0", "availability": "available",
        "event_types": (), "node_types": (), "edge_types": (), "gates": (),
    },
}
EXTENSION_EVENT_REQUIREMENTS = {
    event_type: extension_id
    for extension_id, contract in EXTENSION_CATALOG.items()
    for event_type in contract["event_types"]
}
WORK_DURABLE_STATES = ("draft", "authorized", "active", "delivered", "quality-passed", "accepted", "closed")
WORK_SIDE_STATES = ("rejected", "blocked", "awaiting-user")
RULE_DURABLE_STATES = ("proposed", "approved", "applied", "active", "retired", "superseded")
SUPPORTED_EVENT_TYPES = frozenset({
    "project.initialized", "truth.activated", "project.migrated", "evidence.verified",
    "extension.enabled", "extension.disabled",
    "decision.recorded", "decision.revoked", "observation.recorded", "environment.readback", "audit.checked",
    "channel.sent", "channel.acknowledged", "channel.started", "audit.finding",
    "work.created", "work.authorized", "work.started", "work.delivered",
    "quality.passed", "quality.rejected", "gate.recorded", "work.accepted", "work.closed",
    "work.blocked", "work.unblocked", "work.awaiting-user", "work.user-authorized",
    "resource.registered", "resource.claimed", "resource.released", "resource.recovered",
    "rule.proposed", "rule.approved", "rule.applied", "rule.verified",
    "rule.verification-failed", "rule.rolled-back", "rule.superseded", "rule.retired",
})
NEXT_SAFE_ACTIONS = {
    "draft": "governance authorization",
    "authorized": "claim required resources and start execution",
    "active": "produce evidence and immutable delivery anchor",
    "delivered": "independent quality verdict on current anchor",
    "quality-passed": "verify mandatory gates and accept",
    "accepted": "release resources and close",
    "closed": "none",
    "rejected": "start a new execution attempt",
    "blocked": "satisfy block conditions through an independent resolver",
    "awaiting-user": "wait for scoped User decision",
}
RECOVERY_FACT_BUCKETS = ("observed", "declared", "unknown", "conflicts")
RECOVERY_FACT_FIELDS = (
    "subject", "claim", "source_event", "evidence_id", "evidence_kind",
    "verified_at", "freshness", "conclusion", "blocking_scope",
    "next_safe_action", "required_loop",
)
EVIDENCE_KINDS = {"git-commit", "artifact-digest", "command-result", "runtime-readback", "user-decision"}
EVIDENCE_ID_PATTERN = re.compile(r"^sha256:([a-f0-9]{64})$")
EVIDENCE_VALIDATOR_VERSION = 1
REQUIRED_CONTRACT_SECTIONS = {
    "product": ("Goals", "Non-goals", "Acceptance boundary"),
    "governance": ("User authority", "Loop authority", "Risk boundary"),
    "system": ("Sources of truth", "Mandatory gates", "Runtime boundary"),
    "operations": ("Recovery", "Validation", "Escalation"),
}


class VoyageError(Exception):
    """A deterministic validation or operation error."""


@dataclass(frozen=True)
class ProjectPaths:
    root: Path
    control: Path
    manifest: Path
    truth_registry: Path
    graph: Path
    resources: Path
    gates: Path
    ledger: Path
    evidence: Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp is not a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp has no timezone")
    return parsed


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def extension_catalog_view() -> dict[str, dict[str, Any]]:
    return {
        extension_id: {
            key: [deepcopy(item) for item in value] if isinstance(value, tuple) else deepcopy(value)
            for key, value in contract.items()
        }
        for extension_id, contract in EXTENSION_CATALOG.items()
    }


def risk_policy_view() -> dict[str, Any]:
    return {
        "version": RISK_POLICY_VERSION,
        "order": list(RISK_MODE_ORDER),
        "strict_domains": list(STRICT_RISK_DOMAINS),
        "modes": {mode: deepcopy(RISK_POLICIES[mode]) for mode in RISK_MODE_ORDER},
    }


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _inside_project(root: Path, value: Any, *, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise VoyageError(f"{label} must be a non-empty project-relative path")
    target = (root / value).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise VoyageError(f"{label} escapes project root: {value}") from exc
    return target


def _evidence_common_errors(document: Any) -> list[str]:
    if not isinstance(document, dict):
        return ["evidence document must be an object"]
    errors: list[str] = []
    required_types = {
        "kind": str,
        "version": int,
        "claim": str,
        "locator": dict,
        "observed_at": str,
        "producer": str,
    }
    for field, expected in required_types.items():
        value = document.get(field)
        if field not in document:
            errors.append(f"evidence {field} is required")
        elif not isinstance(value, expected) or isinstance(value, bool):
            errors.append(f"evidence {field} has invalid type")
        elif expected is str and not value:
            errors.append(f"evidence {field} must be non-empty")
    if isinstance(document.get("version"), int) and document.get("version") != 1:
        errors.append("evidence version must be 1")
    if isinstance(document.get("kind"), str) and document.get("kind") not in EVIDENCE_KINDS:
        errors.append(f"unsupported evidence kind: {document.get('kind')}")
    if isinstance(document.get("observed_at"), str):
        try:
            parse_time(document["observed_at"])
        except (TypeError, ValueError):
            errors.append("evidence observed_at must be an RFC3339 timestamp")
    return errors


def _descriptor_errors(paths: ProjectPaths, descriptor: Any, *, label: str) -> list[str]:
    if not isinstance(descriptor, dict):
        return [f"{label} must describe a raw output artifact"]
    errors: list[str] = []
    path_value = descriptor.get("path")
    try:
        target = _inside_project(paths.root, path_value, label=f"{label} path")
    except VoyageError as exc:
        return [str(exc)]
    if not target.is_file():
        errors.append(f"{label} artifact is not a file: {path_value}")
        return errors
    content = target.read_bytes()
    byte_count = descriptor.get("bytes")
    digest = descriptor.get("sha256")
    if not isinstance(byte_count, int) or isinstance(byte_count, bool) or byte_count < 0:
        errors.append(f"{label} bytes must be a non-negative integer")
    elif byte_count != len(content):
        errors.append(f"{label} byte count does not match raw artifact")
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        errors.append(f"{label} sha256 must be a full digest")
    elif digest != hashlib.sha256(content).hexdigest():
        errors.append(f"{label} sha256 does not match raw artifact")
    return errors


def _verify_git_commit(paths: ProjectPaths, document: dict[str, Any]) -> tuple[str, list[str]]:
    locator = document["locator"]
    repository = locator.get("repository")
    revision = locator.get("revision")
    try:
        target = _inside_project(paths.root, repository, label="git repository")
    except VoyageError as exc:
        return "invalid", [str(exc)]
    if not target.is_dir():
        return "invalid", [f"git repository is not a directory: {repository}"]
    if not isinstance(revision, str) or not re.fullmatch(r"(?:[a-f0-9]{40}|[a-f0-9]{64})", revision):
        return "invalid", ["git revision must be a full hexadecimal commit SHA"]
    try:
        inside = subprocess.run(
            ["git", "-C", str(target), "rev-parse", "--show-toplevel"],
            check=False,
            text=True,
            capture_output=True,
            timeout=10,
        )
        if inside.returncode != 0:
            return "invalid", [f"not a readable Git repository: {repository}"]
        if Path(inside.stdout.strip()).resolve() != target:
            return "invalid", [f"declared Git repository is not its exact worktree root: {repository}"]
        resolved = subprocess.run(
            ["git", "-C", str(target), "rev-parse", "--verify", f"{revision}^{{commit}}"],
            check=False,
            text=True,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "invalid", [f"Git commit readback failed: {exc}"]
    if resolved.returncode != 0:
        return "invalid", ["Git commit does not exist or is not readable"]
    if resolved.stdout.strip().lower() != revision.lower():
        return "invalid", ["Git commit readback did not resolve to the exact full SHA"]
    return "valid", []


def _verify_artifact_digest(paths: ProjectPaths, document: dict[str, Any]) -> tuple[str, list[str]]:
    locator = document["locator"]
    if locator.get("algorithm") != "sha256":
        return "invalid", ["artifact algorithm must be sha256"]
    digest = locator.get("digest")
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        return "invalid", ["artifact digest must be a full sha256"]
    try:
        target = _inside_project(paths.root, locator.get("path"), label="artifact path")
    except VoyageError as exc:
        return "invalid", [str(exc)]
    if not target.is_file():
        return "invalid", [f"artifact is not a file: {locator.get('path')}"]
    if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
        return "invalid", ["artifact sha256 does not match current file"]
    return "valid", []


def _counts_errors(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["command counts must be an object"]
    keys = ("total", "passed", "failed", "skipped", "unknown")
    errors: list[str] = []
    for key in keys:
        count = value.get(key)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            errors.append(f"command counts {key} must be a non-negative integer")
    if not errors and sum(value[key] for key in keys[1:]) != value["total"]:
        errors.append("command counts do not add up")
    return errors


def _verify_command_result(paths: ProjectPaths, document: dict[str, Any]) -> tuple[str, list[str]]:
    locator = document["locator"]
    errors: list[str] = []
    argv = locator.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
        errors.append("command argv must be a non-empty string array")
    try:
        cwd = _inside_project(paths.root, locator.get("cwd"), label="command cwd")
        if not cwd.is_dir():
            errors.append("command cwd is not a directory")
    except VoyageError as exc:
        errors.append(str(exc))
    exit_code = locator.get("exit_code")
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        errors.append("command exit_code must be an integer")
    errors.extend(_counts_errors(locator.get("counts")))
    errors.extend(_descriptor_errors(paths, locator.get("stdout"), label="stdout"))
    errors.extend(_descriptor_errors(paths, locator.get("stderr"), label="stderr"))
    counts = locator.get("counts")
    if not errors and document.get("claim") == "command-passed":
        if exit_code != 0 or any(counts[key] for key in ("failed", "skipped", "unknown")):
            errors.append("command-passed claim contradicts exit code or complete counts")
    return ("invalid", errors) if errors else ("valid", [])


def _verify_runtime_readback(document: dict[str, Any], now: datetime) -> tuple[str, list[str]]:
    locator = document["locator"]
    errors: list[str] = []
    for field in ("environment_id", "target_version"):
        if not isinstance(locator.get(field), str) or not locator.get(field):
            errors.append(f"runtime {field} must be non-empty")
    if not isinstance(locator.get("fields"), dict) or not locator.get("fields"):
        errors.append("runtime fields must be a non-empty object")
    max_age = locator.get("max_age_seconds")
    if not isinstance(max_age, int) or isinstance(max_age, bool) or max_age <= 0:
        errors.append("runtime max_age_seconds must be a positive integer")
    try:
        observed = parse_time(document["observed_at"])
    except (TypeError, ValueError):
        return "invalid", ["runtime observed_at is invalid"]
    if observed > now:
        errors.append("runtime observed_at is in the future")
    if errors:
        return "invalid", errors
    if (now - observed).total_seconds() > max_age:
        return "unknown", ["runtime readback has expired"]
    return "valid", []


def _verify_user_decision(state: dict[str, Any], document: dict[str, Any]) -> tuple[str, list[str]]:
    locator = document["locator"]
    required = ("decision_id", "action", "project_id")
    if any(not isinstance(locator.get(field), str) or not locator.get(field) for field in required):
        return "invalid", ["user decision locator requires decision_id, action, and project_id"]
    decision = state.get("decisions", {}).get(locator["decision_id"])
    if decision is None or decision.get("loop") != "user":
        return "invalid", ["referenced User decision does not exist"]
    if decision.get("revoked"):
        return "invalid", ["referenced User decision is revoked"]
    scope = decision.get("payload", {}).get("scope")
    if not isinstance(scope, dict):
        return "invalid", ["referenced User decision has no object scope"]
    actions = scope.get("actions")
    if not isinstance(actions, list) or locator["action"] not in actions and "*" not in actions:
        return "invalid", ["User decision does not cover requested action"]
    if scope.get("project_id") not in {locator["project_id"], "*"}:
        return "invalid", ["User decision does not cover requested project"]
    source_id = locator.get("source_id")
    if source_id is not None:
        sources = scope.get("truth_sources")
        if not isinstance(source_id, str) or not source_id or not isinstance(sources, list) or source_id not in sources and "*" not in sources:
            return "invalid", ["User decision does not cover requested source"]
    return "valid", []


def load_evidence(paths: ProjectPaths, evidence_id: str) -> dict[str, Any]:
    match = EVIDENCE_ID_PATTERN.fullmatch(evidence_id) if isinstance(evidence_id, str) else None
    if match is None:
        raise VoyageError("reference is not a typed evidence ID")
    digest = match.group(1)
    document = load_json(paths.evidence / "sha256" / f"{digest}.json")
    actual = content_hash(document)
    if actual != digest:
        raise VoyageError(f"evidence digest mismatch for {evidence_id}")
    return document


def verify_evidence(
    paths: ProjectPaths,
    evidence_id: str,
    *,
    now: datetime | None = None,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    checked_at = now or datetime.now(timezone.utc)
    if checked_at.tzinfo is None:
        raise VoyageError("evidence verification time must include timezone")
    reasons: list[str] = []
    kind: str | None = None
    try:
        document = load_evidence(paths, evidence_id)
    except VoyageError as exc:
        return {
            "evidence_id": evidence_id,
            "kind": None,
            "status": "invalid",
            "reasons": [str(exc)],
            "validator_version": EVIDENCE_VALIDATOR_VERSION,
            "verified_at": checked_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
        }
    common_errors = _evidence_common_errors(document)
    kind = document.get("kind") if isinstance(document.get("kind"), str) else None
    if common_errors:
        status, reasons = "invalid", common_errors
    elif kind == "git-commit":
        status, reasons = _verify_git_commit(paths, document)
    elif kind == "artifact-digest":
        status, reasons = _verify_artifact_digest(paths, document)
    elif kind == "command-result":
        status, reasons = _verify_command_result(paths, document)
    elif kind == "runtime-readback":
        status, reasons = _verify_runtime_readback(document, checked_at)
    elif kind == "user-decision":
        status, reasons = _verify_user_decision(state or current_state(paths), document)
    else:
        status, reasons = "invalid", [f"unsupported evidence kind: {kind}"]
    return {
        "evidence_id": evidence_id,
        "kind": kind,
        "status": status,
        "reasons": reasons,
        "validator_version": EVIDENCE_VALIDATOR_VERSION,
        "verified_at": checked_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
    }


def record_evidence(paths: ProjectPaths, document: dict[str, Any], *, actor: str) -> dict[str, Any]:
    common_errors = _evidence_common_errors(document)
    if common_errors:
        raise VoyageError("; ".join(common_errors))
    digest = content_hash(document)
    evidence_id = f"sha256:{digest}"
    target = paths.evidence / "sha256" / f"{digest}.json"
    if target.exists():
        existing = load_json(target)
        if canonical_json(existing) != canonical_json(document):
            raise VoyageError(f"content-addressed evidence collision: {evidence_id}")
    else:
        atomic_write_json(target, document)
    return record_evidence_verification(paths, evidence_id, actor=actor)


def record_evidence_verification(paths: ProjectPaths, evidence_id: str, *, actor: str) -> dict[str, Any]:
    result = verify_evidence(paths, evidence_id)
    append_event(
        paths,
        actor=actor,
        loop="system",
        event_type="evidence.verified",
        subject=evidence_id,
        risk="standard",
        payload={
            "validator_version": result["validator_version"],
            "verified_at": result["verified_at"],
            "status": result["status"],
            "reasons": result["reasons"],
            "kind": result["kind"],
        },
    )
    return result


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError as exc:
        raise VoyageError(f"missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise VoyageError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise VoyageError(f"expected JSON object in {path}")
    return value


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def project_paths(root: str | Path) -> ProjectPaths:
    base = Path(root).expanduser().resolve()
    manifest_path = base / ".voyage" / "manifest.json"
    manifest = load_json(manifest_path)

    def resolve(key: str) -> Path:
        value = manifest.get(key)
        if not isinstance(value, str) or not value:
            raise VoyageError(f"manifest field {key!r} must be a non-empty path")
        path = (base / value).resolve()
        try:
            path.relative_to(base)
        except ValueError as exc:
            raise VoyageError(f"manifest path escapes project root: {key}={value}") from exc
        return path

    return ProjectPaths(
        root=base,
        control=base / ".voyage",
        manifest=manifest_path,
        truth_registry=resolve("truth_registry"),
        graph=resolve("graph"),
        resources=resolve("resources"),
        gates=resolve("gates"),
        ledger=resolve("ledger"),
        evidence=resolve("evidence"),
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def initialize_project(root: str | Path, project_id: str, truth_registry_path: str | None = None) -> ProjectPaths:
    base = Path(root).expanduser().resolve()
    control = base / ".voyage"
    if (control / "manifest.json").exists():
        raise VoyageError(f"project is already initialized: {base}")
    if not project_id or any(char.isspace() for char in project_id):
        raise VoyageError("project ID must be non-empty and contain no whitespace")

    registry_relative = truth_registry_path or "docs/voyage/truth-registry.json"
    registry_target = (base / registry_relative).resolve()
    try:
        registry_target.relative_to(base)
    except ValueError as exc:
        raise VoyageError("truth registry must stay inside the project root") from exc
    if truth_registry_path and not registry_target.is_file():
        raise VoyageError(f"existing truth registry not found: {registry_relative}")
    if truth_registry_path:
        adopted_registry = load_json(registry_target)
        if adopted_registry.get("schema_version") != SCHEMA_VERSION:
            raise VoyageError(f"unsupported adopted truth registry schema: {adopted_registry.get('schema_version')}")
        if adopted_registry.get("project") != project_id:
            raise VoyageError(
                f"adopted truth registry project {adopted_registry.get('project')!r} does not match project ID {project_id!r}"
            )
        if not isinstance(adopted_registry.get("sources"), list):
            raise VoyageError("adopted truth registry sources must be an array")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "project_stage": "bootstrap",
        "coordination_boundary": "single-repository-single-machine",
        "truth_registry": registry_relative,
        "graph": ".voyage/graph.json",
        "resources": ".voyage/resources.json",
        "gates": ".voyage/gates.json",
        "ledger": ".voyage/ledger/events.jsonl",
        "evidence": ".voyage/evidence",
    }
    graph = {
        "schema_version": SCHEMA_VERSION,
        "node_types": list(KERNEL_NODE_TYPES),
        "edge_types": list(KERNEL_EDGE_TYPES),
        "loops": list(KERNEL_LOOPS),
    }
    resources = {"schema_version": SCHEMA_VERSION, "resources": []}
    gates = {
        "schema_version": SCHEMA_VERSION,
        "gates": [
            {
                "id": "independent-quality",
                "mandatory": True,
                "allow_skips": False,
                "required_loop": "quality",
            }
        ],
    }

    atomic_write_json(control / "manifest.json", manifest)
    atomic_write_json(control / "graph.json", graph)
    atomic_write_json(control / "resources.json", resources)
    atomic_write_json(control / "gates.json", gates)
    if not truth_registry_path:
        truth_registry = {
            "schema_version": SCHEMA_VERSION,
            "project": project_id,
            "sources": [
                {"id": "product", "domain": "product", "path": "docs/voyage/product.md", "version": "1", "status": "draft", "authority": "bootstrap-draft"},
                {"id": "governance", "domain": "governance", "path": "docs/voyage/governance.md", "version": "1", "status": "draft", "authority": "bootstrap-draft"},
                {"id": "system", "domain": "system", "path": "docs/voyage/system.md", "version": "1", "status": "draft", "authority": "bootstrap-draft"},
                {"id": "operations", "domain": "operations", "path": "docs/voyage/operations.md", "version": "1", "status": "draft", "authority": "bootstrap-draft"},
            ],
            "non_authoritative": ["docs/research/", "conversation memory", "worker summaries"],
        }
        atomic_write_json(registry_target, truth_registry)
        contract_bodies = {
            "product.md": (
                "# Product contract\n\n- Status: draft\n- Version: 1\n\n"
                "## Goals\n\nTODO: define the outcomes this project must produce.\n\n"
                "## Non-goals\n\nTODO: define what this project must not attempt.\n\n"
                "## Acceptance boundary\n\nTODO: define the evidence required for User acceptance.\n"
            ),
            "governance.md": (
                "# Governance contract\n\n- Status: draft\n- Version: 1\n\n"
                "## User authority\n\nTODO: define decisions reserved for User.\n\n"
                "## Loop authority\n\nTODO: define execution, quality, governance, and audit boundaries.\n\n"
                "## Risk boundary\n\nTODO: define escalation and irreversible-action policy.\n"
            ),
            "system.md": (
                "# System contract\n\n- Status: draft\n- Version: 1\n\n"
                "## Sources of truth\n\nTODO: define project truth and external anchors.\n\n"
                "## Mandatory gates\n\nTODO: define gates that fast loops cannot weaken.\n\n"
                "## Runtime boundary\n\nTODO: define state, resource, and environment boundaries.\n"
            ),
            "operations.md": (
                "# Operations runbook\n\n- Status: draft\n- Version: 1\n\n"
                "## Recovery\n\nTODO: define cold-start recovery steps.\n\n"
                "## Validation\n\nTODO: define required validation and readback.\n\n"
                "## Escalation\n\nTODO: define stop and User escalation conditions.\n"
            ),
        }
        for filename, body in contract_bodies.items():
            _write_text(
                base / "docs" / "voyage" / filename,
                body,
            )
    (control / "ledger").mkdir(parents=True, exist_ok=True)
    (control / "ledger" / "events.jsonl").touch(exist_ok=False)
    (control / "evidence").mkdir(parents=True, exist_ok=True)
    _write_text(control / "evidence" / ".gitkeep", "")
    paths = project_paths(base)
    append_event(
        paths,
        actor="voyage-system",
        loop="system",
        event_type="project.initialized",
        subject=project_id,
        risk="standard",
        payload={"schema_version": SCHEMA_VERSION, "project_stage": "bootstrap", "extension_mode": "explicit"},
    )
    return paths


def load_events(ledger: Path) -> list[dict[str, Any]]:
    if not ledger.exists():
        raise VoyageError(f"missing ledger: {ledger}")
    events: list[dict[str, Any]] = []
    with ledger.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise VoyageError(f"invalid ledger JSON at line {line_number}: {exc}") from exc
            if not isinstance(event, dict):
                raise VoyageError(f"ledger line {line_number} is not an object")
            events.append(event)
    return events


@contextmanager
def ledger_lock(ledger: Path) -> Iterator[None]:
    lock_path = ledger.with_suffix(ledger.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def make_event(
    previous_hash: str | None,
    *,
    actor: str,
    loop: str,
    event_type: str,
    subject: str,
    risk: str,
    payload: dict[str, Any] | None = None,
    evidence: list[str] | None = None,
    anchor: str | None = None,
    authorization: str | None = None,
    caused_by: str | None = None,
) -> dict[str, Any]:
    if loop not in LOOPS:
        raise VoyageError(f"invalid loop: {loop}")
    if risk not in RISK_LEVELS:
        raise VoyageError(f"invalid risk: {risk}")
    if event_type not in SUPPORTED_EVENT_TYPES:
        raise VoyageError(f"unsupported event type: {event_type}")
    if not actor or not event_type or not subject:
        raise VoyageError("actor, event type, and subject are required")
    event = {
        "schema_version": SCHEMA_VERSION,
        "event_id": f"evt-{uuid.uuid4().hex}",
        "timestamp": utc_now(),
        "actor": actor,
        "loop": loop,
        "type": event_type,
        "subject": subject,
        "risk": risk,
        "caused_by": caused_by,
        "payload": payload or {},
        "evidence": evidence or [],
        "anchor": anchor,
        "authorization": authorization,
        "prev_hash": previous_hash,
    }
    event["hash"] = content_hash(event)
    return event


def validate_hash_chain(events: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    previous: str | None = None
    seen: set[str] = set()
    required = {
        "schema_version", "event_id", "timestamp", "actor", "loop", "type",
        "subject", "risk", "payload", "evidence", "prev_hash", "hash",
    }
    for index, event in enumerate(events, 1):
        missing = required - event.keys()
        if missing:
            errors.append(f"event {index} missing fields: {', '.join(sorted(missing))}")
            continue
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            errors.append(f"event {index} event_id is not a non-empty string")
        elif event_id in seen:
            errors.append(f"event {index} repeats event ID {event_id}")
        else:
            seen.add(event_id)
        if event.get("prev_hash") != previous:
            errors.append(f"event {index} prev_hash does not match ledger head")
        claimed = event.get("hash")
        body = {key: value for key, value in event.items() if key != "hash"}
        actual = content_hash(body)
        if claimed != actual:
            errors.append(f"event {index} hash mismatch")
        if event.get("loop") not in LOOPS:
            errors.append(f"event {index} has invalid loop {event.get('loop')}")
        if event.get("risk") not in RISK_LEVELS:
            errors.append(f"event {index} has invalid risk {event.get('risk')}")
        if event.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"event {index} has unsupported schema {event.get('schema_version')}")
        for key in ("actor", "type", "subject"):
            if not isinstance(event.get(key), str) or not event.get(key):
                errors.append(f"event {index} {key} is not a non-empty string")
        timestamp = event.get("timestamp")
        try:
            parse_time(timestamp)
        except (TypeError, ValueError):
            errors.append(f"event {index} timestamp is not a valid date-time")
        if not isinstance(event.get("payload"), dict):
            errors.append(f"event {index} payload is not an object")
        if not isinstance(event.get("evidence"), list) or not all(isinstance(item, str) for item in event.get("evidence", [])):
            errors.append(f"event {index} evidence is not a string array")
        previous = claimed
    return errors


def _duplicates(items: list[Any]) -> list[Any]:
    result: list[Any] = []
    for index, item in enumerate(items):
        if item in items[:index] and item not in result:
            result.append(item)
    return result


def _validate_graph_definition(graph: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in ("node_types", "edge_types", "loops"):
        items = graph.get(key)
        if not isinstance(items, list) or not items:
            errors.append(f"$.{key}: must be a non-empty array")
            continue
        duplicates = _duplicates(items)
        if duplicates:
            errors.append(f"$.{key}: uniqueItems contains duplicates {duplicates!r}")
    loops = graph.get("loops")
    if isinstance(loops, list):
        for required_loop in ("execution", "quality", "governance", "audit"):
            if required_loop not in loops:
                errors.append(f"$.loops: contains requires {required_loop!r}")
        invalid = [item for item in loops if item not in {"execution", "quality", "governance", "audit"}]
        if invalid:
            errors.append(f"$.loops: values are not in enum {invalid!r}")
    return errors


def _validate_gate_definition_data(gates: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    definitions = gates.get("gates")
    if not isinstance(definitions, list):
        return ["$.gates: must be an array"]
    seen: set[str] = set()
    required = {
        "id": str,
        "mandatory": bool,
        "allow_skips": bool,
        "required_loop": str,
    }
    for index, definition in enumerate(definitions):
        path = f"$.gates[{index}]"
        if not isinstance(definition, dict):
            errors.append(f"{path}: must be an object")
            continue
        for key, expected_type in required.items():
            if key not in definition:
                errors.append(f"{path}.{key}: required property is missing")
            elif not isinstance(definition[key], expected_type):
                errors.append(f"{path}.{key}: has invalid type")
        gate_id = definition.get("id")
        if isinstance(gate_id, str):
            if gate_id in seen:
                errors.append(f"{path}.id: duplicate gate ID {gate_id}")
            seen.add(gate_id)
        if definition.get("required_loop") != "quality":
            errors.append(f"{path}.required_loop: value is not in enum ['quality']")
        for field, allowed in (("risk_modes", set(RISK_MODE_ORDER)), ("risk_domains", set(STRICT_RISK_DOMAINS))):
            if field not in definition:
                continue
            values = definition[field]
            if not isinstance(values, list):
                errors.append(f"{path}.{field}: must be an array")
                continue
            if len(values) != len(set(values)):
                errors.append(f"{path}.{field}: uniqueItems contains duplicates")
            invalid = [value for value in values if not isinstance(value, str) or value not in allowed]
            if invalid:
                errors.append(f"{path}.{field}: values are not in enum {invalid!r}")
    return errors


def _validate_event_data(events: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for index, event in enumerate(events, 1):
        if not isinstance(event, dict) or not isinstance(event.get("payload"), dict):
            continue
        if event.get("type") == "resource.claimed":
            payload = event["payload"]
            for key in ("resource_id", "lease_id", "work_id", "expires_at"):
                if not isinstance(payload.get(key), str) or not payload.get(key):
                    errors.append(f"event {index} $.payload.{key}: required non-empty string is missing")
            expires_at = payload.get("expires_at")
            if isinstance(expires_at, str) and expires_at:
                try:
                    parse_time(expires_at)
                except (TypeError, ValueError):
                    errors.append(f"event {index} $.payload.expires_at: value is not a valid date-time")
            if event.get("subject") != payload.get("resource_id"):
                errors.append(f"event {index} subject must match $.payload.resource_id")
        if event.get("type") in {"resource.released", "resource.recovered"}:
            payload = event["payload"]
            for key in ("resource_id", "lease_id"):
                if not isinstance(payload.get(key), str) or not payload.get(key):
                    errors.append(f"event {index} $.payload.{key}: required non-empty string is missing")
            if event.get("subject") != payload.get("resource_id"):
                errors.append(f"event {index} subject must match $.payload.resource_id")
    return errors


def _initial_state() -> dict[str, Any]:
    return {
        "project_id": None,
        "project_stage": "legacy-bootstrap",
        "extension_mode": "legacy-compatible",
        "extensions": {},
        "truth_activations": {},
        "works": {},
        "leases": {},
        "rules": {},
        "gates": {},
        "blocks": {},
        "decisions": {},
        "observations": [],
        "last_event": None,
    }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VoyageError(message)


def _validated_counts(value: Any, *, context: str) -> dict[str, int]:
    _require(isinstance(value, dict), f"{context} result requires counts")
    keys = ("total", "passed", "failed", "skipped", "unknown")
    for key in keys:
        count = value.get(key)
        _require(type(count) is int and count >= 0, f"{context} count {key} must be a non-negative integer")
    counts = {key: value[key] for key in keys}
    _require(counts["total"] > 0, f"{context} total must be positive")
    _require(
        counts["passed"] + counts["failed"] + counts["skipped"] + counts["unknown"] == counts["total"],
        f"{context} counts do not add up",
    )
    return counts


def _require_decision_scope(
    state: dict[str, Any],
    decision_id: Any,
    *,
    action: str,
    project_id: str,
    source_id: str | None = None,
) -> dict[str, Any]:
    decision = state["decisions"].get(decision_id)
    _require(decision is not None and decision.get("loop") == "user", "operation must reference a recorded User decision")
    _require(not decision.get("revoked"), "referenced User decision is revoked")
    scope = decision.get("payload", {}).get("scope")
    _require(isinstance(scope, dict), "User decision requires an object scope")
    actions = scope.get("actions")
    _require(
        isinstance(actions, list) and (action in actions or "*" in actions),
        f"User decision does not cover action {action}",
    )
    covered_project = scope.get("project_id")
    _require(covered_project in {project_id, "*"}, f"User decision does not cover project {project_id}")
    if source_id is not None:
        sources = scope.get("truth_sources")
        _require(
            isinstance(sources, list) and (source_id in sources or "*" in sources),
            f"User decision does not cover truth source {source_id}",
        )
    return decision


def _require_extension_decision_scope(
    state: dict[str, Any],
    decision_id: Any,
    *,
    action: str,
    project_id: str,
    extension_id: str,
    version: str,
) -> dict[str, Any]:
    decision = state["decisions"].get(decision_id)
    _require(decision is not None, f"extension {action} requires a recorded User decision")
    _require(not decision.get("revoked"), f"extension {action} decision is revoked")
    _require(decision.get("loop") == "user", f"extension {action} requires User-loop authority")
    scope = decision.get("payload", {}).get("scope")
    _require(isinstance(scope, dict), f"extension {action} decision requires object scope")
    actions = scope.get("actions")
    _require(isinstance(actions, list) and action in actions, f"extension decision does not cover action {action}")
    _require(scope.get("project_id") == project_id, "extension decision does not cover this project")
    extensions = scope.get("extensions")
    _require(isinstance(extensions, list) and extension_id in extensions, "extension decision does not cover this extension")
    versions = scope.get("extension_versions")
    _require(isinstance(versions, dict) and versions.get(extension_id) == version, "extension decision does not cover this version")
    return decision


def _require_work_action_decision_scope(
    state: dict[str, Any],
    decision_id: Any,
    *,
    action: str,
    work_id: str,
    resource_id: str | None = None,
) -> dict[str, Any]:
    decision = state["decisions"].get(decision_id)
    _require(decision is not None, f"strict {action} requires a recorded User decision")
    _require(not decision.get("revoked"), f"strict {action} decision is revoked")
    _require(decision.get("loop") == "user", f"strict {action} requires User-loop authority")
    scope = decision.get("payload", {}).get("scope")
    _require(isinstance(scope, dict), f"strict {action} decision requires object scope")
    actions = scope.get("actions")
    _require(isinstance(actions, list) and action in actions, f"User decision does not cover action {action}")
    _require(scope.get("project_id") == state["project_id"], "User decision does not cover this project")
    works = scope.get("works")
    _require(isinstance(works, list) and work_id in works, "User decision does not cover this work")
    if resource_id is not None:
        resources = scope.get("resources")
        _require(isinstance(resources, list) and resource_id in resources, "User decision does not cover this resource")
    return decision


def _work(state: dict[str, Any], work_id: str) -> dict[str, Any]:
    work = state["works"].get(work_id)
    if work is None:
        raise VoyageError(f"unknown work item: {work_id}")
    return work


def _required_gate_definitions(work: dict[str, Any], gate_defs: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    domains = set((work.get("risk_assessment") or {}).get("domains", []))
    required: dict[str, dict[str, Any]] = {}
    for gate_id, definition in gate_defs.items():
        if definition.get("mandatory") is True:
            required[gate_id] = definition
            continue
        modes = definition.get("risk_modes", [])
        if isinstance(modes, list) and work["risk"] in modes:
            required[gate_id] = definition
            continue
        risk_domains = definition.get("risk_domains", [])
        if work["risk"] == "strict" and isinstance(risk_domains, list) and domains.intersection(risk_domains):
            required[gate_id] = definition
    return required


def _gate_definitions(gates: dict[str, Any]) -> dict[str, dict[str, Any]]:
    definitions = gates.get("gates", [])
    if not isinstance(definitions, list):
        raise VoyageError("gates file must contain a gates array")
    result: dict[str, dict[str, Any]] = {}
    for definition in definitions:
        if not isinstance(definition, dict) or not isinstance(definition.get("id"), str):
            raise VoyageError("every gate definition requires an ID")
        if definition["id"] in result:
            raise VoyageError(f"duplicate gate ID: {definition['id']}")
        result[definition["id"]] = definition
    return result


def replay_events(
    events: list[dict[str, Any]],
    *,
    resources: dict[str, Any] | None = None,
    gates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = _initial_state()
    resource_defs = {
        item["id"]: item
        for item in (resources or {}).get("resources", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    gate_defs = _gate_definitions(gates or {"gates": []})

    for event in events:
        event_type = event["type"]
        subject = event["subject"]
        actor = event["actor"]
        loop = event["loop"]
        payload = event.get("payload") or {}
        anchor = event.get("anchor")
        evidence = event.get("evidence") or []

        required_extension = EXTENSION_EVENT_REQUIREMENTS.get(event_type)
        if required_extension and state["extension_mode"] == "explicit":
            extension = state["extensions"].get(required_extension)
            _require(
                extension is not None and extension.get("status") == "enabled",
                f"extension {required_extension} is not enabled for event {event_type}",
            )

        if event_type == "project.initialized":
            _require(loop == "system", "project initialization requires system loop")
            stage = payload.get("project_stage", "legacy-bootstrap")
            _require(stage in {"bootstrap", "legacy-bootstrap"}, f"invalid initial project stage: {stage}")
            state["project_stage"] = stage
            state["project_id"] = subject
            extension_mode = payload.get("extension_mode", "legacy-compatible")
            _require(extension_mode in {"explicit", "legacy-compatible"}, "invalid extension mode")
            state["extension_mode"] = extension_mode

        elif event_type == "extension.enabled":
            _require(loop == "governance", "extension enable requires governance loop")
            extension_id = payload.get("extension_id")
            version = payload.get("version")
            contract = EXTENSION_CATALOG.get(extension_id)
            _require(contract is not None, f"unknown extension: {extension_id}")
            _require(contract["availability"] == "available", f"extension is reserved: {extension_id}")
            _require(subject == extension_id, "extension enable subject must match extension_id")
            _require(version == contract["version"], f"extension version mismatch: {version}")
            _require(payload.get("contract") == extension_catalog_view()[extension_id], "extension enable contract snapshot mismatch")
            _require_extension_decision_scope(
                state,
                event.get("authorization"),
                action="extension.enable",
                project_id=state["project_id"],
                extension_id=extension_id,
                version=version,
            )
            previous = state["extensions"].get(extension_id)
            _require(previous is None or previous.get("status") != "enabled", f"extension already enabled: {extension_id}")
            history = list(previous.get("history", [])) if previous else []
            history.append({
                "type": event_type,
                "event_id": event["event_id"],
                "decision_id": event.get("authorization"),
                "version": version,
            })
            state["extension_mode"] = "explicit"
            state["extensions"][extension_id] = {
                "status": "enabled",
                "version": version,
                "enabled_event": event["event_id"],
                "enabled_decision": event.get("authorization"),
                "disabled_event": None,
                "disabled_decision": None,
                "history": history,
            }

        elif event_type == "extension.disabled":
            _require(loop == "governance", "extension disable requires governance loop")
            extension_id = payload.get("extension_id")
            version = payload.get("version")
            contract = EXTENSION_CATALOG.get(extension_id)
            _require(contract is not None, f"unknown extension: {extension_id}")
            _require(subject == extension_id, "extension disable subject must match extension_id")
            _require(version == contract["version"], f"extension version mismatch: {version}")
            _require_extension_decision_scope(
                state,
                event.get("authorization"),
                action="extension.disable",
                project_id=state["project_id"],
                extension_id=extension_id,
                version=version,
            )
            previous = state["extensions"].get(extension_id)
            _require(previous is not None and previous.get("status") == "enabled", f"extension is not enabled: {extension_id}")
            _require(previous.get("version") == version, f"enabled extension version mismatch: {extension_id}")
            history = list(previous["history"])
            history.append({
                "type": event_type,
                "event_id": event["event_id"],
                "decision_id": event.get("authorization"),
                "version": version,
            })
            previous.update(
                status="disabled",
                disabled_event=event["event_id"],
                disabled_decision=event.get("authorization"),
                history=history,
            )

        elif event_type == "truth.activated":
            _require(loop == "governance", "truth activation requires governance loop")
            source_id = payload.get("source_id")
            domain = payload.get("domain")
            path = payload.get("path")
            _require(isinstance(source_id, str) and source_id, "truth activation requires source_id")
            _require(isinstance(domain, str) and domain, "truth activation requires domain")
            _require(isinstance(path, str) and path, "truth activation requires path")
            _require(source_id not in state["truth_activations"], f"truth source {source_id} already has activation evidence")
            decision_id = event.get("authorization")
            _require_decision_scope(
                state,
                decision_id,
                action="truth.activate",
                project_id=payload.get("project_id"),
                source_id=source_id,
            )
            state["truth_activations"][source_id] = {
                "event_id": event["event_id"],
                "decision_id": decision_id,
                "domain": domain,
                "path": path,
                "supersedes": payload.get("supersedes"),
            }
            verified_domains = {item["domain"] for item in state["truth_activations"].values()}
            if set(REQUIRED_TRUTH_DOMAINS).issubset(verified_domains):
                state["project_stage"] = "operational"

        elif event_type == "project.migrated":
            _require(loop == "governance", "legacy migration requires governance loop")
            _require(state["project_stage"] == "legacy-bootstrap", "project migration is only for v0.1 legacy projects")
            project_id = payload.get("project_id")
            _require(project_id == state["project_id"], "legacy migration project does not match initialized project")
            _require_decision_scope(
                state,
                event.get("authorization"),
                action="truth.migrate",
                project_id=project_id,
            )
            sources = payload.get("sources")
            _require(isinstance(sources, list), "legacy migration requires active truth sources")
            active_domains = {
                item.get("domain") for item in sources
                if isinstance(item, dict) and isinstance(item.get("id"), str) and isinstance(item.get("path"), str)
            }
            _require(set(REQUIRED_TRUTH_DOMAINS).issubset(active_domains), "legacy migration requires four active required domains")
            for item in sources:
                state["truth_activations"][item["id"]] = {
                    "event_id": event["event_id"],
                    "decision_id": event.get("authorization"),
                    "domain": item["domain"],
                    "path": item["path"],
                    "migration": True,
                }
            state["project_stage"] = "operational"

        elif event_type == "evidence.verified":
            _require(loop == "system", "evidence verification requires system loop")
            _require(EVIDENCE_ID_PATTERN.fullmatch(subject) is not None, "evidence verification requires typed evidence ID")
            _require(payload.get("validator_version") == EVIDENCE_VALIDATOR_VERSION, "unsupported evidence validator version")
            _require(payload.get("status") in {"valid", "invalid", "unknown"}, "invalid evidence verification status")
            _require(isinstance(payload.get("reasons"), list), "evidence verification reasons must be an array")
            _require(isinstance(payload.get("verified_at"), str), "evidence verification requires verified_at")
            try:
                parse_time(payload["verified_at"])
            except (TypeError, ValueError) as exc:
                raise VoyageError("evidence verification verified_at is invalid") from exc
            state["observations"].append(event)

        elif event_type == "decision.revoked":
            _require(loop == "user", "decision revocation requires User loop")
            decision = state["decisions"].get(subject)
            _require(decision is not None, f"decision does not exist: {subject}")
            _require(not decision.get("revoked"), f"decision already revoked: {subject}")
            _require(payload.get("reason"), "decision revocation requires reason")
            decision["revoked"] = True
            decision["revoked_event"] = event["event_id"]

        elif event_type == "work.created":
            _require(loop == "governance", "work creation requires governance loop")
            _require(subject not in state["works"], f"work already exists: {subject}")
            _require(payload.get("title"), "work creation requires title")
            _require(payload.get("scope"), "work creation requires scope")
            _require(payload.get("acceptance"), "work creation requires acceptance criteria")
            dependencies = payload.get("dependencies", [])
            _require(isinstance(dependencies, list) and all(isinstance(item, str) for item in dependencies), "work dependencies must be a string array")
            dangling = [item for item in dependencies if item not in state["works"] and not item.startswith("external:")]
            _require(not dangling, f"work has unknown internal dependencies: {', '.join(dangling)}")
            unknown_resources = set(payload.get("required_resources", [])) - set(resource_defs)
            _require(not unknown_resources, f"work requires unknown resources: {', '.join(sorted(unknown_resources))}")
            assessment = payload.get("risk_assessment")
            if assessment is not None:
                _require(isinstance(assessment, dict), "risk_assessment must be an object")
                _require(assessment.get("version") == RISK_POLICY_VERSION, "work risk policy version mismatch")
                _require(assessment.get("requested") in RISK_LEVELS, "work requested risk is invalid")
                _require(assessment.get("effective") == event["risk"], "work effective risk must match event risk")
                _require(isinstance(assessment.get("domains"), list), "work risk domains must be an array")
                _require(isinstance(assessment.get("reasons"), list), "work risk reasons must be an array")
            state["works"][subject] = {
                "id": subject,
                "title": payload["title"],
                "scope": payload["scope"],
                "acceptance": payload["acceptance"],
                "non_goals": payload.get("non_goals", []),
                "dependencies": dependencies,
                "required_resources": payload.get("required_resources", []),
                "declared_risk": assessment.get("requested") if assessment else event["risk"],
                "risk": event["risk"],
                "risk_policy_version": assessment.get("version") if assessment else None,
                "risk_assessment": deepcopy(assessment) if assessment else None,
                "status": "draft",
                "delivery": None,
                "quality_actor": None,
                "audit_checkpoint": None,
                "previous_status": None,
            }

        elif event_type == "work.authorized":
            _require(loop == "governance", "work authorization requires governance loop")
            _require(state["project_stage"] == "operational", "bootstrap project must become operational before work authorization")
            work = _work(state, subject)
            _require(work["status"] == "draft", f"work {subject} is not draft")
            if work["risk"] == "strict":
                _require(bool(event.get("authorization")), "strict work requires User authorization")
                if work.get("risk_policy_version") == RISK_POLICY_VERSION:
                    _require_work_action_decision_scope(
                        state, event.get("authorization"), action="work.authorize", work_id=subject,
                    )
                else:
                    decision = state["decisions"].get(event["authorization"])
                    _require(decision is not None, "strict work authorization must reference a recorded User decision")
                    _require(not decision.get("revoked"), "strict work authorization references a revoked User decision")
            work["authorization"] = event.get("authorization")
            work["status"] = "authorized"

        elif event_type == "work.started":
            _require(loop == "execution", "work start requires execution loop")
            work = _work(state, subject)
            _require(work["status"] in {"authorized", "rejected"}, f"work {subject} cannot start from {work['status']}")
            if work.get("risk_policy_version") == RISK_POLICY_VERSION and work["risk"] == "strict":
                _require_work_action_decision_scope(
                    state, event.get("authorization"), action="work.start", work_id=subject,
                )
                _require(bool(evidence), "strict work start requires fresh runtime readback evidence")
            held_resources = {
                lease["resource_id"]
                for lease in state["leases"].values()
                if lease["active"] and lease["work_id"] == subject and lease["holder"] == actor
            }
            missing_resources = set(work["required_resources"]) - held_resources
            _require(not missing_resources, f"work {subject} has unclaimed resources: {', '.join(sorted(missing_resources))}")
            work["status"] = "active"
            work["executor"] = actor
            if work.get("risk_policy_version") == RISK_POLICY_VERSION and work["risk"] == "strict":
                work["start_authorization"] = event.get("authorization")
                work["pre_readback"] = evidence[0]

        elif event_type == "work.delivered":
            _require(loop == "execution", "delivery requires execution loop")
            work = _work(state, subject)
            _require(work["status"] == "active", f"work {subject} is not active")
            active_resources = {
                lease["resource_id"]
                for lease in state["leases"].values()
                if lease["active"] and lease["work_id"] == subject and lease["holder"] == actor
            }
            missing_resources = set(work["required_resources"]) - active_resources
            _require(not missing_resources, f"delivery lost required resources: {', '.join(sorted(missing_resources))}")
            _require(bool(anchor), "delivery requires immutable anchor")
            _require(bool(evidence), "delivery requires evidence")
            attempt = 1 + (work["delivery"]["attempt"] if work["delivery"] else 0)
            work["delivery"] = {"anchor": anchor, "evidence": list(evidence), "actor": actor, "attempt": attempt, "event_id": event["event_id"]}
            work["quality_actor"] = None
            work["audit_checkpoint"] = None
            work["status"] = "delivered"
            state["gates"].setdefault(subject, {}).pop("independent-quality", None)

        elif event_type in {"quality.passed", "quality.rejected"}:
            _require(loop == "quality", "quality verdict requires quality loop")
            work = _work(state, subject)
            _require(work["status"] == "delivered", f"work {subject} is not awaiting quality")
            _require(work["delivery"] is not None, "quality verdict requires delivery")
            _require(anchor == work["delivery"]["anchor"], "quality anchor does not match current delivery")
            _require(actor != work["delivery"]["actor"], "executor cannot issue final quality verdict")
            _require(bool(evidence), "quality verdict requires evidence")
            work["quality_actor"] = actor
            verdict = "pass" if event_type == "quality.passed" else "reject"
            counts = _validated_counts(payload.get("counts"), context="quality")
            if verdict == "pass":
                _require(
                    counts["failed"] == 0 and counts["skipped"] == 0 and counts["unknown"] == 0,
                    "passing independent quality cannot contain failed, skipped, or unknown checks",
                )
            else:
                _require(
                    counts["failed"] > 0 or counts["unknown"] > 0,
                    "rejected quality requires failed or unknown checks",
                )
            state["gates"].setdefault(subject, {})["independent-quality"] = {
                "verdict": verdict,
                "anchor": anchor,
                "evidence": list(evidence),
                "actor": actor,
                "counts": counts,
            }
            work["status"] = "quality-passed" if verdict == "pass" else "rejected"

        elif event_type == "audit.checked":
            _require(loop == "audit", "audit checkpoint requires audit loop")
            work = _work(state, subject)
            _require(work["status"] in {"delivered", "quality-passed"}, f"work {subject} is not ready for audit checkpoint")
            _require(work.get("delivery") is not None, "audit checkpoint requires current delivery")
            _require(anchor == work["delivery"]["anchor"], "audit checkpoint anchor does not match current delivery")
            _require(actor != work["delivery"]["actor"], "executor cannot issue its own audit checkpoint")
            _require(bool(evidence), "audit checkpoint requires evidence")
            counts = _validated_counts(payload.get("counts"), context="audit checkpoint")
            _require(
                counts["failed"] == 0 and counts["skipped"] == 0 and counts["unknown"] == 0,
                "passing audit checkpoint cannot contain failed, skipped, or unknown checks",
            )
            work["audit_checkpoint"] = {
                "event_id": event["event_id"],
                "anchor": anchor,
                "actor": actor,
                "evidence": list(evidence),
                "counts": counts,
            }

        elif event_type == "gate.recorded":
            _require(loop == "quality", "gate recording requires quality loop")
            work = _work(state, subject)
            gate_id = payload.get("gate_id")
            _require(gate_id in gate_defs, f"unknown gate: {gate_id}")
            _require(anchor and work.get("delivery") and anchor == work["delivery"]["anchor"], "gate anchor does not match current delivery")
            _require(bool(evidence), "gate result requires evidence")
            required_loop = gate_defs[gate_id].get("required_loop", "quality")
            _require(loop == required_loop, f"gate {gate_id} requires {required_loop} loop")
            counts = _validated_counts(payload.get("counts"), context="gate")
            verdict = "pass" if counts["failed"] == 0 and counts["unknown"] == 0 and (gate_defs[gate_id].get("allow_skips", False) or counts["skipped"] == 0) else "fail"
            state["gates"].setdefault(subject, {})[gate_id] = {"verdict": verdict, "anchor": anchor, "evidence": list(evidence), "actor": actor, "counts": counts}

        elif event_type == "work.accepted":
            _require(loop == "governance", "work acceptance requires governance loop")
            work = _work(state, subject)
            _require(work["status"] == "quality-passed", f"work {subject} has not passed quality")
            assessment = work.get("risk_assessment") or {}
            requires_post_readback = (
                work.get("risk_policy_version") == RISK_POLICY_VERSION
                and (work["risk"] == "strict" or assessment.get("environment_change") is True)
            )
            if requires_post_readback:
                _require(bool(evidence), "work acceptance requires fresh runtime readback evidence")
                if work["risk"] == "strict":
                    _require(evidence[0] != work.get("pre_readback"), "strict post-action runtime readback must be separate from pre-action readback")
            current_anchor = work["delivery"]["anchor"]
            if work.get("risk_policy_version") == RISK_POLICY_VERSION and work["risk"] == "strict":
                checkpoint = work.get("audit_checkpoint")
                _require(checkpoint is not None, "strict work acceptance requires audit checkpoint")
                _require(checkpoint.get("anchor") == current_anchor, "strict audit checkpoint targets stale anchor")
            work_gates = state["gates"].get(subject, {})
            for gate_id, definition in _required_gate_definitions(work, gate_defs).items():
                result = work_gates.get(gate_id)
                gate_kind = "mandatory" if definition.get("mandatory") else "required"
                _require(result is not None, f"{gate_kind} gate missing: {gate_id}")
                _require(result["anchor"] == current_anchor, f"{gate_kind} gate {gate_id} targets stale anchor")
                _require(result["verdict"] == "pass", f"{gate_kind} gate failed: {gate_id}")
            work["status"] = "accepted"
            if requires_post_readback:
                work["post_readback"] = evidence[0]

        elif event_type == "work.closed":
            _require(loop == "governance", "work closure requires governance loop")
            work = _work(state, subject)
            _require(work["status"] == "accepted", f"work {subject} is not accepted")
            active_work_leases = [lease["lease_id"] for lease in state["leases"].values() if lease["active"] and lease["work_id"] == subject]
            _require(not active_work_leases, f"work {subject} still holds leases: {', '.join(active_work_leases)}")
            work["status"] = "closed"

        elif event_type == "work.blocked":
            _require(loop in {"quality", "governance", "audit"}, "work block requires quality, governance, or audit loop")
            work = _work(state, subject)
            _require(work["status"] not in {"closed", "blocked"}, f"work {subject} cannot be blocked from {work['status']}")
            for key in ("reason", "scope", "unblock_condition", "appeal_to"):
                _require(payload.get(key), f"block requires {key}")
            _require(bool(evidence), "block requires evidence")
            block_id = payload.get("block_id") or f"block-{event['event_id']}"
            state["blocks"][block_id] = {
                "work_id": subject,
                "actor": actor,
                "loop": loop,
                "active": True,
                **payload,
            }
            work["previous_status"] = work["status"]
            work["status"] = "blocked"
            work["block_id"] = block_id

        elif event_type == "work.unblocked":
            _require(loop in {"governance", "audit", "user"}, "unblock requires governance, audit, or User loop")
            work = _work(state, subject)
            _require(work["status"] == "blocked", f"work {subject} is not blocked")
            block = state["blocks"].get(work.get("block_id"))
            _require(block is not None and block["active"], "active block not found")
            if block["actor"] == actor:
                _require(loop == "user", "block author cannot resolve its own block appeal")
            _require(bool(evidence), "unblock requires evidence")
            block["active"] = False
            work["status"] = work.get("previous_status") or "authorized"
            work["previous_status"] = None

        elif event_type == "work.awaiting-user":
            _require(loop in {"execution", "quality", "governance", "audit"}, "awaiting-user requires a project loop")
            work = _work(state, subject)
            _require(payload.get("decision"), "awaiting-user requires a minimal decision request")
            work["previous_status"] = work["status"]
            work["status"] = "awaiting-user"

        elif event_type == "work.user-authorized":
            _require(loop == "governance", "work resume requires governance loop")
            work = _work(state, subject)
            _require(work["status"] == "awaiting-user", f"work {subject} is not awaiting User")
            decision = event.get("authorization")
            recorded_decision = state["decisions"].get(decision)
            _require(recorded_decision is not None, "work resume must reference a recorded User decision")
            _require(not recorded_decision.get("revoked"), "work resume references a revoked User decision")
            work["authorization"] = decision
            work["status"] = work.get("previous_status") or "authorized"
            work["previous_status"] = None

        elif event_type == "resource.claimed":
            resource_id = payload.get("resource_id")
            lease_id = payload.get("lease_id")
            _require(loop == "execution", "resource claim requires execution loop")
            _require(subject == resource_id, "resource identity requires subject to match resource_id")
            _require(resource_id in resource_defs, f"unknown resource: {resource_id}")
            _require(lease_id and lease_id not in state["leases"], "resource claim requires a unique lease ID")
            _work(state, payload.get("work_id", ""))
            work = _work(state, payload["work_id"])
            definition = resource_defs[resource_id]
            if work.get("risk_policy_version") == RISK_POLICY_VERSION:
                conflict_prone = definition.get("mode") in {"exclusive", "serialized"} or definition.get("type") == "port"
                requires_probe = work["risk"] in {"standard", "strict"} or conflict_prone
                if requires_probe:
                    _require(bool(evidence), f"resource {resource_id} requires typed probe evidence")
                if work["risk"] == "strict":
                    _require_work_action_decision_scope(
                        state,
                        event.get("authorization"),
                        action="resource.claim",
                        work_id=work["id"],
                        resource_id=resource_id,
                    )
            elif definition.get("risk") == "strict" or work["risk"] == "strict":
                decision = state["decisions"].get(work.get("authorization"))
                _require(decision is not None, f"strict resource {resource_id} requires recorded User authorization")
                _require(not decision.get("revoked"), f"strict resource {resource_id} authorization is revoked")
            conflicts = definition.get("conflict_key", resource_id)
            if definition.get("mode") in {"exclusive", "serialized"}:
                for lease in state["leases"].values():
                    if lease["active"] and lease["conflict_key"] == conflicts:
                        raise VoyageError(f"resource conflict with active lease {lease['lease_id']}")
            if definition.get("type") in STATEFUL_RESOURCE_TYPES:
                _require(bool(evidence), f"stateful resource {resource_id} requires fresh probe evidence")
            state["leases"][lease_id] = {
                "lease_id": lease_id,
                "resource_id": resource_id,
                "conflict_key": conflicts,
                "holder": actor,
                "work_id": payload["work_id"],
                "expires_at": payload["expires_at"],
                "active": True,
                "stateful": definition.get("type") in STATEFUL_RESOURCE_TYPES,
                "probe_evidence": list(evidence),
            }

        elif event_type in {"resource.released", "resource.recovered"}:
            lease_id = payload.get("lease_id")
            resource_id = payload.get("resource_id")
            lease = state["leases"].get(lease_id)
            _require(lease is not None and lease["active"], f"active lease not found: {lease_id}")
            _require(
                subject == resource_id == lease["resource_id"],
                "resource identity requires subject, resource_id, and lease binding to match",
            )
            _require(actor == lease["holder"] or loop in {"governance", "audit", "user"}, "only holder or control loop can release lease")
            if event_type == "resource.recovered":
                _require(bool(evidence), "resource recovery requires probe evidence")
            lease["active"] = False
            lease["released_by"] = actor

        elif event_type == "rule.proposed":
            _require(loop == "audit", "rule proposal requires audit loop")
            _require(subject not in state["rules"], f"rule already exists: {subject}")
            for key in ("scope", "source", "cost", "verification", "retirement"):
                _require(payload.get(key), f"rule proposal requires {key}")
            state["rules"][subject] = {
                "status": "proposed",
                "proposer": actor,
                "approver": None,
                "applier": None,
                "verifier": None,
                "verification_status": None,
                "verification_event": None,
                "rollback_event": None,
            }

        elif event_type == "rule.approved":
            _require(loop in {"governance", "user"}, "rule approval requires governance or User loop")
            rule = state["rules"].get(subject)
            _require(rule and rule["status"] == "proposed", f"rule {subject} is not proposed")
            _require(actor != rule["proposer"], "rule proposer cannot approve its own proposal")
            rule.update(status="approved", approver=actor)

        elif event_type == "rule.applied":
            _require(loop == "governance", "rule application requires governance loop")
            rule = state["rules"].get(subject)
            _require(rule and rule["status"] == "approved", f"rule {subject} is not approved")
            _require(bool(evidence), "rule application requires evidence")
            rule.update(status="applied", applier=actor, verifier=None, verification_status="pending", verification_event=None)

        elif event_type == "rule.verified":
            _require(loop in {"quality", "audit"}, "rule verification requires quality or audit loop")
            rule = state["rules"].get(subject)
            _require(rule and rule["status"] == "applied", f"rule {subject} is not applied")
            _require(actor != rule["applier"], "rule applier cannot verify effectiveness")
            _require(bool(evidence), "rule verification requires evidence")
            rule.update(status="active", verifier=actor, verification_status="passed", verification_event=event["event_id"])

        elif event_type == "rule.verification-failed":
            _require(loop in {"quality", "audit"}, "rule verification failure requires quality or audit loop")
            rule = state["rules"].get(subject)
            _require(rule and rule["status"] == "applied", f"rule {subject} is not applied")
            _require(actor != rule["applier"], "rule applier cannot verify effectiveness")
            _require(bool(evidence), "rule verification failure requires evidence")
            _require(payload.get("reason"), "rule verification failure requires reason")
            rule.update(
                verifier=actor,
                verification_status="failed",
                verification_event=event["event_id"],
                verification_reason=payload["reason"],
            )

        elif event_type == "rule.rolled-back":
            _require(loop == "governance", "rule rollback requires governance loop")
            rule = state["rules"].get(subject)
            _require(
                rule and rule["status"] == "applied" and rule.get("verification_status") == "failed",
                f"rule {subject} rollback requires failed verification",
            )
            _require(bool(evidence), "rule rollback requires evidence")
            rule.update(
                status="approved",
                applier=None,
                verification_status="rolled-back",
                rollback_event=event["event_id"],
            )

        elif event_type == "rule.superseded":
            _require(loop in {"governance", "user"}, "rule supersession requires governance or User loop")
            rule = state["rules"].get(subject)
            replacement_id = payload.get("replacement")
            replacement = state["rules"].get(replacement_id)
            _require(rule and rule["status"] == "active", f"rule {subject} is not active")
            _require(replacement and replacement["status"] == "active", f"replacement rule {replacement_id} is not active")
            _require(replacement_id != subject, "rule cannot supersede itself")
            _require(bool(evidence), "rule supersession requires evidence")
            rule["status"] = "superseded"
            rule["superseded_by"] = replacement_id

        elif event_type == "rule.retired":
            _require(loop in {"governance", "user"}, "rule retirement requires governance or User loop")
            rule = state["rules"].get(subject)
            _require(rule and rule["status"] == "active", f"rule {subject} is not active")
            _require(bool(evidence), "rule retirement requires evidence")
            rule["status"] = "retired"

        elif event_type in {
            "decision.recorded", "observation.recorded", "channel.sent",
            "channel.acknowledged", "channel.started", "environment.readback",
            "audit.finding", "resource.registered",
        }:
            if event_type == "decision.recorded":
                _require(loop == "user", "decision recording requires User loop")
                _require(subject not in state["decisions"], f"decision already recorded: {subject}")
                state["decisions"][subject] = {"actor": actor, "loop": loop, "event_id": event["event_id"], "payload": payload}
            if event_type == "audit.finding":
                _require(loop == "audit", "audit finding requires audit loop")
            if event_type == "resource.registered":
                _require(loop == "governance", "resource registration requires governance loop")
            if event_type in {"observation.recorded", "environment.readback", "audit.finding"}:
                _require(bool(evidence), f"{event_type} requires evidence")
            state["observations"].append(event)

        else:
            raise VoyageError(f"unsupported event type: {event_type}")

        state["last_event"] = event["event_id"]

    return state


def _enforce_typed_transition_evidence(
    paths: ProjectPaths,
    state: dict[str, Any],
    *,
    event_type: str,
    subject: str,
    anchor: str | None,
    evidence: list[str] | None,
) -> None:
    typed_events = {"work.delivered", "quality.passed", "quality.rejected", "gate.recorded", "audit.checked"}
    if event_type in {"work.accepted", "work.closed"}:
        work = state.get("works", {}).get(subject)
        if not isinstance(work, dict) or not isinstance(work.get("delivery"), dict):
            return
        delivery = work["delivery"]
        delivery_anchor = verify_evidence(paths, delivery.get("anchor", ""), state=state)
        if delivery_anchor["status"] != "valid":
            raise VoyageError(f"current delivery anchor is {delivery_anchor['status']}: {'; '.join(delivery_anchor['reasons'])}")
        for evidence_id in delivery.get("evidence", []):
            result = verify_evidence(paths, evidence_id, state=state)
            if result["status"] != "valid":
                raise VoyageError(f"current delivery evidence {evidence_id} is {result['status']}: {'; '.join(result['reasons'])}")
        gate_definitions = {
            item.get("id"): item
            for item in load_json(paths.gates).get("gates", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        required = set(_required_gate_definitions(work, gate_definitions))
        for gate_id, result_data in state.get("gates", {}).get(subject, {}).items():
            if gate_id not in required:
                continue
            for evidence_id in result_data.get("evidence", []):
                result = verify_evidence(paths, evidence_id, state=state)
                if result["status"] != "valid":
                    raise VoyageError(f"current gate evidence {evidence_id} is {result['status']}: {'; '.join(result['reasons'])}")
        if event_type == "work.accepted" and work.get("risk_policy_version") == RISK_POLICY_VERSION and work["risk"] == "strict":
            checkpoint = work.get("audit_checkpoint") or {}
            for evidence_id in checkpoint.get("evidence", []):
                result = verify_evidence(paths, evidence_id, state=state)
                if result["status"] != "valid":
                    raise VoyageError(
                        f"current audit checkpoint evidence {evidence_id} is {result['status']}: "
                        f"{'; '.join(result['reasons'])}"
                    )
        return
    if event_type not in typed_events:
        return
    anchor_result = verify_evidence(paths, anchor or "", state=state)
    if anchor_result["status"] != "valid":
        reason = "; ".join(anchor_result["reasons"])
        raise VoyageError(f"anchor is {anchor_result['status']}: {reason}")
    if anchor_result["kind"] not in {"git-commit", "artifact-digest"}:
        raise VoyageError("anchor must be valid git-commit or artifact-digest evidence")
    if not evidence:
        raise VoyageError(f"{event_type} requires typed evidence")
    for evidence_id in evidence:
        result = verify_evidence(paths, evidence_id, state=state)
        if result["status"] != "valid":
            reason = "; ".join(result["reasons"])
            raise VoyageError(f"evidence {evidence_id} is {result['status']}: {reason}")


def _prepare_work_risk(
    paths: ProjectPaths,
    state: dict[str, Any],
    resources: dict[str, Any],
    *,
    requested: str,
    payload: dict[str, Any] | None,
    evidence: list[str] | None,
) -> tuple[str, dict[str, Any]]:
    _require(requested in RISK_LEVELS, f"invalid risk: {requested}")
    prepared = deepcopy(payload or {})
    supplied = prepared.get("risk_assessment", {})
    if supplied is None:
        supplied = {}
    _require(isinstance(supplied, dict), "risk_assessment must be an object")
    version = supplied.get("version", RISK_POLICY_VERSION)
    _require(version == RISK_POLICY_VERSION, f"unsupported risk policy version: {version}")
    domains = supplied.get("domains", [])
    _require(
        isinstance(domains, list) and all(isinstance(item, str) for item in domains),
        "risk assessment domains must be a string array",
    )
    _require(len(domains) == len(set(domains)), "risk assessment domains must be unique")
    invalid_domains = set(domains) - set(STRICT_RISK_DOMAINS)
    _require(not invalid_domains, f"unknown risk domains: {', '.join(sorted(invalid_domains))}")
    for field in ("unknown", "disputed", "environment_change"):
        _require(isinstance(supplied.get(field, False), bool), f"risk assessment {field} must be boolean")

    effective_index = RISK_MODE_ORDER.index(requested)
    reasons: list[str] = []
    evidence_refs = list(evidence or [])
    valid_classification = False
    for evidence_id in evidence_refs:
        result = verify_evidence(paths, evidence_id, state=state)
        if result["status"] == "valid":
            valid_classification = True
            break
    if requested == "light" and not valid_classification:
        effective_index = max(effective_index, RISK_MODE_ORDER.index("standard"))
        reasons.append("missing-valid-classification-evidence")

    resource_definitions = {
        item.get("id"): item
        for item in resources.get("resources", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    for resource_id in prepared.get("required_resources", []):
        definition = resource_definitions.get(resource_id, {})
        resource_risk = definition.get("risk", "standard")
        if resource_risk in RISK_LEVELS:
            resource_index = RISK_MODE_ORDER.index(resource_risk)
            if resource_index > effective_index:
                effective_index = resource_index
                reasons.append(f"resource-risk:{resource_id}:{resource_risk}")

    unknown = supplied.get("unknown", False)
    disputed = supplied.get("disputed", False)
    if unknown:
        effective_index = RISK_MODE_ORDER.index("strict")
        reasons.append("classification-unknown")
    if disputed:
        effective_index = RISK_MODE_ORDER.index("strict")
        reasons.append("classification-disputed")
    strict_domains = sorted(set(domains) & set(STRICT_RISK_DOMAINS))
    for domain in strict_domains:
        effective_index = RISK_MODE_ORDER.index("strict")
        reasons.append(f"strict-domain:{domain}")

    effective = RISK_MODE_ORDER[effective_index]
    prepared["risk_assessment"] = {
        "version": RISK_POLICY_VERSION,
        "requested": requested,
        "effective": effective,
        "domains": sorted(domains),
        "unknown": unknown,
        "disputed": disputed,
        "environment_change": supplied.get("environment_change", False),
        "classification_evidence": evidence_refs,
        "reasons": reasons,
    }
    return effective, prepared


def _require_fresh_runtime_readback(
    paths: ProjectPaths,
    state: dict[str, Any],
    evidence: list[str] | None,
    *,
    context: str,
) -> str:
    _require(bool(evidence), f"{context} requires fresh runtime readback evidence")
    evidence_id = evidence[0]
    result = verify_evidence(paths, evidence_id, state=state)
    _require(result["kind"] == "runtime-readback", f"{context} requires runtime-readback evidence")
    _require(
        result["status"] == "valid",
        f"{context} runtime readback is {result['status']}: {'; '.join(result['reasons'])}",
    )
    return evidence_id


def _enforce_risk_policy_evidence(
    paths: ProjectPaths,
    state: dict[str, Any],
    *,
    event_type: str,
    subject: str,
    payload: dict[str, Any] | None,
    evidence: list[str] | None,
) -> None:
    work_id = (payload or {}).get("work_id") if event_type == "resource.claimed" else subject
    work = state.get("works", {}).get(work_id)
    if not isinstance(work, dict) or work.get("risk_policy_version") != RISK_POLICY_VERSION:
        return
    if event_type == "work.started" and work["risk"] == "strict":
        _require_fresh_runtime_readback(paths, state, evidence, context="strict work start")
    if event_type == "work.accepted" and (
        work["risk"] == "strict" or (work.get("risk_assessment") or {}).get("environment_change") is True
    ):
        evidence_id = _require_fresh_runtime_readback(paths, state, evidence, context="work acceptance")
        if work["risk"] == "strict":
            _require(
                evidence_id != work.get("pre_readback"),
                "strict post-action runtime readback must be separate from pre-action readback",
            )
    if event_type == "resource.claimed":
        definitions = {
            item.get("id"): item
            for item in load_json(paths.resources).get("resources", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        definition = definitions.get(subject, {})
        conflict_prone = definition.get("mode") in {"exclusive", "serialized"} or definition.get("type") == "port"
        requires_probe = work["risk"] in {"standard", "strict"} or conflict_prone
        if requires_probe:
            _require(bool(evidence), f"resource {subject} requires typed probe evidence")
            result = verify_evidence(paths, evidence[0], state=state)
            _require(result["kind"] in PROBE_EVIDENCE_KINDS, f"resource {subject} requires typed probe evidence")
            _require(
                result["status"] == "valid",
                f"resource {subject} probe evidence is {result['status']}: {'; '.join(result['reasons'])}",
            )


def append_event(
    paths: ProjectPaths,
    *,
    actor: str,
    loop: str,
    event_type: str,
    subject: str,
    risk: str,
    payload: dict[str, Any] | None = None,
    evidence: list[str] | None = None,
    anchor: str | None = None,
    authorization: str | None = None,
    caused_by: str | None = None,
) -> dict[str, Any]:
    with ledger_lock(paths.ledger):
        events = load_events(paths.ledger)
        chain_errors = validate_hash_chain(events)
        if chain_errors:
            raise VoyageError("ledger integrity failure: " + "; ".join(chain_errors))
        resources = load_json(paths.resources)
        gates = load_json(paths.gates)
        existing_state = replay_events(events, resources=resources, gates=gates)
        historical_policy_errors = _risk_policy_evidence_validation_errors(paths, events, existing_state, resources)
        if historical_policy_errors:
            raise VoyageError("risk policy evidence failure: " + "; ".join(historical_policy_errors))
        if existing_state["project_stage"] == "legacy-bootstrap" and event_type not in {"project.initialized", "decision.recorded", "project.migrated"}:
            raise VoyageError("legacy project requires migration confirmation before the first write operation")
        if event_type == "work.created":
            risk, payload = _prepare_work_risk(
                paths,
                existing_state,
                resources,
                requested=risk,
                payload=payload,
                evidence=evidence,
            )
        _enforce_typed_transition_evidence(
            paths,
            existing_state,
            event_type=event_type,
            subject=subject,
            anchor=anchor,
            evidence=evidence,
        )
        _enforce_risk_policy_evidence(
            paths,
            existing_state,
            event_type=event_type,
            subject=subject,
            payload=payload,
            evidence=evidence,
        )
        previous_hash = events[-1]["hash"] if events else None
        event = make_event(
            previous_hash,
            actor=actor,
            loop=loop,
            event_type=event_type,
            subject=subject,
            risk=risk,
            payload=payload,
            evidence=evidence,
            anchor=anchor,
            authorization=authorization,
            caused_by=caused_by,
        )
        candidate_state = replay_events(events + [event], resources=resources, gates=gates)
        runtime_errors = _truth_runtime_errors(
            paths,
            candidate_state,
            load_json(paths.truth_registry),
            load_json(paths.manifest),
        )
        if runtime_errors:
            raise VoyageError("truth runtime consistency failure: " + "; ".join(runtime_errors))
        with paths.ledger.open("a", encoding="utf-8") as handle:
            handle.write(canonical_json(event) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return event


def register_resource(
    paths: ProjectPaths,
    *,
    actor: str,
    resource_id: str,
    resource_type: str,
    mode: str,
    conflict_key: str | int | None = None,
    risk: str = "standard",
    probe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if resource_type not in ALLOWED_RESOURCE_TYPES:
        raise VoyageError(f"invalid resource type: {resource_type}")
    if mode not in ALLOWED_RESOURCE_MODES:
        raise VoyageError(f"invalid resource mode: {mode}")
    if risk not in RISK_LEVELS:
        raise VoyageError(f"invalid resource risk: {risk}")
    if not resource_id:
        raise VoyageError("resource ID is required")
    original = load_json(paths.resources)
    items = original.get("resources")
    if not isinstance(items, list):
        raise VoyageError("resources file must contain a resources array")
    if any(isinstance(item, dict) and item.get("id") == resource_id for item in items):
        raise VoyageError(f"resource already exists: {resource_id}")
    definition: dict[str, Any] = {
        "id": resource_id,
        "type": resource_type,
        "mode": mode,
        "conflict_key": conflict_key if conflict_key is not None else resource_id,
        "risk": risk,
    }
    if probe is not None:
        definition["probe"] = probe
    updated = deepcopy(original)
    updated["resources"].append(definition)
    atomic_write_json(paths.resources, updated)
    try:
        return append_event(
            paths,
            actor=actor,
            loop="governance",
            event_type="resource.registered",
            subject=resource_id,
            risk=risk,
            payload={"definition": definition},
        )
    except Exception:
        atomic_write_json(paths.resources, original)
        raise


def _typed_evidence_validation_errors(
    paths: ProjectPaths,
    events: list[dict[str, Any]],
    state: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    checked_documents: set[str] = set()
    for event in events:
        if event.get("type") == "evidence.verified":
            evidence_id = event.get("subject")
            if not isinstance(evidence_id, str) or evidence_id in checked_documents:
                continue
            checked_documents.add(evidence_id)
            try:
                document = load_evidence(paths, evidence_id)
            except VoyageError as exc:
                errors.append(str(exc))
                continue
            errors.extend(f"evidence {evidence_id}: {error}" for error in _evidence_common_errors(document))

        if event.get("type") not in {"work.delivered", "quality.passed", "quality.rejected", "gate.recorded", "audit.checked"}:
            continue
        anchor = event.get("anchor")
        if isinstance(anchor, str) and EVIDENCE_ID_PATTERN.fullmatch(anchor):
            result = verify_evidence(paths, anchor, state=state)
            if result["status"] != "valid":
                errors.append(f"consumed anchor {anchor} is {result['status']}: {'; '.join(result['reasons'])}")
        for evidence_id in event.get("evidence", []):
            if not isinstance(evidence_id, str) or EVIDENCE_ID_PATTERN.fullmatch(evidence_id) is None:
                continue
            result = verify_evidence(paths, evidence_id, state=state)
            if result["status"] != "valid":
                errors.append(f"consumed evidence {evidence_id} is {result['status']}: {'; '.join(result['reasons'])}")
    return errors


def _risk_policy_evidence_validation_errors(
    paths: ProjectPaths,
    events: list[dict[str, Any]],
    state: dict[str, Any],
    resources: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    definitions = {
        item.get("id"): item
        for item in resources.get("resources", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }

    def result_at_event(event: dict[str, Any]) -> dict[str, Any] | None:
        references = event.get("evidence")
        if not isinstance(references, list) or not references or not isinstance(references[0], str):
            return None
        try:
            checked_at = parse_time(event.get("timestamp"))
        except (TypeError, ValueError):
            return None
        return verify_evidence(paths, references[0], now=checked_at, state=state)

    def has_valid_evidence_at_event(event: dict[str, Any]) -> bool:
        references = event.get("evidence")
        if not isinstance(references, list):
            return False
        try:
            checked_at = parse_time(event.get("timestamp"))
        except (TypeError, ValueError):
            return False
        return any(
            isinstance(reference, str)
            and verify_evidence(paths, reference, now=checked_at, state=state).get("status") == "valid"
            for reference in references
        )

    for event in events:
        event_type = event.get("type")
        payload = event.get("payload", {})
        work_id = payload.get("work_id") if event_type == "resource.claimed" else event.get("subject")
        work = state.get("works", {}).get(work_id)
        if not isinstance(work, dict) or work.get("risk_policy_version") != RISK_POLICY_VERSION:
            continue
        result = result_at_event(event)
        assessment = payload.get("risk_assessment") if event_type == "work.created" else None
        if (
            event_type == "work.created"
            and isinstance(assessment, dict)
            and assessment.get("version") == RISK_POLICY_VERSION
            and assessment.get("effective") == "light"
            and not has_valid_evidence_at_event(event)
        ):
            errors.append(f"work.created {work_id} requires valid typed classification evidence at action time")
        elif event_type == "work.started" and work["risk"] == "strict":
            if result is None or result.get("kind") != "runtime-readback" or result.get("status") != "valid":
                errors.append(f"work.started {work_id} requires valid runtime-readback evidence at action time")
        elif event_type == "work.accepted" and (
            work["risk"] == "strict" or (work.get("risk_assessment") or {}).get("environment_change") is True
        ):
            if result is None or result.get("kind") != "runtime-readback" or result.get("status") != "valid":
                errors.append(f"work.accepted {work_id} requires valid runtime-readback evidence at action time")
        elif event_type == "resource.claimed":
            definition = definitions.get(event.get("subject"), {})
            conflict_prone = definition.get("mode") in {"exclusive", "serialized"} or definition.get("type") == "port"
            requires_probe = work["risk"] in {"standard", "strict"} or conflict_prone
            if requires_probe and (
                result is None or result.get("kind") not in PROBE_EVIDENCE_KINDS or result.get("status") != "valid"
            ):
                errors.append(f"resource.claimed {event.get('subject')} requires valid typed probe evidence at action time")
    return errors


def validate_project(paths: ProjectPaths) -> list[str]:
    errors: list[str] = []
    try:
        manifest = load_json(paths.manifest)
        if manifest.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"unsupported manifest schema: {manifest.get('schema_version')}")
        registry = load_json(paths.truth_registry)
        if registry.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"unsupported truth registry schema: {registry.get('schema_version')}")
        if registry.get("project") != manifest.get("project_id"):
            errors.append(
                f"truth registry project {registry.get('project')!r} does not match manifest project {manifest.get('project_id')!r}"
            )
        sources = registry.get("sources")
        if not isinstance(sources, list):
            errors.append("truth registry sources must be an array")
        else:
            active_by_domain: dict[str, list[str]] = {}
            for index, source in enumerate(sources):
                if not isinstance(source, dict):
                    errors.append(f"$.sources[{index}]: truth registry source must be an object")
                    continue
                if source.get("status") == "active":
                    path_value = source.get("path")
                    domain = source.get("domain")
                    if not isinstance(path_value, str) or not isinstance(domain, str):
                        errors.append("active truth source requires domain and path")
                        continue
                    source_path = (paths.root / path_value).resolve()
                    try:
                        source_path.relative_to(paths.root)
                    except ValueError:
                        errors.append(f"truth source escapes project root: {path_value}")
                        continue
                    if not source_path.is_file():
                        errors.append(f"active truth source is missing: {path_value}")
                    active_by_domain.setdefault(domain, []).append(path_value)
            for domain, items in active_by_domain.items():
                if len(items) > 1:
                    errors.append(f"multiple active truth sources in domain {domain}: {', '.join(items)}")

        graph = load_json(paths.graph)
        if graph.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"unsupported graph schema: {graph.get('schema_version')}")
        errors.extend(_validate_graph_definition(graph))

        resources = load_json(paths.resources)
        if resources.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"unsupported resources schema: {resources.get('schema_version')}")
        resource_items = resources.get("resources")
        if not isinstance(resource_items, list):
            errors.append("resources must be an array")
            resource_items = []
        resource_ids: set[str] = set()
        for resource in resource_items:
            if not isinstance(resource, dict):
                errors.append("resource definition must be an object")
                continue
            resource_id = resource.get("id")
            if not isinstance(resource_id, str) or not resource_id:
                errors.append("resource requires ID")
            elif resource_id in resource_ids:
                errors.append(f"duplicate resource ID: {resource_id}")
            resource_ids.add(resource_id)
            if resource.get("type") not in ALLOWED_RESOURCE_TYPES:
                errors.append(f"resource {resource_id} has invalid type")
            if resource.get("mode") not in ALLOWED_RESOURCE_MODES:
                errors.append(f"resource {resource_id} has invalid mode")

        gates = load_json(paths.gates)
        if gates.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"unsupported gates schema: {gates.get('schema_version')}")
        errors.extend(_validate_gate_definition_data(gates))
        events = load_events(paths.ledger)
        errors.extend(validate_hash_chain(events))
        errors.extend(_validate_event_data(events))
        if not errors:
            state = replay_events(events, resources=resources, gates=gates)
            errors.extend(_truth_runtime_errors(paths, state, registry, manifest))
            errors.extend(_typed_evidence_validation_errors(paths, events, state))
            errors.extend(_risk_policy_evidence_validation_errors(paths, events, state, resources))
    except VoyageError as exc:
        errors.append(str(exc))
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"invalid project data: {type(exc).__name__}: {exc}")
    return errors


def current_state(paths: ProjectPaths) -> dict[str, Any]:
    events = load_events(paths.ledger)
    errors = validate_hash_chain(events)
    if errors:
        raise VoyageError("ledger integrity failure: " + "; ".join(errors))
    resources = load_json(paths.resources)
    state = replay_events(events, resources=resources, gates=load_json(paths.gates))
    policy_errors = _risk_policy_evidence_validation_errors(paths, events, state, resources)
    if policy_errors:
        raise VoyageError("risk policy evidence failure: " + "; ".join(policy_errors))
    runtime_errors = _truth_runtime_errors(paths, state, load_json(paths.truth_registry), load_json(paths.manifest))
    if runtime_errors:
        raise VoyageError("truth runtime consistency failure: " + "; ".join(runtime_errors))
    return state


def _truth_runtime_errors(
    paths: ProjectPaths,
    state: dict[str, Any],
    registry: dict[str, Any],
    manifest: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    declared_stage = manifest.get("project_stage")
    derived_stage = state.get("project_stage")
    if declared_stage is not None and declared_stage not in {"bootstrap", "operational"}:
        errors.append(f"manifest project_stage is invalid: {declared_stage}")
    elif declared_stage is not None and declared_stage != derived_stage:
        errors.append(f"manifest project_stage {declared_stage} conflicts with ledger-derived {derived_stage}")

    source_items = registry.get("sources")
    if not isinstance(source_items, list):
        return errors
    sources = {
        item.get("id"): item
        for item in source_items
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    activations = state.get("truth_activations", {})
    for source_id, activation in activations.items():
        source = sources.get(source_id)
        if source is None:
            errors.append(f"truth activation references unknown registry source {source_id}")
            continue
        if source.get("status") == "draft":
            errors.append(f"truth activation {source_id} targets a draft registry source")
        if activation.get("domain") != source.get("domain") or activation.get("path") != source.get("path"):
            errors.append(f"truth activation identity does not match registry for {source_id}")
        try:
            target = _truth_source_path(paths, source)
        except VoyageError as exc:
            errors.append(str(exc))
            continue
        if not target.is_file():
            errors.append(f"activated truth source is missing: {source.get('path')}")
        elif not target.read_text(encoding="utf-8").strip():
            errors.append(f"activated truth source is empty: {source.get('path')}")

    if derived_stage == "operational":
        active_by_domain: dict[str, list[dict[str, Any]]] = {}
        for source in sources.values():
            if source.get("status") == "active" and source.get("domain") in REQUIRED_TRUTH_DOMAINS:
                active_by_domain.setdefault(source["domain"], []).append(source)
        for domain in REQUIRED_TRUTH_DOMAINS:
            active = active_by_domain.get(domain, [])
            if len(active) != 1:
                errors.append(f"operational project requires exactly one active truth source in domain {domain}")
                continue
            source_id = active[0]["id"]
            if source_id not in activations:
                errors.append(f"active truth source {source_id} lacks activation evidence")
    return errors


def _truth_source_path(paths: ProjectPaths, source: dict[str, Any]) -> Path:
    path_value = source.get("path")
    _require(isinstance(path_value, str) and path_value, "truth source requires path")
    target = (paths.root / path_value).resolve()
    try:
        target.relative_to(paths.root)
    except ValueError as exc:
        raise VoyageError(f"truth source escapes project root: {path_value}") from exc
    return target


def _validate_bootstrap_contract(source: dict[str, Any], content: str) -> None:
    domain = source.get("domain")
    if source.get("authority") != "bootstrap-draft":
        _require(bool(content.strip()), "truth contract must not be empty")
        return
    _require("TODO" not in content, f"truth contract {source.get('id')} contains unresolved TODO")
    for section in REQUIRED_CONTRACT_SECTIONS.get(domain, ()):
        _require(f"## {section}" in content, f"truth contract {source.get('id')} missing required section {section}")
    _require("- Status: draft" in content, f"truth contract {source.get('id')} must be draft before activation")


def enable_extension(
    paths: ProjectPaths,
    *,
    actor: str,
    extension_id: str,
    version: str,
    decision_id: str,
) -> dict[str, Any]:
    contract = EXTENSION_CATALOG.get(extension_id)
    if contract is None:
        raise VoyageError(f"unknown extension: {extension_id}")
    if contract["availability"] != "available":
        raise VoyageError(f"extension is reserved: {extension_id}")
    if version != contract["version"]:
        raise VoyageError(f"extension version mismatch: expected {contract['version']}, got {version}")
    return append_event(
        paths,
        actor=actor,
        loop="governance",
        event_type="extension.enabled",
        subject=extension_id,
        risk="standard",
        payload={
            "extension_id": extension_id,
            "version": version,
            "contract": extension_catalog_view()[extension_id],
        },
        authorization=decision_id,
    )


def disable_extension(
    paths: ProjectPaths,
    *,
    actor: str,
    extension_id: str,
    version: str,
    decision_id: str,
) -> dict[str, Any]:
    contract = EXTENSION_CATALOG.get(extension_id)
    if contract is None:
        raise VoyageError(f"unknown extension: {extension_id}")
    if version != contract["version"]:
        raise VoyageError(f"extension version mismatch: expected {contract['version']}, got {version}")
    return append_event(
        paths,
        actor=actor,
        loop="governance",
        event_type="extension.disabled",
        subject=extension_id,
        risk="standard",
        payload={"extension_id": extension_id, "version": version},
        authorization=decision_id,
    )


def effective_contract(paths: ProjectPaths) -> dict[str, Any]:
    graph = load_json(paths.graph)
    gates = load_json(paths.gates).get("gates", [])
    state = current_state(paths)
    nodes = list(graph.get("node_types", []))
    edges = list(graph.get("edge_types", []))
    effective_gates = deepcopy(gates) if isinstance(gates, list) else []
    for extension_id, extension in sorted(state["extensions"].items()):
        if extension.get("status") != "enabled":
            continue
        contract = EXTENSION_CATALOG[extension_id]
        for node in contract["node_types"]:
            if node not in nodes:
                nodes.append(node)
        for edge in contract["edge_types"]:
            if edge not in edges:
                edges.append(edge)
        known_gates = {item.get("id") for item in effective_gates if isinstance(item, dict)}
        for gate in contract["gates"]:
            if gate.get("id") not in known_gates:
                effective_gates.append(deepcopy(gate))
    return {
        "node_types": nodes,
        "edge_types": edges,
        "loops": list(graph.get("loops", [])),
        "gates": effective_gates,
    }


def extension_status(paths: ProjectPaths) -> dict[str, Any]:
    state = current_state(paths)
    extensions = deepcopy(state["extensions"])
    for extension in extensions.values():
        extension["next_safe_action"] = (
            "disable with a scoped User decision"
            if extension["status"] == "enabled"
            else "enable with a new scoped User decision"
        )
    return {
        "mode": state["extension_mode"],
        "enabled": sorted(key for key, value in extensions.items() if value.get("status") == "enabled"),
        "disabled": sorted(key for key, value in extensions.items() if value.get("status") == "disabled"),
        "reserved": sorted(key for key, value in EXTENSION_CATALOG.items() if value["availability"] == "reserved"),
        "extensions": extensions,
        "effective_contract": effective_contract(paths),
    }


def _require_derived_graph_enabled(paths: ProjectPaths) -> dict[str, Any]:
    state = current_state(paths)
    extension = state["extensions"].get("derived-graph")
    _require(
        extension is not None and extension.get("status") == "enabled",
        "derived-graph extension is not enabled",
    )
    return state


def _derived_source_fingerprints(paths: ProjectPaths, events: list[dict[str, Any]]) -> dict[str, str]:
    evidence_files = []
    evidence_root = paths.evidence / "sha256"
    if evidence_root.is_dir():
        for path in sorted(evidence_root.glob("*.json")):
            evidence_files.append(
                {
                    "path": str(path.relative_to(paths.root)),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    return {
        "manifest": content_hash(load_json(paths.manifest)),
        "truth_registry": content_hash(load_json(paths.truth_registry)),
        "graph": content_hash(load_json(paths.graph)),
        "resources": content_hash(load_json(paths.resources)),
        "gates": content_hash(load_json(paths.gates)),
        "ledger": content_hash(events),
        "evidence": content_hash(evidence_files),
    }


def _derived_node(
    node_id: str,
    node_type: str,
    *,
    status: str,
    scope: str,
    authority: str,
    risk: str = "standard",
    evidence: list[str] | None = None,
    provenance: list[str] | None = None,
    supersedes: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": node_type,
        "schema_version": DERIVED_GRAPH_SCHEMA_VERSION,
        "status": status,
        "scope": scope,
        "authority": authority,
        "risk": risk,
        "evidence": sorted(set(evidence or [])),
        "provenance": sorted(set(provenance or [])),
        "supersedes": supersedes,
        "attributes": deepcopy(attributes or {}),
    }


def _derived_edge(
    edge_type: str,
    source: str,
    target: str,
    *,
    status: str = "active",
    authority: str = "system",
    evidence: list[str] | None = None,
    provenance: list[str] | None = None,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = {
        "type": edge_type,
        "schema_version": DERIVED_GRAPH_SCHEMA_VERSION,
        "source": source,
        "target": target,
        "status": status,
        "authority": authority,
        "evidence": sorted(set(evidence or [])),
        "provenance": sorted(set(provenance or [])),
        "attributes": deepcopy(attributes or {}),
    }
    return {"id": f"edge:{content_hash(body)}", **body}


def _derive_graph_body(paths: ProjectPaths, state: dict[str, Any]) -> dict[str, Any]:
    events = load_events(paths.ledger)
    registry = load_json(paths.truth_registry)
    resources = load_json(paths.resources)
    gates = load_json(paths.gates)
    project_id = state["project_id"]
    project_node_id = f"project:{project_id}"
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}

    status_priority = {
        "missing": 0,
        "stored": 1,
        "referenced": 2,
        "superseded": 3,
        "current": 4,
    }

    def add_node(node: dict[str, Any]) -> None:
        existing = nodes.get(node["id"])
        if existing is None:
            nodes[node["id"]] = node
            return
        _require(existing["type"] == node["type"], f"derived node type collision: {node['id']}")
        existing["evidence"] = sorted(set(existing["evidence"]) | set(node["evidence"]))
        existing["provenance"] = sorted(set(existing["provenance"]) | set(node["provenance"]))
        if status_priority.get(node["status"], 0) > status_priority.get(existing["status"], 0):
            existing["status"] = node["status"]
        if existing.get("supersedes") is None and node.get("supersedes") is not None:
            existing["supersedes"] = node["supersedes"]
        existing["attributes"].update(deepcopy(node["attributes"]))

    def add_edge(edge: dict[str, Any]) -> None:
        edges[edge["id"]] = edge

    def add_principal(principal_id: str, *, provenance: str, loop: str | None = None) -> str:
        node_id = f"principal:{principal_id}"
        add_node(
            _derived_node(
                node_id,
                "principal",
                status="known",
                scope=project_id,
                authority=principal_id,
                provenance=[provenance],
                attributes={},
            )
        )
        add_edge(_derived_edge("governs", project_node_id, node_id, provenance=[provenance]))
        if loop in KERNEL_LOOPS:
            add_edge(
                _derived_edge(
                    "bound-to-loop",
                    node_id,
                    f"loop:{loop}",
                    authority=principal_id,
                    provenance=[provenance],
                )
            )
        return node_id

    def add_evidence(evidence_id: str, *, status: str, provenance: str) -> str:
        node_id = f"evidence:{evidence_id}"
        document_path = None
        kind = None
        if isinstance(evidence_id, str):
            match = EVIDENCE_ID_PATTERN.fullmatch(evidence_id)
            if match is not None:
                candidate = paths.evidence / "sha256" / f"{match.group(1)}.json"
                if candidate.is_file():
                    document_path = str(candidate.relative_to(paths.root))
                    try:
                        document = load_json(candidate)
                    except VoyageError:
                        document = {}
                    kind = document.get("kind") if isinstance(document.get("kind"), str) else None
        add_node(
            _derived_node(
                node_id,
                "evidence",
                status=status if document_path is not None else "missing",
                scope=project_id,
                authority="system",
                evidence=[evidence_id],
                provenance=[provenance] + ([document_path] if document_path else []),
                attributes={"evidence_id": evidence_id, "kind": kind},
            )
        )
        return node_id

    add_node(
        _derived_node(
            project_node_id,
            "project",
            status=state["project_stage"],
            scope=project_id,
            authority="governance",
            provenance=[str(paths.manifest.relative_to(paths.root)), state["last_event"]],
            attributes={"extension_mode": state["extension_mode"]},
        )
    )

    for loop in KERNEL_LOOPS:
        loop_id = f"loop:{loop}"
        add_node(
            _derived_node(
                loop_id,
                "loop-binding",
                status="active",
                scope=project_id,
                authority=loop,
                provenance=[str(paths.graph.relative_to(paths.root))],
                attributes={"loop": loop},
            )
        )
        add_edge(_derived_edge("governs", project_node_id, loop_id, provenance=[str(paths.graph.relative_to(paths.root))]))

    for event in events:
        add_principal(event["actor"], provenance=event["event_id"], loop=event.get("loop"))

    for source in registry.get("sources", []):
        if not isinstance(source, dict) or not isinstance(source.get("id"), str):
            continue
        source_id = f"truth:{source['id']}"
        activation = state["truth_activations"].get(source["id"], {})
        supersedes = activation.get("supersedes")
        provenance = [str(paths.truth_registry.relative_to(paths.root)), source.get("path", "")]
        if activation.get("event_id"):
            provenance.append(activation["event_id"])
        add_node(
            _derived_node(
                source_id,
                "truth-source",
                status=source.get("status", "unknown"),
                scope=source.get("domain", project_id),
                authority=source.get("authority", "unknown"),
                provenance=provenance,
                supersedes=f"truth:{supersedes}" if supersedes else None,
                attributes={
                    "domain": source.get("domain"),
                    "path": source.get("path"),
                    "version": source.get("version"),
                },
            )
        )
        add_edge(_derived_edge("governs", project_node_id, source_id, provenance=provenance))
        if supersedes:
            add_edge(_derived_edge("supersedes", source_id, f"truth:{supersedes}", provenance=provenance))

    for decision_id, decision in state["decisions"].items():
        node_id = f"decision:{decision_id}"
        payload = decision.get("payload", {})
        add_node(
            _derived_node(
                node_id,
                "decision",
                status="revoked" if decision.get("revoked") else "active",
                scope=project_id,
                authority=decision.get("actor", "user"),
                provenance=[decision["event_id"]] + ([decision["revoked_event"]] if decision.get("revoked_event") else []),
                attributes={"decision": payload.get("decision"), "scope": deepcopy(payload.get("scope"))},
            )
        )
        add_edge(_derived_edge("governs", project_node_id, node_id, provenance=[decision["event_id"]]))

    work_events: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        if event["type"].startswith("work.") or event["type"] in {"quality.passed", "quality.rejected", "gate.recorded", "audit.checked"}:
            work_events.setdefault(event["subject"], []).append(event)

    for work_id, work in state["works"].items():
        related = work_events.get(work_id, [])
        created = next((event for event in related if event["type"] == "work.created"), None)
        work_node_id = f"work:{work_id}"
        add_node(
            _derived_node(
                work_node_id,
                "work-item",
                status=work["status"],
                scope=work["scope"],
                authority="governance",
                risk=work["risk"],
                evidence=(created or {}).get("evidence", []),
                provenance=[event["event_id"] for event in related],
                attributes={
                    "title": work["title"],
                    "acceptance": deepcopy(work["acceptance"]),
                    "required_resources": deepcopy(work["required_resources"]),
                    "risk_assessment": deepcopy(work.get("risk_assessment")),
                },
            )
        )
        add_edge(_derived_edge("governs", project_node_id, work_node_id, provenance=[(created or {}).get("event_id", "")]))
        if work.get("executor"):
            add_edge(
                _derived_edge(
                    "assigned-to",
                    work_node_id,
                    add_principal(work["executor"], provenance=work.get("delivery", {}).get("event_id", "work-state"), loop="execution"),
                    authority="execution",
                    provenance=[work.get("delivery", {}).get("event_id", "work-state")],
                )
            )
        dependencies = (created or {}).get("payload", {}).get("dependencies", [])
        for dependency in dependencies if isinstance(dependencies, list) else []:
            if dependency.startswith("external:"):
                target = dependency
                add_node(
                    _derived_node(
                        target,
                        "external-anchor",
                        status="referenced",
                        scope=work_id,
                        authority="external",
                        provenance=[(created or {}).get("event_id", "")],
                        attributes={"reference": dependency},
                    )
                )
            else:
                target = f"work:{dependency}"
            add_edge(
                _derived_edge(
                    "depends-on",
                    work_node_id,
                    target,
                    authority="governance",
                    provenance=[(created or {}).get("event_id", "")],
                )
            )
        for event in related:
            decision_id = event.get("authorization")
            if isinstance(decision_id, str) and decision_id:
                add_edge(
                    _derived_edge(
                        "authorized-by",
                        work_node_id,
                        f"decision:{decision_id}",
                        authority=event["loop"],
                        provenance=[event["event_id"]],
                    )
                )

    delivery_counts: dict[str, int] = {}
    for event in events:
        if event["type"] != "work.delivered":
            continue
        work_id = event["subject"]
        delivery_counts[work_id] = delivery_counts.get(work_id, 0) + 1
        delivery_id = f"delivery:{event['event_id']}"
        work = state["works"].get(work_id, {})
        current_event = (work.get("delivery") or {}).get("event_id")
        delivery_status = "current" if current_event == event["event_id"] else "superseded"
        add_node(
            _derived_node(
                delivery_id,
                "delivery",
                status=delivery_status,
                scope=work_id,
                authority=event["actor"],
                risk=event["risk"],
                evidence=event.get("evidence", []),
                provenance=[event["event_id"]],
                attributes={"attempt": delivery_counts[work_id]},
            )
        )
        add_edge(
            _derived_edge(
                "delivered-via",
                f"work:{work_id}",
                delivery_id,
                status=delivery_status,
                authority="execution",
                provenance=[event["event_id"]],
            )
        )
        anchor = event.get("anchor")
        if isinstance(anchor, str) and anchor:
            anchor_id = f"anchor:{anchor}"
            add_node(
                _derived_node(
                    anchor_id,
                    "immutable-anchor",
                    status=delivery_status,
                    scope=work_id,
                    authority=event["actor"],
                    risk=event["risk"],
                    evidence=[anchor],
                    provenance=[event["event_id"]],
                    attributes={"evidence_id": anchor, "work_id": work_id},
                )
            )
            add_edge(_derived_edge("anchored-at", delivery_id, anchor_id, status=delivery_status, provenance=[event["event_id"]]))
            evidence_node = add_evidence(anchor, status="referenced", provenance=event["event_id"])
            add_edge(_derived_edge("validated-by", anchor_id, evidence_node, status=delivery_status, evidence=[anchor], provenance=[event["event_id"]]))
        for evidence_id in event.get("evidence", []):
            evidence_node = add_evidence(evidence_id, status="referenced", provenance=event["event_id"])
            add_edge(_derived_edge("produces", delivery_id, evidence_node, evidence=[evidence_id], provenance=[event["event_id"]]))

    for definition in gates.get("gates", []):
        if not isinstance(definition, dict) or not isinstance(definition.get("id"), str):
            continue
        gate_id = f"gate:{definition['id']}"
        add_node(
            _derived_node(
                gate_id,
                "gate",
                status="active",
                scope=project_id,
                authority=definition.get("required_loop", "quality"),
                provenance=[str(paths.gates.relative_to(paths.root))],
                attributes=definition,
            )
        )
        add_edge(_derived_edge("governs", project_node_id, gate_id, provenance=[str(paths.gates.relative_to(paths.root))]))

    for event in events:
        if event["type"] not in {"quality.passed", "quality.rejected", "gate.recorded", "audit.checked"}:
            continue
        gate_name = (
            event.get("payload", {}).get("gate_id")
            if event["type"] == "gate.recorded"
            else "independent-quality" if event["type"].startswith("quality.")
            else None
        )
        if gate_name:
            verdict = "pass" if event["type"] in {"quality.passed", "gate.recorded"} else "reject"
            add_edge(
                _derived_edge(
                    "validated-by",
                    f"work:{event['subject']}",
                    f"gate:{gate_name}",
                    status=verdict,
                    authority=event["loop"],
                    evidence=event.get("evidence", []),
                    provenance=[event["event_id"]],
                    attributes={"anchor": event.get("anchor"), "counts": deepcopy(event.get("payload", {}).get("counts"))},
                )
            )
        for evidence_id in event.get("evidence", []):
            add_evidence(evidence_id, status="referenced", provenance=event["event_id"])

    for definition in resources.get("resources", []):
        if not isinstance(definition, dict) or not isinstance(definition.get("id"), str):
            continue
        resource_id = f"resource:{definition['id']}"
        add_node(
            _derived_node(
                resource_id,
                "resource",
                status="registered",
                scope=project_id,
                authority="governance",
                risk=definition.get("risk", "standard"),
                provenance=[str(paths.resources.relative_to(paths.root))],
                attributes=definition,
            )
        )
        add_edge(_derived_edge("governs", project_node_id, resource_id, provenance=[str(paths.resources.relative_to(paths.root))]))

    lease_events: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        if event["type"] in {"resource.claimed", "resource.released", "resource.recovered"}:
            lease_id = event.get("payload", {}).get("lease_id")
            if isinstance(lease_id, str):
                lease_events.setdefault(lease_id, []).append(event)
    for lease_id, lease in state["leases"].items():
        related = lease_events.get(lease_id, [])
        node_id = f"lease:{lease_id}"
        status = "active" if lease.get("active") else "released"
        add_node(
            _derived_node(
                node_id,
                "lease",
                status=status,
                scope=lease["work_id"],
                authority=lease["holder"],
                evidence=lease.get("probe_evidence", []),
                provenance=[event["event_id"] for event in related],
                attributes={
                    "work_id": lease["work_id"],
                    "resource_id": lease["resource_id"],
                    "holder": lease["holder"],
                    "expires_at": lease["expires_at"],
                },
            )
        )
        add_edge(_derived_edge("claims", f"work:{lease['work_id']}", node_id, status=status, evidence=lease.get("probe_evidence", []), provenance=[event["event_id"] for event in related]))
        add_edge(_derived_edge("claims", node_id, f"resource:{lease['resource_id']}", status=status, evidence=lease.get("probe_evidence", []), provenance=[event["event_id"] for event in related]))
        if not lease.get("active"):
            add_edge(_derived_edge("releases", node_id, f"resource:{lease['resource_id']}", status="released", provenance=[event["event_id"] for event in related]))
        for evidence_id in lease.get("probe_evidence", []):
            add_evidence(evidence_id, status="referenced", provenance=related[0]["event_id"] if related else node_id)

    rule_events: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        if event["type"].startswith("rule."):
            rule_events.setdefault(event["subject"], []).append(event)
    for rule_id, rule in state["rules"].items():
        related = rule_events.get(rule_id, [])
        superseded_by = rule.get("superseded_by")
        node_id = f"rule:{rule_id}"
        add_node(
            _derived_node(
                node_id,
                "rule",
                status=rule["status"],
                scope=project_id,
                authority="governance",
                evidence=[evidence for event in related for evidence in event.get("evidence", [])],
                provenance=[event["event_id"] for event in related],
                supersedes=f"rule:{superseded_by}" if superseded_by else None,
                attributes={key: deepcopy(value) for key, value in rule.items() if key != "status"},
            )
        )
        add_edge(_derived_edge("governs", project_node_id, node_id, provenance=[event["event_id"] for event in related]))
        if superseded_by:
            add_edge(_derived_edge("supersedes", node_id, f"rule:{superseded_by}", provenance=[event["event_id"] for event in related]))
        for event in related:
            for evidence_id in event.get("evidence", []):
                add_evidence(evidence_id, status="referenced", provenance=event["event_id"])

    block_events: dict[str, dict[str, Any]] = {}
    for event in events:
        if event["type"] == "work.blocked":
            block_id = event.get("payload", {}).get("block_id") or f"block-{event['event_id']}"
            block_events[block_id] = event
    for block_id, block in state["blocks"].items():
        event = block_events.get(block_id)
        provenance = [event["event_id"]] if event else []
        node_id = f"block:{block_id}"
        add_node(
            _derived_node(
                node_id,
                "block",
                status="active" if block.get("active") else "resolved",
                scope=block.get("scope", block["work_id"]),
                authority=block["actor"],
                evidence=(event or {}).get("evidence", []),
                provenance=provenance,
                attributes={
                    "work_id": block["work_id"],
                    "blocker": block["actor"],
                    "reason": block.get("reason"),
                    "unblock_condition": block.get("unblock_condition"),
                    "appeal_to": block.get("appeal_to"),
                },
            )
        )
        add_edge(_derived_edge("blocks", node_id, f"work:{block['work_id']}", status="active" if block.get("active") else "resolved", evidence=(event or {}).get("evidence", []), provenance=provenance))
        appeal_to = block.get("appeal_to")
        if isinstance(appeal_to, str) and appeal_to:
            target = add_principal(appeal_to, provenance=(event or {}).get("event_id", node_id))
            add_edge(_derived_edge("escalates-to", node_id, target, status="active" if block.get("active") else "resolved", provenance=provenance))
        for evidence_id in (event or {}).get("evidence", []):
            add_evidence(evidence_id, status="referenced", provenance=(event or {}).get("event_id", node_id))

    evidence_root = paths.evidence / "sha256"
    if evidence_root.is_dir():
        for path in sorted(evidence_root.glob("*.json")):
            add_evidence(f"sha256:{path.stem}", status="stored", provenance=str(path.relative_to(paths.root)))

    body = {
        "schema_version": DERIVED_GRAPH_SCHEMA_VERSION,
        "project_id": project_id,
        "ledger_head": state["last_event"],
        "source_fingerprints": _derived_source_fingerprints(paths, events),
        "nodes": [nodes[node_id] for node_id in sorted(nodes)],
        "edges": [edges[edge_id] for edge_id in sorted(edges)],
    }
    return body


def derive_graph(paths: ProjectPaths) -> dict[str, Any]:
    state = _require_derived_graph_enabled(paths)
    body = _derive_graph_body(paths, state)
    return {**body, "fingerprint": content_hash(body)}


def _graph_issue(
    code: str,
    subject: str,
    message: str,
    *,
    related: list[str] | None = None,
    severity: str = "error",
) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "subject": subject,
        "related": list(related or []),
        "message": message,
    }


def _sort_graph_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    severity_order = {"error": 0, "warning": 1}
    return sorted(
        issues,
        key=lambda item: (
            severity_order.get(item.get("severity"), 2),
            item.get("code", ""),
            item.get("subject", ""),
            canonical_json(item.get("related", [])),
        ),
    )


def _derived_graph_enabled_in_events(events: list[dict[str, Any]]) -> bool:
    enabled = False
    for event in events:
        if event.get("subject") != "derived-graph":
            continue
        if event.get("type") == "extension.enabled":
            enabled = True
        elif event.get("type") == "extension.disabled":
            enabled = False
    return enabled


def _canonical_dependency_cycles(adjacency: dict[str, set[str]]) -> list[list[str]]:
    visited: set[str] = set()
    active: set[str] = set()
    stack: list[str] = []
    cycles: set[tuple[str, ...]] = set()

    def canonicalize(path: list[str]) -> tuple[str, ...]:
        body = path[:-1]
        rotations = [tuple(body[index:] + body[:index]) for index in range(len(body))]
        canonical = min(rotations)
        return canonical + (canonical[0],)

    def visit(node: str) -> None:
        visited.add(node)
        active.add(node)
        stack.append(node)
        for target in sorted(adjacency.get(node, set())):
            if target not in visited:
                visit(target)
            elif target in active:
                index = stack.index(target)
                cycles.add(canonicalize(stack[index:] + [target]))
        stack.pop()
        active.remove(node)

    for node in sorted(adjacency):
        if node not in visited:
            visit(node)
    return [list(cycle) for cycle in sorted(cycles)]


def _raw_dependency_issues(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    created = {
        event.get("subject")
        for event in events
        if event.get("type") == "work.created" and isinstance(event.get("subject"), str)
    }
    adjacency: dict[str, set[str]] = {f"work:{work_id}": set() for work_id in created}
    issues: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") != "work.created" or not isinstance(event.get("subject"), str):
            continue
        source = f"work:{event['subject']}"
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        dependencies = payload.get("dependencies", [])
        if not isinstance(dependencies, list):
            continue
        for dependency in dependencies:
            if not isinstance(dependency, str) or dependency.startswith("external:"):
                continue
            target = f"work:{dependency}"
            if dependency not in created:
                issues.append(
                    _graph_issue(
                        "dangling-reference",
                        source,
                        f"internal work dependency does not exist: {target}",
                        related=[target],
                    )
                )
            else:
                adjacency[source].add(target)
    for cycle in _canonical_dependency_cycles(adjacency):
        issues.append(
            _graph_issue(
                "dependency-cycle",
                cycle[0],
                "work dependency cycle: " + " -> ".join(cycle),
                related=cycle,
            )
        )
    return issues


def _graph_check_result(
    *,
    project_id: str | None,
    ledger_head: str | None,
    graph_fingerprint: str | None,
    issues: list[dict[str, Any]],
    node_count: int,
    edge_count: int,
) -> dict[str, Any]:
    ordered = _sort_graph_issues(issues)
    errors = sum(item["severity"] == "error" for item in ordered)
    warnings = sum(item["severity"] == "warning" for item in ordered)
    return {
        "schema_version": DERIVED_GRAPH_SCHEMA_VERSION,
        "project_id": project_id,
        "ledger_head": ledger_head,
        "graph_fingerprint": graph_fingerprint,
        "valid": errors == 0,
        "summary": {"errors": errors, "warnings": warnings, "nodes": node_count, "edges": edge_count},
        "issues": ordered,
    }


def _structural_graph_issues(paths: ProjectPaths, graph: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    node_items = graph.get("nodes", []) if isinstance(graph.get("nodes"), list) else []
    edge_items = graph.get("edges", []) if isinstance(graph.get("edges"), list) else []

    node_counts: dict[str, int] = {}
    edge_counts: dict[str, int] = {}
    for node in node_items:
        if isinstance(node, dict) and isinstance(node.get("id"), str):
            node_counts[node["id"]] = node_counts.get(node["id"], 0) + 1
    for edge in edge_items:
        if isinstance(edge, dict) and isinstance(edge.get("id"), str):
            edge_counts[edge["id"]] = edge_counts.get(edge["id"], 0) + 1
    for node_id, count in sorted(node_counts.items()):
        if count > 1:
            issues.append(_graph_issue("duplicate-node-id", node_id, f"node ID occurs {count} times"))
    for edge_id, count in sorted(edge_counts.items()):
        if count > 1:
            issues.append(_graph_issue("duplicate-edge-id", edge_id, f"edge ID occurs {count} times"))

    nodes = {
        node["id"]: node
        for node in node_items
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }
    effective = effective_contract(paths)
    allowed_nodes = set(effective["node_types"])
    allowed_edges = set(effective["edge_types"])
    for node_id, node in sorted(nodes.items()):
        if node.get("type") not in allowed_nodes:
            issues.append(_graph_issue("unknown-node-type", node_id, f"node type is not in effective contract: {node.get('type')}"))
    valid_edges: list[dict[str, Any]] = []
    for edge in edge_items:
        if not isinstance(edge, dict) or not isinstance(edge.get("id"), str):
            continue
        if edge.get("type") not in allowed_edges:
            issues.append(_graph_issue("unknown-edge-type", edge["id"], f"edge type is not in effective contract: {edge.get('type')}"))
        missing = [endpoint for endpoint in (edge.get("source"), edge.get("target")) if endpoint not in nodes]
        if missing:
            issues.append(
                _graph_issue(
                    "dangling-edge",
                    edge["id"],
                    "edge endpoint does not exist: " + ", ".join(str(item) for item in missing),
                    related=[str(item) for item in missing],
                )
            )
        else:
            valid_edges.append(edge)

    dependency_adjacency: dict[str, set[str]] = {
        node_id: set() for node_id, node in nodes.items() if node.get("type") == "work-item"
    }
    for edge in valid_edges:
        if edge.get("type") == "depends-on" and edge.get("source") in dependency_adjacency and edge.get("target") in dependency_adjacency:
            dependency_adjacency[edge["source"]].add(edge["target"])
    for cycle in _canonical_dependency_cycles(dependency_adjacency):
        issues.append(_graph_issue("dependency-cycle", cycle[0], "work dependency cycle: " + " -> ".join(cycle), related=cycle))

    for node_id, node in sorted(nodes.items()):
        if node.get("type") != "immutable-anchor" or node.get("status") != "current":
            continue
        evidence_id = node.get("attributes", {}).get("evidence_id")
        result = verify_evidence(paths, evidence_id)
        if result["status"] != "valid" or result["kind"] not in {"git-commit", "artifact-digest"}:
            subject = f"work:{node.get('attributes', {}).get('work_id')}"
            reason = "; ".join(result["reasons"]) if result["reasons"] else f"invalid anchor kind: {result['kind']}"
            issues.append(_graph_issue("invalid-anchor", subject, reason, related=[node_id]))

    adjacency: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    for edge in valid_edges:
        source = edge["source"]
        target = edge["target"]
        adjacency[source].add(target)
        adjacency[target].add(source)
    project_nodes = sorted(node_id for node_id, node in nodes.items() if node.get("type") == "project")
    reachable: set[str] = set()
    pending = list(project_nodes[:1])
    while pending:
        node_id = pending.pop(0)
        if node_id in reachable:
            continue
        reachable.add(node_id)
        pending.extend(sorted(adjacency[node_id] - reachable))
    active_types = {"work-item", "delivery", "immutable-anchor", "gate", "resource", "lease", "rule", "block", "decision", "truth-source"}
    inactive_statuses = {"closed", "disabled", "missing", "released", "resolved", "retired", "revoked", "stored", "superseded"}
    for node_id, node in sorted(nodes.items()):
        if node.get("type") in active_types and node.get("status") not in inactive_statuses and node_id not in reachable:
            issues.append(_graph_issue("orphan-active-node", node_id, "active node is not reachable from the project node"))

    for node_id, node in sorted(nodes.items()):
        if node.get("type") != "block" or node.get("status") != "active":
            continue
        attributes = node.get("attributes", {})
        blocker = attributes.get("blocker")
        appeal_to = attributes.get("appeal_to")
        condition = attributes.get("unblock_condition")
        if not isinstance(condition, str) or not condition.strip() or not isinstance(appeal_to, str) or not appeal_to or appeal_to == blocker:
            issues.append(
                _graph_issue(
                    "unresolvable-block",
                    node_id,
                    "active block lacks an independent resolution target or unblock condition",
                    related=[f"principal:{appeal_to}"] if appeal_to else [],
                )
            )
    return issues


def check_graph(paths: ProjectPaths, *, graph: dict[str, Any] | None = None) -> dict[str, Any]:
    events = load_events(paths.ledger)
    if graph is not None:
        _require_derived_graph_enabled(paths)
        raw_issues = _raw_dependency_issues(events)
        issues = raw_issues + _structural_graph_issues(paths, graph)
        return _graph_check_result(
            project_id=graph.get("project_id"),
            ledger_head=graph.get("ledger_head"),
            graph_fingerprint=graph.get("fingerprint"),
            issues=issues,
            node_count=len(graph.get("nodes", [])) if isinstance(graph.get("nodes"), list) else 0,
            edge_count=len(graph.get("edges", [])) if isinstance(graph.get("edges"), list) else 0,
        )

    raw_issues = _raw_dependency_issues(events)
    try:
        derived = derive_graph(paths)
    except VoyageError as exc:
        if not _derived_graph_enabled_in_events(events):
            raise
        if not raw_issues:
            raw_issues.append(_graph_issue("project-invalid", f"project:{events[0].get('subject', 'unknown') if events else 'unknown'}", str(exc)))
        return _graph_check_result(
            project_id=events[0].get("subject") if events else None,
            ledger_head=events[-1].get("event_id") if events else None,
            graph_fingerprint=None,
            issues=raw_issues,
            node_count=0,
            edge_count=0,
        )
    issues = raw_issues + _structural_graph_issues(paths, derived)
    return _graph_check_result(
        project_id=derived["project_id"],
        ledger_head=derived["ledger_head"],
        graph_fingerprint=derived["fingerprint"],
        issues=issues,
        node_count=len(derived["nodes"]),
        edge_count=len(derived["edges"]),
    )


def graph_path(paths: ProjectPaths, source: str, target: str) -> dict[str, Any]:
    graph = derive_graph(paths)
    known = {node.get("id") for node in graph["nodes"] if isinstance(node, dict)}
    for endpoint in (source, target):
        _require(endpoint in known, f"unknown graph endpoint: {endpoint}")
    found = source == target
    node_path = [source] if found else []
    edge_path: list[dict[str, Any]] = []
    if not found:
        outgoing: dict[str, list[dict[str, Any]]] = {node_id: [] for node_id in known}
        for edge in graph["edges"]:
            if edge["source"] in outgoing and edge["target"] in known:
                outgoing[edge["source"]].append(edge)
        for edge_list in outgoing.values():
            edge_list.sort(key=lambda item: (item["target"], item["id"]))
        pending = [source]
        visited = {source}
        parent: dict[str, tuple[str, dict[str, Any]]] = {}
        while pending and target not in visited:
            node_id = pending.pop(0)
            for edge in outgoing[node_id]:
                next_id = edge["target"]
                if next_id in visited:
                    continue
                visited.add(next_id)
                parent[next_id] = (node_id, edge)
                pending.append(next_id)
                if next_id == target:
                    break
        found = target in visited
        if found:
            reversed_nodes = [target]
            reversed_edges: list[dict[str, Any]] = []
            cursor = target
            while cursor != source:
                previous, edge = parent[cursor]
                reversed_nodes.append(previous)
                reversed_edges.append(edge)
                cursor = previous
            node_path = list(reversed(reversed_nodes))
            edge_path = list(reversed(reversed_edges))
    return {
        "schema_version": DERIVED_GRAPH_SCHEMA_VERSION,
        "project_id": graph["project_id"],
        "ledger_head": graph["ledger_head"],
        "graph_fingerprint": graph["fingerprint"],
        "from": source,
        "to": target,
        "found": found,
        "length": len(edge_path),
        "nodes": node_path,
        "edges": edge_path,
    }


def risk_status(paths: ProjectPaths, work_id: str) -> dict[str, Any]:
    state = current_state(paths)
    work = _work(state, work_id)
    assessment = deepcopy(work.get("risk_assessment"))
    return {
        "work_id": work_id,
        "policy_version": work.get("risk_policy_version"),
        "legacy": work.get("risk_policy_version") is None,
        "declared": work.get("declared_risk", work["risk"]),
        "effective": work["risk"],
        "assessment": assessment,
        "requirements": deepcopy(RISK_POLICIES[work["risk"]]),
        "missing_controls": _missing_risk_controls(paths, state, work),
        "status": work["status"],
        "next_safe_action": next_safe_action(work),
    }


def _missing_risk_controls(paths: ProjectPaths, state: dict[str, Any], work: dict[str, Any]) -> list[str]:
    if work.get("risk_policy_version") != RISK_POLICY_VERSION:
        return []
    missing: set[str] = set()
    status = work["status"]
    if work["risk"] == "strict":
        if status == "draft":
            missing.add("user-decision:work.authorize")
        if status in {"authorized", "rejected"}:
            missing.update({"user-decision:work.start", "runtime-readback:pre-action"})
        if status in {"delivered", "quality-passed"} and work.get("audit_checkpoint") is None:
            missing.add("audit.checked:current-anchor")
        if status == "quality-passed":
            missing.add("runtime-readback:post-action")
    elif status == "quality-passed" and (work.get("risk_assessment") or {}).get("environment_change") is True:
        missing.add("runtime-readback:post-action")

    if status in {"authorized", "rejected"}:
        active_resources = {
            lease["resource_id"]
            for lease in state["leases"].values()
            if lease.get("active") and lease.get("work_id") == work["id"]
        }
        for resource_id in set(work.get("required_resources", [])) - active_resources:
            missing.add(f"resource-lease:{resource_id}")

    if status == "quality-passed":
        gate_defs = {
            item.get("id"): item
            for item in load_json(paths.gates).get("gates", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        results = state.get("gates", {}).get(work["id"], {})
        for gate_id in _required_gate_definitions(work, gate_defs):
            result = results.get(gate_id)
            if not result or result.get("verdict") != "pass":
                missing.add(f"gate:{gate_id}")
    return sorted(missing)


def activate_truth(
    paths: ProjectPaths,
    *,
    actor: str,
    source_id: str,
    decision_id: str,
    supersedes: str | None = None,
) -> dict[str, Any]:
    manifest = load_json(paths.manifest)
    registry = load_json(paths.truth_registry)
    state = current_state(paths)
    project_id = manifest.get("project_id")
    _require(isinstance(project_id, str) and project_id, "manifest requires project_id")
    _require(source_id not in state["truth_activations"], f"truth source {source_id} already has activation evidence")
    _require_decision_scope(
        state,
        decision_id,
        action="truth.activate",
        project_id=project_id,
        source_id=source_id,
    )

    sources = registry.get("sources")
    _require(isinstance(sources, list), "truth registry sources must be an array")
    target = next((item for item in sources if isinstance(item, dict) and item.get("id") == source_id), None)
    _require(target is not None, f"unknown truth source: {source_id}")
    domain = target.get("domain")
    _require(isinstance(domain, str) and domain, f"truth source {source_id} requires domain")
    contract_path = _truth_source_path(paths, target)
    _require(contract_path.is_file(), f"truth contract file is missing: {target.get('path')}")
    original_contract = contract_path.read_text(encoding="utf-8")
    _validate_bootstrap_contract(target, original_contract)

    active_same_domain = [
        item for item in sources
        if isinstance(item, dict) and item.get("domain") == domain and item.get("status") == "active" and item.get("id") != source_id
    ]
    if active_same_domain and supersedes is None:
        raise VoyageError(f"domain {domain} already has active source; activation requires explicit supersedes")
    if supersedes is not None:
        previous = next((item for item in sources if isinstance(item, dict) and item.get("id") == supersedes), None)
        _require(previous is not None and previous.get("status") == "active", f"superseded source is not active: {supersedes}")
        _require(previous.get("domain") == domain, "supersedes must target a source in the same domain")

    updated_registry = deepcopy(registry)
    updated_target = next(item for item in updated_registry["sources"] if item.get("id") == source_id)
    updated_target["status"] = "active"
    updated_target["authority"] = f"user-decision:{decision_id}"
    if supersedes is not None:
        updated_previous = next(item for item in updated_registry["sources"] if item.get("id") == supersedes)
        updated_previous["status"] = "superseded"

    updated_contract = original_contract
    if target.get("authority") == "bootstrap-draft":
        updated_contract = original_contract.replace("- Status: draft", "- Status: active", 1)

    original_manifest = deepcopy(manifest)
    original_registry = deepcopy(registry)
    existing_domains = {item["domain"] for item in state["truth_activations"].values()}
    next_stage = "operational" if set(REQUIRED_TRUTH_DOMAINS).issubset(existing_domains | {domain}) else "bootstrap"
    updated_manifest = deepcopy(manifest)
    updated_manifest["project_stage"] = next_stage

    atomic_write_json(paths.truth_registry, updated_registry)
    atomic_write_json(paths.manifest, updated_manifest)
    if updated_contract != original_contract:
        _write_text(contract_path, updated_contract)
    try:
        return append_event(
            paths,
            actor=actor,
            loop="governance",
            event_type="truth.activated",
            subject=source_id,
            risk="standard",
            payload={
                "source_id": source_id,
                "domain": domain,
                "path": target["path"],
                "project_id": project_id,
                "supersedes": supersedes,
            },
            evidence=[f"contract:{target['path']}", f"decision:{decision_id}"],
            authorization=decision_id,
        )
    except Exception:
        atomic_write_json(paths.manifest, original_manifest)
        atomic_write_json(paths.truth_registry, original_registry)
        if updated_contract != original_contract:
            _write_text(contract_path, original_contract)
        raise


def migrate_legacy_project(
    paths: ProjectPaths,
    *,
    actor: str,
    decision_id: str,
) -> dict[str, Any]:
    manifest = load_json(paths.manifest)
    _require("project_stage" not in manifest, "project migration is only for v0.1 legacy projects")
    project_id = manifest.get("project_id")
    _require(isinstance(project_id, str) and project_id, "manifest requires project_id")
    state = current_state(paths)
    _require(state["project_stage"] == "legacy-bootstrap", "project migration is only for v0.1 legacy projects")
    _require_decision_scope(
        state,
        decision_id,
        action="truth.migrate",
        project_id=project_id,
    )

    registry = load_json(paths.truth_registry)
    sources = registry.get("sources")
    _require(isinstance(sources, list), "truth registry sources must be an array")
    active_required: dict[str, dict[str, Any]] = {}
    for source in sources:
        if not isinstance(source, dict) or source.get("status") != "active":
            continue
        domain = source.get("domain")
        if domain in REQUIRED_TRUTH_DOMAINS:
            _require(domain not in active_required, f"legacy project has multiple active truth sources in domain {domain}")
            contract_path = _truth_source_path(paths, source)
            _require(contract_path.is_file(), f"truth contract file is missing: {source.get('path')}")
            _require(bool(contract_path.read_text(encoding="utf-8").strip()), f"truth contract is empty: {source.get('path')}")
            active_required[domain] = source
    _require(
        set(active_required) == set(REQUIRED_TRUTH_DOMAINS),
        "legacy migration requires four active required domains",
    )

    original_manifest = deepcopy(manifest)
    updated_manifest = deepcopy(manifest)
    updated_manifest["project_stage"] = "operational"
    atomic_write_json(paths.manifest, updated_manifest)
    try:
        return append_event(
            paths,
            actor=actor,
            loop="governance",
            event_type="project.migrated",
            subject=project_id,
            risk="standard",
            payload={
                "project_id": project_id,
                "from": "v0.1-legacy",
                "to": "operational",
                "sources": [
                    {"id": source["id"], "domain": domain, "path": source["path"]}
                    for domain, source in sorted(active_required.items())
                ],
            },
            evidence=[f"decision:{decision_id}", "truth-registry:active-required-domains"],
            authorization=decision_id,
        )
    except Exception:
        atomic_write_json(paths.manifest, original_manifest)
        raise


def truth_status(paths: ProjectPaths) -> dict[str, Any]:
    manifest = load_json(paths.manifest)
    registry = load_json(paths.truth_registry)
    state = current_state(paths)
    activations = state.get("truth_activations", {})
    sources: list[dict[str, Any]] = []
    verified_domains: set[str] = set()
    unverified_active: list[str] = []
    for source in registry.get("sources", []):
        if not isinstance(source, dict):
            continue
        item = deepcopy(source)
        verified = source.get("id") in activations
        item["activation_verified"] = verified
        item["activation_event"] = activations.get(source.get("id"), {}).get("event_id") if verified else None
        sources.append(item)
        if source.get("status") == "active" and verified and source.get("domain") in REQUIRED_TRUTH_DOMAINS:
            verified_domains.add(source["domain"])
        elif source.get("status") == "active" and not verified:
            unverified_active.append(source.get("id", "<unknown>"))
    missing = [domain for domain in REQUIRED_TRUTH_DOMAINS if domain not in verified_domains]
    stage = state.get("project_stage", manifest.get("project_stage", "legacy-bootstrap"))
    legacy = "project_stage" not in manifest or stage == "legacy-bootstrap"
    if legacy:
        next_action = "record a scoped User decision and run voyage truth migrate"
    elif missing:
        next_action = "review draft contracts, record a scoped User decision, and run voyage truth activate"
    else:
        next_action = "none"
    return {
        "project_stage": stage,
        "legacy": legacy,
        "required_domains": list(REQUIRED_TRUTH_DOMAINS),
        "missing_domains": missing,
        "unverified_active_sources": sorted(unverified_active),
        "sources": sources,
        "next_safe_action": next_action,
    }


def active_leases(state: dict[str, Any], *, now: datetime | None = None) -> list[dict[str, Any]]:
    checked_at = now or datetime.now(timezone.utc)
    if checked_at.tzinfo is None:
        raise VoyageError("lease readback time must include timezone")
    result = []
    for lease in state["leases"].values():
        if not lease["active"]:
            continue
        item = deepcopy(lease)
        try:
            item["expired"] = parse_time(lease["expires_at"]) <= checked_at
        except (KeyError, TypeError, ValueError) as exc:
            raise VoyageError(f"lease {lease.get('lease_id', '<unknown>')} expires_at is not a valid date-time") from exc
        item["recovery_required"] = item["expired"] and lease["stateful"]
        result.append(item)
    return sorted(result, key=lambda item: item["lease_id"])


def probe_port(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.settimeout(0.2)
        return client.connect_ex((host, port)) == 0


def new_lease_expiry(ttl_minutes: int) -> str:
    if ttl_minutes <= 0:
        raise VoyageError("lease TTL must be positive")
    return (datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)).isoformat(timespec="seconds").replace("+00:00", "Z")


def _recovery_fact(
    *,
    subject: str,
    claim: str,
    source_event: str | None,
    evidence_id: str | None = None,
    evidence_kind: str | None = None,
    verified_at: str | None = None,
    freshness: str | None = None,
    conclusion: str,
    blocking_scope: str | None = None,
    next_safe_action: str,
    required_loop: str,
) -> dict[str, Any]:
    return {
        "subject": subject,
        "claim": claim,
        "source_event": source_event,
        "evidence_id": evidence_id,
        "evidence_kind": evidence_kind,
        "verified_at": verified_at,
        "freshness": freshness,
        "conclusion": conclusion,
        "blocking_scope": blocking_scope,
        "next_safe_action": next_safe_action,
        "required_loop": required_loop,
    }


def recovery_fact_sort_key(item: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(item.get(key) or "") for key in ("subject", "claim", "source_event", "evidence_id"))


def _evidence_recovery_facts(
    paths: ProjectPaths,
    events: list[dict[str, Any]],
    state: dict[str, Any],
    *,
    now: datetime,
) -> dict[str, list[dict[str, Any]]]:
    facts: dict[str, list[dict[str, Any]]] = {bucket: [] for bucket in RECOVERY_FACT_BUCKETS}
    seen: set[tuple[str, str]] = set()
    for event in events:
        references = list(event.get("evidence", []))
        if isinstance(event.get("anchor"), str):
            references.append(event["anchor"])
        for evidence_id in references:
            if not isinstance(evidence_id, str):
                continue
            identity = (event["subject"], evidence_id)
            if identity in seen:
                continue
            seen.add(identity)
            if EVIDENCE_ID_PATTERN.fullmatch(evidence_id) is None:
                facts["declared"].append(
                    _recovery_fact(
                        subject=event["subject"],
                        claim=event["type"],
                        source_event=event["event_id"],
                        evidence_id=evidence_id,
                        conclusion="declared",
                        freshness="unverified",
                        blocking_scope=event["subject"],
                        next_safe_action="replace legacy evidence with typed evidence",
                        required_loop=event["loop"],
                    )
                )
                continue

            result = verify_evidence(paths, evidence_id, now=now, state=state)
            try:
                document = load_evidence(paths, evidence_id)
            except VoyageError:
                document = {}
            claim = document.get("claim") if isinstance(document.get("claim"), str) else event["type"]
            if result["status"] == "valid":
                facts["observed"].append(
                    _recovery_fact(
                        subject=event["subject"],
                        claim=claim,
                        source_event=event["event_id"],
                        evidence_id=evidence_id,
                        evidence_kind=result["kind"],
                        verified_at=result["verified_at"],
                        freshness="fresh",
                        conclusion="valid",
                        next_safe_action="none",
                        required_loop=event["loop"],
                    )
                )
                continue

            expired = result["status"] == "unknown" and any("expired" in reason for reason in result["reasons"])
            facts["unknown"].append(
                _recovery_fact(
                    subject=event["subject"],
                    claim=claim,
                    source_event=event["event_id"],
                    evidence_id=evidence_id,
                    evidence_kind=result["kind"],
                    verified_at=result["verified_at"],
                    freshness="expired" if expired else "invalid",
                    conclusion=result["status"],
                    blocking_scope=event["subject"],
                    next_safe_action=(
                        "re-probe and record fresh typed evidence"
                        if expired else "repair or replace typed evidence and verify"
                    ),
                    required_loop="execution" if result["kind"] == "runtime-readback" else event["loop"],
                )
            )
    return facts


def _resource_recovery_facts(
    paths: ProjectPaths,
    events: list[dict[str, Any]],
    state: dict[str, Any],
    *,
    now: datetime,
    port_probe,
) -> dict[str, list[dict[str, Any]]]:
    facts: dict[str, list[dict[str, Any]]] = {bucket: [] for bucket in RECOVERY_FACT_BUCKETS}
    definitions = {
        item["id"]: item
        for item in load_json(paths.resources).get("resources", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    lease_events: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        if event.get("type") not in {"resource.claimed", "resource.released", "resource.recovered"}:
            continue
        lease_id = event.get("payload", {}).get("lease_id")
        if isinstance(lease_id, str):
            lease_events.setdefault(lease_id, []).append(event)

    for lease_id, lease in sorted(state["leases"].items()):
        resource_id = lease["resource_id"]
        history = lease_events.get(lease_id, [])
        source = history[-1] if history else None
        source_event = source.get("event_id") if source else None
        scope = f"resource:{resource_id}/lease:{lease_id}"
        if lease["active"]:
            try:
                expired = parse_time(lease["expires_at"]) <= now
            except (KeyError, TypeError, ValueError):
                expired = True
            if expired:
                facts["unknown"].append(
                    _recovery_fact(
                        subject=resource_id,
                        claim="resource.lease-active",
                        source_event=source_event,
                        freshness="expired",
                        conclusion="unknown",
                        blocking_scope=scope,
                        next_safe_action="recover or renew the expired lease after resource readback",
                        required_loop="governance",
                    )
                )
            elif lease.get("stateful"):
                facts["unknown"].append(
                    _recovery_fact(
                        subject=resource_id,
                        claim="resource.lease-active",
                        source_event=source_event,
                        freshness="unprobed",
                        conclusion="unknown",
                        blocking_scope=scope,
                        next_safe_action="run an adapted fresh resource probe before reuse",
                        required_loop="execution",
                    )
                )
            else:
                facts["declared"].append(
                    _recovery_fact(
                        subject=resource_id,
                        claim="resource.lease-active",
                        source_event=source_event,
                        freshness="current",
                        conclusion="declared",
                        blocking_scope=scope,
                        next_safe_action="respect the active lease or obtain a governed release",
                        required_loop="execution",
                    )
                )
            continue

        definition = definitions.get(resource_id, {})
        if definition.get("type") != "port" or not source or source.get("type") not in {"resource.released", "resource.recovered"}:
            continue
        try:
            port = int(definition.get("conflict_key", resource_id))
            occupied = port_probe(port)
        except (OSError, TypeError, ValueError):
            facts["unknown"].append(
                _recovery_fact(
                    subject=resource_id,
                    claim="resource.released",
                    source_event=source_event,
                    evidence_kind="port-probe",
                    verified_at=now.isoformat(timespec="seconds").replace("+00:00", "Z"),
                    freshness="unknown",
                    conclusion="unknown",
                    blocking_scope=f"resource:{resource_id}",
                    next_safe_action="re-run the registered port probe before reuse",
                    required_loop="execution",
                )
            )
            continue
        if occupied:
            facts["conflicts"].append(
                _recovery_fact(
                    subject=resource_id,
                    claim="resource.released",
                    source_event=source_event,
                    evidence_kind="port-probe",
                    verified_at=now.isoformat(timespec="seconds").replace("+00:00", "Z"),
                    freshness="fresh",
                    conclusion="declared-released-but-port-occupied",
                    blocking_scope=f"resource:{resource_id}",
                    next_safe_action="reconcile port occupancy with the released lease before reuse",
                    required_loop="governance",
                )
            )
        else:
            facts["observed"].append(
                _recovery_fact(
                    subject=resource_id,
                    claim="resource.released",
                    source_event=source_event,
                    evidence_kind="port-probe",
                    verified_at=now.isoformat(timespec="seconds").replace("+00:00", "Z"),
                    freshness="fresh",
                    conclusion="port-free",
                    next_safe_action="none",
                    required_loop="execution",
                )
            )
    return facts


def _current_state_recovery_facts(
    events: list[dict[str, Any]],
    state: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    facts: dict[str, list[dict[str, Any]]] = {bucket: [] for bucket in RECOVERY_FACT_BUCKETS}
    latest_work: dict[str, dict[str, Any]] = {}
    latest_rule: dict[str, dict[str, Any]] = {}
    block_sources: dict[str, dict[str, Any]] = {}
    for event in events:
        event_type = event.get("type", "")
        if event_type.startswith("work."):
            latest_work[event["subject"]] = event
        if event_type.startswith("rule."):
            latest_rule[event["subject"]] = event
        if event_type == "work.blocked":
            block_id = event.get("payload", {}).get("block_id") or f"block-{event['event_id']}"
            block_sources[block_id] = event

    for work_id, work in sorted(state["works"].items()):
        source = latest_work.get(work_id)
        facts["declared"].append(
            _recovery_fact(
                subject=work_id,
                claim=f"work.status:{work['status']}",
                source_event=source.get("event_id") if source else None,
                freshness="current",
                conclusion="declared",
                blocking_scope=f"work:{work_id}",
                next_safe_action=next_safe_action(work),
                required_loop=(source.get("loop") if source else "governance"),
            )
        )

    for rule_id, rule in sorted(state["rules"].items()):
        source = latest_rule.get(rule_id)
        facts["declared"].append(
            _recovery_fact(
                subject=rule_id,
                claim=f"rule.status:{rule['status']}",
                source_event=source.get("event_id") if source else None,
                freshness="current",
                conclusion="declared",
                blocking_scope=f"rule:{rule_id}",
                next_safe_action="inspect the active rule lifecycle before changing it",
                required_loop="governance",
            )
        )

    for block_id, block in sorted(state["blocks"].items()):
        if not block.get("active"):
            continue
        source = block_sources.get(block_id)
        facts["declared"].append(
            _recovery_fact(
                subject=block_id,
                claim="block.active",
                source_event=source.get("event_id") if source else None,
                freshness="current",
                conclusion="declared",
                blocking_scope=block.get("scope") or f"work:{block.get('work_id')}",
                next_safe_action=block.get("unblock_condition") or "satisfy the recorded unblock condition",
                required_loop="governance",
            )
        )
    return facts


def _apply_runtime_recovery_conflicts(
    paths: ProjectPaths,
    facts: dict[str, list[dict[str, Any]]],
) -> None:
    observations: dict[tuple[str, str, str], list[tuple[str, str, dict[str, Any]]]] = {}
    for fact in facts["observed"]:
        if fact.get("evidence_kind") != "runtime-readback" or not isinstance(fact.get("evidence_id"), str):
            continue
        try:
            document = load_evidence(paths, fact["evidence_id"])
        except VoyageError:
            continue
        locator = document.get("locator", {})
        environment_id = locator.get("environment_id")
        target_version = locator.get("target_version")
        fields = locator.get("fields")
        if not isinstance(environment_id, str) or not isinstance(target_version, str) or not isinstance(fields, dict):
            continue
        for field, value in fields.items():
            if not isinstance(field, str):
                continue
            key = (environment_id, target_version, field)
            observations.setdefault(key, []).append((canonical_json(value), fact["evidence_id"], fact))

    conflicted_ids: set[str] = set()
    for (environment_id, target_version, field), items in sorted(observations.items()):
        values = {value for value, _, _ in items}
        if len(values) <= 1:
            continue
        evidence_ids = sorted({evidence_id for _, evidence_id, _ in items})
        source_events = sorted({fact["source_event"] for _, _, fact in items if fact.get("source_event")})
        verified_times = sorted({fact["verified_at"] for _, _, fact in items if fact.get("verified_at")})
        conflicted_ids.update(evidence_ids)
        facts["conflicts"].append(
            _recovery_fact(
                subject=f"environment:{environment_id}",
                claim=f"runtime.field:{field}",
                source_event=",".join(source_events) or None,
                evidence_id=",".join(evidence_ids),
                evidence_kind="runtime-readback",
                verified_at=verified_times[-1] if verified_times else None,
                freshness="fresh",
                conclusion="conflicting-valid-observations",
                blocking_scope=f"environment:{environment_id}/version:{target_version}/field:{field}",
                next_safe_action="run an independent runtime readback and reconcile the conflicting observations",
                required_loop="quality",
            )
        )
    if conflicted_ids:
        facts["observed"] = [item for item in facts["observed"] if item.get("evidence_id") not in conflicted_ids]


def recovery_snapshot(
    paths: ProjectPaths,
    *,
    now: datetime | None = None,
    port_probe=probe_port,
) -> dict[str, Any]:
    checked_at = now or datetime.now(timezone.utc)
    if checked_at.tzinfo is None:
        raise VoyageError("recovery time must include timezone")
    state = current_state(paths)
    bootstrap = truth_status(paths)
    events = load_events(paths.ledger)
    facts = _evidence_recovery_facts(paths, events, state, now=checked_at)
    resource_facts = _resource_recovery_facts(paths, events, state, now=checked_at, port_probe=port_probe)
    state_facts = _current_state_recovery_facts(events, state)
    for bucket in RECOVERY_FACT_BUCKETS:
        facts[bucket].extend(resource_facts[bucket])
        facts[bucket].extend(state_facts[bucket])
    _apply_runtime_recovery_conflicts(paths, facts)
    works = []
    for work in sorted(state["works"].values(), key=lambda item: item["id"]):
        works.append(
            {
                "id": work["id"],
                "title": work["title"],
                "status": work["status"],
                "risk": work["risk"],
                "declared_risk": work.get("declared_risk", work["risk"]),
                "effective_risk": work["risk"],
                "risk_assessment": deepcopy(work.get("risk_assessment")),
                "requirements": deepcopy(RISK_POLICIES[work["risk"]]),
                "missing_controls": _missing_risk_controls(paths, state, work),
                "anchor": work["delivery"]["anchor"] if work.get("delivery") else None,
                "next_safe_action": next_safe_action(work),
            }
        )
    active_blocks = [dict({"id": block_id}, **block) for block_id, block in state["blocks"].items() if block["active"]]
    leases = active_leases(state, now=checked_at)
    for bucket in RECOVERY_FACT_BUCKETS:
        facts[bucket].sort(key=recovery_fact_sort_key)
    return {
        "project_root": str(paths.root),
        "project_stage": bootstrap["project_stage"],
        "bootstrap": bootstrap,
        "validated_at": checked_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "truth_registry": str(paths.truth_registry.relative_to(paths.root)),
        "ledger_head": state["last_event"],
        "work": works,
        "active_leases": leases,
        "active_blocks": active_blocks,
        "rules": state["rules"],
        "volatile_recheck_required": [lease["resource_id"] for lease in leases if lease["stateful"] or lease["expired"]],
        "extensions": extension_status(paths),
        "risk_policy": risk_policy_view(),
        **facts,
    }


def next_safe_action(work: dict[str, Any]) -> str:
    return NEXT_SAFE_ACTIONS.get(work["status"], "inspect unknown state")
