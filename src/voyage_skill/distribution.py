"""Deterministic, commit-bound local distribution artifacts."""

from __future__ import annotations

import base64
import csv
import gzip
import hashlib
import io
import json
import re
import subprocess
import tarfile
import zipfile
from email.parser import Parser
from pathlib import Path
from typing import Any


class DistributionError(ValueError):
    """Raised when a distribution input or artifact is invalid."""


def _run_git(repository: Path, *args: str, text: bool = True) -> Any:
    try:
        return subprocess.run(
            ["git", "-C", str(repository), *args],
            check=False,
            capture_output=True,
            text=text,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DistributionError(f"Git readback failed: {exc}") from exc


def _repository_and_revision(source: Path, revision: str) -> tuple[Path, str]:
    repository = source.expanduser().resolve()
    root = _run_git(repository, "rev-parse", "--show-toplevel")
    if root.returncode != 0 or Path(root.stdout.strip()).resolve() != repository:
        raise DistributionError(f"source is not an exact Git repository root: {repository}")
    resolved = _run_git(repository, "rev-parse", "--verify", f"{revision}^{{commit}}")
    if resolved.returncode != 0:
        raise DistributionError(f"revision is not a readable commit: {revision}")
    commit = resolved.stdout.strip().lower()
    if not re.fullmatch(r"[a-f0-9]{40,64}", commit):
        raise DistributionError(f"revision did not resolve to a full commit: {revision}")
    return repository, commit


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _git_blob(repository: Path, commit: str, path: str) -> bytes:
    result = _run_git(repository, "show", f"{commit}:{path}", text=False)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise DistributionError(f"cannot read {path} from revision {commit}: {stderr.strip()}")
    return result.stdout


def _tracked_files(repository: Path, commit: str) -> list[tuple[str, str, str]]:
    result = _run_git(repository, "ls-tree", "-rz", "--full-tree", commit, text=False)
    if result.returncode != 0:
        raise DistributionError(f"cannot list revision files: {commit}")
    entries: list[tuple[str, str, str]] = []
    for record in result.stdout.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, kind, object_id = metadata.decode("ascii").split(" ")
        if kind != "blob":
            continue
        entries.append((raw_path.decode("utf-8", errors="surrogateescape"), mode, object_id))
    return sorted(entries)


def _version_from_commit(repository: Path, commit: str) -> str:
    content = _git_blob(repository, commit, "src/voyage_skill/__init__.py").decode("utf-8")
    matches = re.findall(r'^__version__\s*=\s*["\']([^"\']+)["\']\s*$', content, flags=re.MULTILINE)
    if len(matches) != 1 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", matches[0]):
        raise DistributionError("revision must declare exactly one valid __version__")
    return matches[0]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record_digest(content: bytes) -> str:
    encoded = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=")
    return "sha256=" + encoded.decode("ascii")


def _zip_info(name: str, epoch: int) -> zipfile.ZipInfo:
    effective = max(int(epoch), 315532800)
    from datetime import datetime, timezone

    timestamp = datetime.fromtimestamp(effective, tz=timezone.utc)
    info = zipfile.ZipInfo(name, timestamp.timetuple()[:6])
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def _build_wheel(repository: Path, commit: str, version: str, destination: Path, epoch: int) -> Path:
    normalized = version.replace("-", "_")
    dist_info = f"voyage_skill-{normalized}.dist-info"
    wheel = destination / f"voyage_skill-{normalized}-py3-none-any.whl"
    entries: dict[str, bytes] = {}
    tracked = _tracked_files(repository, commit)
    for path, _, _ in tracked:
        if path.startswith("src/voyage_skill/") and path.endswith(".py"):
            entries[path.removeprefix("src/")] = _git_blob(repository, commit, path)
    if "voyage_skill/__init__.py" not in entries or "voyage_skill/cli.py" not in entries:
        raise DistributionError("revision is missing required runtime package files")
    entries[f"{dist_info}/METADATA"] = (
        "Metadata-Version: 2.1\n"
        "Name: voyage-skill\n"
        f"Version: {version}\n"
        "Summary: Verifiable operating control for multi-agent software projects\n"
        "License: MIT\n"
        "Requires-Python: >=3.9\n\n"
    ).encode("utf-8")
    entries[f"{dist_info}/WHEEL"] = (
        "Wheel-Version: 1.0\n"
        "Generator: voyage-skill deterministic builder\n"
        "Root-Is-Purelib: true\n"
        "Tag: py3-none-any\n"
    ).encode("utf-8")
    entries[f"{dist_info}/entry_points.txt"] = b"[console_scripts]\nvoyage = voyage_skill.cli:main\n"
    entries[f"{dist_info}/licenses/LICENSE"] = _git_blob(repository, commit, "LICENSE")
    record_name = f"{dist_info}/RECORD"
    record_rows = [f"{name},{_record_digest(content)},{len(content)}" for name, content in sorted(entries.items())]
    record_rows.append(f"{record_name},,")
    entries[record_name] = ("\n".join(record_rows) + "\n").encode("utf-8")
    with zipfile.ZipFile(wheel, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in sorted(entries.items()):
            archive.writestr(_zip_info(name, epoch), content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return wheel


def _build_source(repository: Path, commit: str, version: str, destination: Path, epoch: int) -> Path:
    archive_path = destination / f"voyage-skill-{version}.tar.gz"
    prefix = f"voyage-skill-{version}"
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for path, mode, object_id in _tracked_files(repository, commit):
            content = _git_blob(repository, commit, path)
            info = tarfile.TarInfo(f"{prefix}/{path}")
            info.mtime = int(epoch)
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            if mode == "120000":
                info.type = tarfile.SYMTYPE
                info.mode = 0o777
                info.linkname = content.decode("utf-8", errors="surrogateescape")
                info.size = 0
                archive.addfile(info)
            else:
                info.mode = 0o755 if mode == "100755" else 0o644
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
        manifest = json.dumps(
            {
                "schema_version": 1,
                "project": "voyage-skill",
                "version": version,
                "revision": commit,
                "test_material": ["tests/fixtures/history/"],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        info = tarfile.TarInfo(f"{prefix}/VOYAGE-SOURCE.json")
        info.mtime = int(epoch)
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        info.mode = 0o644
        info.size = len(manifest)
        archive.addfile(info, io.BytesIO(manifest))
    with archive_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=int(epoch)) as compressed:
            compressed.write(tar_buffer.getvalue())
    return archive_path


def build_artifacts(
    source: str | Path,
    output: str | Path,
    *,
    revision: str = "HEAD",
    source_date_epoch: int = 0,
) -> dict[str, Any]:
    repository, commit = _repository_and_revision(Path(source), revision)
    destination = Path(output).expanduser().resolve()
    if _inside(repository, destination):
        raise DistributionError("artifact output must be outside the source tree")
    if source_date_epoch < 0:
        raise DistributionError("source_date_epoch must be non-negative")
    version = _version_from_commit(repository, commit)
    destination.mkdir(parents=True, exist_ok=False)
    try:
        wheel = _build_wheel(repository, commit, version, destination, source_date_epoch)
        source_archive = _build_source(repository, commit, version, destination, source_date_epoch)
        wheel_info = inspect_wheel(wheel)
    except Exception:
        for item in destination.iterdir():
            if item.is_file():
                item.unlink()
        destination.rmdir()
        raise
    return {
        "schema_version": 1,
        "revision": commit,
        "version": version,
        "source_date_epoch": source_date_epoch,
        "wheel": {"path": str(wheel), "sha256": wheel_info["sha256"], "bytes": wheel.stat().st_size},
        "source": {"path": str(source_archive), "sha256": _sha256(source_archive), "bytes": source_archive.stat().st_size},
    }


def inspect_wheel(path: str | Path, *, expected_sha256: str | None = None) -> dict[str, Any]:
    wheel = Path(path).expanduser().resolve()
    digest = _sha256(wheel)
    if expected_sha256 is not None and digest != expected_sha256:
        raise DistributionError("wheel digest does not match expected sha256")
    try:
        with zipfile.ZipFile(wheel, mode="r") as archive:
            names = archive.namelist()
            record_names = [name for name in names if name.endswith(".dist-info/RECORD")]
            metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
            entry_names = [name for name in names if name.endswith(".dist-info/entry_points.txt")]
            if len(record_names) != 1:
                raise DistributionError("wheel must contain exactly one RECORD")
            if len(metadata_names) != 1 or len(entry_names) != 1:
                raise DistributionError("wheel metadata or entry point is incomplete")
            record_name = record_names[0]
            rows = list(csv.reader(io.StringIO(archive.read(record_name).decode("utf-8"))))
            declared = {row[0]: row for row in rows if len(row) == 3}
            if set(declared) != set(names):
                raise DistributionError("wheel RECORD does not cover every file")
            for name in names:
                row = declared[name]
                if name == record_name:
                    if row[1:] != ["", ""]:
                        raise DistributionError("wheel RECORD self-entry is invalid")
                    continue
                content = archive.read(name)
                if row[1] != _record_digest(content) or row[2] != str(len(content)):
                    raise DistributionError(f"wheel RECORD digest or size mismatch: {name}")
            entrypoint_lines = [line.strip() for line in archive.read(entry_names[0]).decode("utf-8").splitlines()]
            expected_entry = "voyage = voyage_skill.cli:main"
            if expected_entry not in entrypoint_lines:
                raise DistributionError("wheel entry point is invalid")
            metadata = Parser().parsestr(archive.read(metadata_names[0]).decode("utf-8"))
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, KeyError) as exc:
        raise DistributionError(f"invalid wheel: {exc}") from exc
    return {
        "schema_version": 1,
        "path": str(wheel),
        "sha256": digest,
        "bytes": wheel.stat().st_size,
        "files": names,
        "name": metadata.get("Name"),
        "version": metadata.get("Version"),
        "requires_python": metadata.get("Requires-Python"),
        "requires_dist": metadata.get_all("Requires-Dist") or [],
        "entrypoint": expected_entry,
    }
