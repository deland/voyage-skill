from __future__ import annotations

import fcntl
import hashlib
import json
import os
import socket
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
RISK_LEVELS = {"light", "standard", "strict"}
STATEFUL_RESOURCE_TYPES = {"account", "environment", "session", "window", "quota"}
ALLOWED_RESOURCE_TYPES = {"file", "account", "port", "environment", "session", "window", "quota"}
ALLOWED_RESOURCE_MODES = {"exclusive", "shared-read", "serialized", "rebuildable"}


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


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


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

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
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
        "node_types": [
            "project", "principal", "loop-binding", "truth-source", "decision",
            "work-item", "delivery", "immutable-anchor", "evidence", "gate",
            "resource", "lease", "environment", "channel", "rule", "block",
            "external-anchor",
        ],
        "edge_types": [
            "governs", "depends-on", "authorized-by", "bound-to-loop", "assigned-to",
            "delivered-via", "acknowledged-by", "claims", "releases", "produces",
            "anchored-at", "validated-by", "rejects", "blocks", "unblocks",
            "supersedes", "retires", "readback-of", "escalates-to",
        ],
        "loops": sorted(LOOPS - {"user", "system"}),
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
                {"id": "product", "domain": "product", "path": "docs/voyage/product.md", "version": "1", "status": "active"},
                {"id": "governance", "domain": "governance", "path": "docs/voyage/governance.md", "version": "1", "status": "active"},
                {"id": "system", "domain": "system", "path": "docs/voyage/system.md", "version": "1", "status": "active"},
                {"id": "operations", "domain": "operations", "path": "docs/voyage/operations.md", "version": "1", "status": "active"},
            ],
            "non_authoritative": ["docs/research/", "conversation memory", "worker summaries"],
        }
        atomic_write_json(registry_target, truth_registry)
        contract_bodies = {
            "product.md": (
                "# Product contract\n\n- Status: active\n- Version: 1\n\n"
                "Authorize only explicit work items with scope, non-goals, risk, and acceptance criteria. "
                "Treat User decisions and real outcomes as external product anchors.\n"
            ),
            "governance.md": (
                "# Governance contract\n\n- Status: active\n- Version: 1\n\n"
                "Keep execution, final quality, governance, and audit permissions independent. "
                "Require recorded User decisions for strict-risk work.\n"
            ),
            "system.md": (
                "# System contract\n\n- Status: active\n- Version: 1\n\n"
                "Use `.voyage/graph.json`, hash-chained ledger events, immutable delivery anchors, "
                "registered resources, and mandatory gates as the machine-checkable runtime model.\n"
            ),
            "operations.md": (
                "# Operations runbook\n\n- Status: active\n- Version: 1\n\n"
                "Run `voyage validate` and `voyage recover` before resuming work. "
                "Append runtime facts through the CLI and re-probe volatile resources before dispatch.\n"
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
        payload={"schema_version": SCHEMA_VERSION},
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
    return errors


def _initial_state() -> dict[str, Any]:
    return {
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


def _work(state: dict[str, Any], work_id: str) -> dict[str, Any]:
    work = state["works"].get(work_id)
    if work is None:
        raise VoyageError(f"unknown work item: {work_id}")
    return work


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

        if event_type == "project.initialized":
            _require(loop == "system", "project initialization requires system loop")

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
            state["works"][subject] = {
                "id": subject,
                "title": payload["title"],
                "scope": payload["scope"],
                "acceptance": payload["acceptance"],
                "non_goals": payload.get("non_goals", []),
                "dependencies": dependencies,
                "required_resources": payload.get("required_resources", []),
                "risk": event["risk"],
                "status": "draft",
                "delivery": None,
                "quality_actor": None,
                "previous_status": None,
            }

        elif event_type == "work.authorized":
            _require(loop == "governance", "work authorization requires governance loop")
            work = _work(state, subject)
            _require(work["status"] == "draft", f"work {subject} is not draft")
            if work["risk"] == "strict":
                _require(bool(event.get("authorization")), "strict work requires User authorization")
                _require(event["authorization"] in state["decisions"], "strict work authorization must reference a recorded User decision")
            work["authorization"] = event.get("authorization")
            work["status"] = "authorized"

        elif event_type == "work.started":
            _require(loop == "execution", "work start requires execution loop")
            work = _work(state, subject)
            _require(work["status"] in {"authorized", "rejected"}, f"work {subject} cannot start from {work['status']}")
            held_resources = {
                lease["resource_id"]
                for lease in state["leases"].values()
                if lease["active"] and lease["work_id"] == subject and lease["holder"] == actor
            }
            missing_resources = set(work["required_resources"]) - held_resources
            _require(not missing_resources, f"work {subject} has unclaimed resources: {', '.join(sorted(missing_resources))}")
            work["status"] = "active"
            work["executor"] = actor

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
            work["delivery"] = {"anchor": anchor, "actor": actor, "attempt": attempt, "event_id": event["event_id"]}
            work["quality_actor"] = None
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
                "actor": actor,
                "counts": counts,
            }
            work["status"] = "quality-passed" if verdict == "pass" else "rejected"

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
            state["gates"].setdefault(subject, {})[gate_id] = {"verdict": verdict, "anchor": anchor, "actor": actor, "counts": counts}

        elif event_type == "work.accepted":
            _require(loop == "governance", "work acceptance requires governance loop")
            work = _work(state, subject)
            _require(work["status"] == "quality-passed", f"work {subject} has not passed quality")
            current_anchor = work["delivery"]["anchor"]
            work_gates = state["gates"].get(subject, {})
            for gate_id, definition in gate_defs.items():
                if not definition.get("mandatory", False):
                    continue
                result = work_gates.get(gate_id)
                _require(result is not None, f"mandatory gate missing: {gate_id}")
                _require(result["anchor"] == current_anchor, f"mandatory gate {gate_id} targets stale anchor")
                _require(result["verdict"] == "pass", f"mandatory gate failed: {gate_id}")
            work["status"] = "accepted"

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
            _require(work["status"] not in {"closed", "canceled", "blocked"}, f"work {subject} cannot be blocked from {work['status']}")
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
            _require(decision in state["decisions"], "work resume must reference a recorded User decision")
            work["authorization"] = decision
            work["status"] = work.get("previous_status") or "authorized"
            work["previous_status"] = None

        elif event_type == "resource.claimed":
            resource_id = payload.get("resource_id")
            lease_id = payload.get("lease_id")
            _require(loop == "execution", "resource claim requires execution loop")
            _require(resource_id in resource_defs, f"unknown resource: {resource_id}")
            _require(lease_id and lease_id not in state["leases"], "resource claim requires a unique lease ID")
            _work(state, payload.get("work_id", ""))
            work = _work(state, payload["work_id"])
            definition = resource_defs[resource_id]
            if definition.get("risk") == "strict" or work["risk"] == "strict":
                _require(work.get("authorization") in state["decisions"], f"strict resource {resource_id} requires recorded User authorization")
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
            }

        elif event_type in {"resource.released", "resource.recovered"}:
            lease_id = payload.get("lease_id")
            lease = state["leases"].get(lease_id)
            _require(lease is not None and lease["active"], f"active lease not found: {lease_id}")
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
            state["rules"][subject] = {"status": "proposed", "proposer": actor, "approver": None, "applier": None, "verifier": None}

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
            rule.update(status="applied", applier=actor)

        elif event_type == "rule.verified":
            _require(loop in {"quality", "audit"}, "rule verification requires quality or audit loop")
            rule = state["rules"].get(subject)
            _require(rule and rule["status"] == "applied", f"rule {subject} is not applied")
            _require(actor != rule["applier"], "rule applier cannot verify effectiveness")
            _require(bool(evidence), "rule verification requires evidence")
            rule.update(status="active", verifier=actor)

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
                state["decisions"][subject] = {"actor": actor, "event_id": event["event_id"], "payload": payload}
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
        resources = load_json(paths.resources)
        gates = load_json(paths.gates)
        replay_events(events + [event], resources=resources, gates=gates)
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


def validate_project(paths: ProjectPaths) -> list[str]:
    errors: list[str] = []
    try:
        manifest = load_json(paths.manifest)
        if manifest.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"unsupported manifest schema: {manifest.get('schema_version')}")
        registry = load_json(paths.truth_registry)
        if registry.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"unsupported truth registry schema: {registry.get('schema_version')}")
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
            replay_events(events, resources=resources, gates=gates)
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
    return replay_events(events, resources=load_json(paths.resources), gates=load_json(paths.gates))


def active_leases(state: dict[str, Any]) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    result = []
    for lease in state["leases"].values():
        if not lease["active"]:
            continue
        item = deepcopy(lease)
        try:
            item["expired"] = parse_time(lease["expires_at"]) <= now
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


def recovery_snapshot(paths: ProjectPaths) -> dict[str, Any]:
    state = current_state(paths)
    works = []
    for work in sorted(state["works"].values(), key=lambda item: item["id"]):
        works.append(
            {
                "id": work["id"],
                "title": work["title"],
                "status": work["status"],
                "risk": work["risk"],
                "anchor": work["delivery"]["anchor"] if work.get("delivery") else None,
                "next_safe_action": next_safe_action(work),
            }
        )
    active_blocks = [dict({"id": block_id}, **block) for block_id, block in state["blocks"].items() if block["active"]]
    return {
        "project_root": str(paths.root),
        "validated_at": utc_now(),
        "truth_registry": str(paths.truth_registry.relative_to(paths.root)),
        "ledger_head": state["last_event"],
        "work": works,
        "active_leases": active_leases(state),
        "active_blocks": active_blocks,
        "rules": state["rules"],
        "volatile_recheck_required": [lease["resource_id"] for lease in active_leases(state) if lease["stateful"] or lease["expired"]],
    }


def next_safe_action(work: dict[str, Any]) -> str:
    return {
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
        "canceled": "none",
        "superseded": "follow superseding work item",
    }.get(work["status"], "inspect unknown state")
