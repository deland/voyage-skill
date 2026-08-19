"""Deterministic local release evidence; never an external publication action."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

from .distribution import DistributionError, inspect_wheel


RELEASE_SCHEMA_VERSION = 1
REQUIRED_CHECKS = (
    "dogfood-validation",
    "external-journeys",
    "repository-tests",
    "skill-validation",
    "upgrade-recovery",
)


class ReleaseEvidenceError(RuntimeError):
    """A local candidate input or report cannot be verified."""


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _exact_commit(source: Path, revision: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", revision):
        raise ReleaseEvidenceError("release revision must be a full hexadecimal commit")
    result = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "--verify", f"{revision}^{{commit}}"],
        check=False,
        text=True,
        capture_output=True,
        timeout=10,
    )
    if result.returncode != 0 or result.stdout.strip().lower() != revision.lower():
        raise ReleaseEvidenceError("release revision is not an exact readable source commit")
    top = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "--show-toplevel"],
        check=False,
        text=True,
        capture_output=True,
        timeout=10,
    )
    if top.returncode != 0 or Path(top.stdout.strip()).resolve() != source:
        raise ReleaseEvidenceError("release source must be the exact Git worktree root")
    return revision.lower()


def _one_artifact(directory: Path, pattern: str, label: str) -> Path:
    matches = sorted(path for path in directory.glob(pattern) if path.is_file())
    if len(matches) != 1:
        raise ReleaseEvidenceError(f"artifact directory must contain exactly one {label}")
    return matches[0]


def _source_contract(path: Path) -> dict[str, Any]:
    try:
        with tarfile.open(path, "r:gz") as archive:
            names = [name for name in archive.getnames() if name.endswith("VOYAGE-SOURCE.json")]
            if len(names) != 1:
                raise ReleaseEvidenceError("source archive must contain exactly one VOYAGE-SOURCE.json")
            handle = archive.extractfile(names[0])
            if handle is None:
                raise ReleaseEvidenceError("source archive manifest is unreadable")
            body = json.loads(handle.read())
    except (OSError, tarfile.TarError, json.JSONDecodeError) as exc:
        raise ReleaseEvidenceError(f"invalid source archive: {exc}") from exc
    expected = {"schema_version", "project", "version", "revision", "test_material"}
    if set(body) != expected or body.get("schema_version") != 1 or body.get("project") != "voyage-skill":
        raise ReleaseEvidenceError("source archive manifest contract is invalid")
    if body.get("test_material") != ["tests/fixtures/history/"]:
        raise ReleaseEvidenceError("source archive test material classification is invalid")
    return body


def _descriptor(path: Path) -> dict[str, Any]:
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": _sha256(path)}


def _artifact_inputs(source: Path, directory: Path, revision: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
    if not directory.is_dir():
        raise ReleaseEvidenceError("artifact directory does not exist")
    wheel = _one_artifact(directory, "*.whl", "wheel")
    source_archive = _one_artifact(directory, "*.tar.gz", "source archive")
    try:
        wheel_readback = inspect_wheel(wheel)
    except DistributionError as exc:
        raise ReleaseEvidenceError(str(exc)) from exc
    source_readback = _source_contract(source_archive)
    version = wheel_readback.get("version")
    if not isinstance(version, str) or not version:
        raise ReleaseEvidenceError("wheel package version is missing")
    if source_readback["revision"] != revision:
        raise ReleaseEvidenceError("source archive revision does not match release revision")
    if source_readback["version"] != version:
        raise ReleaseEvidenceError("wheel and source package versions do not match")
    return version, {"wheel": _descriptor(wheel), "source": _descriptor(source_archive)}, source_readback


def _counts(value: Any, check_id: str) -> dict[str, int]:
    keys = ("total", "passed", "failed", "skipped", "unknown")
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ReleaseEvidenceError(f"check {check_id} counts contract is incomplete")
    if any(not isinstance(value[key], int) or isinstance(value[key], bool) or value[key] < 0 for key in keys):
        raise ReleaseEvidenceError(f"check {check_id} counts must be non-negative integers")
    if sum(value[key] for key in keys[1:]) != value["total"] or value["total"] <= 0:
        raise ReleaseEvidenceError(f"check {check_id} counts are inconsistent")
    if value["passed"] != value["total"] or any(value[key] for key in ("failed", "skipped", "unknown")):
        raise ReleaseEvidenceError(f"check {check_id} is not complete pass")
    return {key: value[key] for key in keys}


def _check_inputs(path: Path, revision: str) -> list[dict[str, Any]]:
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseEvidenceError(f"invalid check bundle: {exc}") from exc
    if body.get("schema_version") != 1 or body.get("revision") != revision or not isinstance(body.get("checks"), list):
        raise ReleaseEvidenceError("check bundle schema or revision is invalid")
    by_id: dict[str, dict[str, Any]] = {}
    for item in body["checks"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ReleaseEvidenceError("every release check requires an ID")
        check_id = item["id"]
        if check_id in by_id:
            raise ReleaseEvidenceError(f"duplicate release check: {check_id}")
        command = item.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(arg, str) and arg for arg in command):
            raise ReleaseEvidenceError(f"check {check_id} command is invalid")
        if item.get("exit_code") != 0:
            raise ReleaseEvidenceError(f"check {check_id} exit code is not zero")
        counts = _counts(item.get("counts"), check_id)
        output = item.get("output")
        if not isinstance(output, dict) or set(output) != {"path", "bytes", "sha256"}:
            raise ReleaseEvidenceError(f"check {check_id} output descriptor is invalid")
        relative = output.get("path")
        if not isinstance(relative, str) or not relative or Path(relative).name != relative:
            raise ReleaseEvidenceError(f"check {check_id} output must be one file beside the bundle")
        target = path.parent / relative
        if not target.is_file():
            raise ReleaseEvidenceError(f"check {check_id} raw output is missing")
        if output.get("bytes") != target.stat().st_size or output.get("sha256") != _sha256(target):
            raise ReleaseEvidenceError(f"check {check_id} raw output digest or size does not match")
        by_id[check_id] = {
            "id": check_id,
            "command": list(command),
            "exit_code": 0,
            "counts": counts,
            "output": {"name": relative, "bytes": target.stat().st_size, "sha256": _sha256(target)},
        }
    if set(by_id) != set(REQUIRED_CHECKS):
        missing = sorted(set(REQUIRED_CHECKS) - set(by_id))
        extra = sorted(set(by_id) - set(REQUIRED_CHECKS))
        raise ReleaseEvidenceError(f"release checks do not match required set; missing={missing}, extra={extra}")
    return [by_id[check_id] for check_id in REQUIRED_CHECKS]


def _interpreter() -> dict[str, str]:
    return {
        "implementation": platform.python_implementation(),
        "version": platform.python_version(),
        "platform": f"{sys.platform}-{platform.machine()}",
    }


def _body(source: Path, artifacts: Path, checks: Path, revision: str) -> dict[str, Any]:
    commit = _exact_commit(source, revision)
    version, artifact_data, source_contract = _artifact_inputs(source, artifacts, commit)
    return {
        "schema_version": RELEASE_SCHEMA_VERSION,
        "kind": "voyage-local-release-evidence",
        "revision": commit,
        "version": version,
        "artifacts": artifact_data,
        "source_contract": source_contract,
        "interpreter": _interpreter(),
        "checks": _check_inputs(checks, commit),
        "authority": "local-evidence-only-user-authorization-required-for-publication",
    }


def create_release_evidence(
    source: str | Path,
    artifacts: str | Path,
    checks: str | Path,
    output: str | Path,
    *,
    revision: str,
) -> dict[str, Any]:
    repository = Path(source).expanduser().resolve()
    artifact_dir = Path(artifacts).expanduser().resolve()
    checks_path = Path(checks).expanduser().resolve()
    destination = Path(output).expanduser().resolve()
    if _inside(repository, destination):
        raise ReleaseEvidenceError("release evidence output must be outside the source tree")
    if destination.exists():
        raise ReleaseEvidenceError("release evidence output directory must not exist")
    body = _body(repository, artifact_dir, checks_path, revision)
    digest = hashlib.sha256(_canonical(body)).hexdigest()
    manifest = dict(body, manifest_id=f"sha256:{digest}")
    destination.mkdir(parents=True, exist_ok=False)
    path = destination / f"voyage-release-{digest}.json"
    path.write_bytes(_canonical(manifest))
    return {"manifest_id": manifest["manifest_id"], "path": str(path), "revision": body["revision"], "version": body["version"]}


def verify_release_evidence(
    manifest: str | Path,
    source: str | Path,
    artifacts: str | Path,
    checks: str | Path,
) -> dict[str, Any]:
    path = Path(manifest).expanduser().resolve()
    try:
        recorded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseEvidenceError(f"invalid release manifest: {exc}") from exc
    manifest_id = recorded.get("manifest_id")
    if not isinstance(manifest_id, str) or not manifest_id.startswith("sha256:"):
        raise ReleaseEvidenceError("release manifest has no content address")
    body = {key: value for key, value in recorded.items() if key != "manifest_id"}
    expected_digest = hashlib.sha256(_canonical(body)).hexdigest()
    if manifest_id != f"sha256:{expected_digest}" or path.name != f"voyage-release-{expected_digest}.json":
        raise ReleaseEvidenceError("release manifest content address or filename does not match")
    if body.get("schema_version") != RELEASE_SCHEMA_VERSION or body.get("kind") != "voyage-local-release-evidence":
        raise ReleaseEvidenceError("release manifest contract is invalid")
    expected = _body(
        Path(source).expanduser().resolve(),
        Path(artifacts).expanduser().resolve(),
        Path(checks).expanduser().resolve(),
        body.get("revision", ""),
    )
    if body != expected:
        if body.get("version") != expected.get("version"):
            raise ReleaseEvidenceError("release package version does not match live artifacts")
        raise ReleaseEvidenceError("release manifest fields do not match immutable input readback")
    return {
        "valid": True,
        "manifest_id": manifest_id,
        "revision": body["revision"],
        "version": body["version"],
        "checks": {item["id"]: "pass" for item in body["checks"]},
        "authority": body["authority"],
    }
