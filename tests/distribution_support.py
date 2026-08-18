"""Standard-library black-box distribution test support for PLAN-0002."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Mapping, Sequence


@dataclass(frozen=True)
class BlackBoxResult:
    argv: tuple[str, ...]
    exit_code: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _archive_members_are_safe(archive: tarfile.TarFile, destination: Path) -> bool:
    root = destination.resolve()
    for member in archive.getmembers():
        target = (root / member.name).resolve()
        if not _inside(root, target):
            return False
        if member.issym() or member.islnk():
            link_target = (target.parent / member.linkname).resolve()
            if not _inside(root, link_target):
                return False
    return True


def isolated_source_copy(repository: Path, destination: Path, revision: str) -> Path:
    source = repository.resolve()
    target = destination.resolve()
    if target.exists() and any(target.iterdir()):
        raise ValueError(f"distribution destination is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="voyage-source-archive-") as temporary:
        archive_path = Path(temporary) / "source.tar"
        result = subprocess.run(
            ["git", "-C", str(source), "archive", "--format=tar", "--output", str(archive_path), revision],
            check=False,
            text=True,
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"cannot archive source revision {revision}: {result.stderr.strip()}")
        with tarfile.open(archive_path, mode="r:") as archive:
            if not _archive_members_are_safe(archive, target):
                raise RuntimeError("source archive contains an unsafe path")
            archive.extractall(target)
    return target


def sanitized_environment(base: Mapping[str, str] | None = None) -> dict[str, str]:
    environment = dict(os.environ if base is None else base)
    for key in ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONUSERBASE", "VIRTUAL_ENV"):
        environment.pop(key, None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONNOUSERSITE"] = "1"
    return environment


def run_black_box(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout: float,
) -> BlackBoxResult:
    command = tuple(str(item) for item in argv)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=dict(env),
            check=False,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        duration = time.monotonic() - started
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        stderr += f"process timed out after {timeout} seconds\n"
        return BlackBoxResult(command, None, stdout, stderr, duration, True)
    return BlackBoxResult(
        command,
        completed.returncode,
        completed.stdout,
        completed.stderr,
        time.monotonic() - started,
        False,
    )


def tree_snapshot(root: Path) -> dict[str, str]:
    base = root.resolve()
    snapshot: dict[str, str] = {}
    for path in sorted(base.rglob("*")):
        relative = path.relative_to(base).as_posix()
        if path.is_symlink():
            payload = f"symlink:{os.readlink(path)}".encode("utf-8")
        elif path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            payload = f"file:{digest.hexdigest()}".encode("ascii")
        else:
            continue
        snapshot[relative] = hashlib.sha256(payload).hexdigest()
    return snapshot


@contextmanager
def temporary_distribution_workspace(repository: Path) -> Iterator[Path]:
    source = repository.resolve()
    with tempfile.TemporaryDirectory(prefix="voyage-distribution-") as directory:
        workspace = Path(directory).resolve()
        if _inside(source, workspace):
            raise RuntimeError("temporary distribution workspace is inside the repository")
        yield workspace
