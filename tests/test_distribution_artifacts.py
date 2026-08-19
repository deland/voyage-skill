from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from tests.distribution_support import run_black_box, sanitized_environment, tree_snapshot


REPOSITORY = Path(__file__).resolve().parents[1]
RUNBOOK = REPOSITORY / "docs" / "operations" / "runbook.md"


def distribution_module():
    return importlib.import_module("voyage_skill.distribution")


def committed_source(parent: Path) -> tuple[Path, str]:
    source = parent / "source"
    shutil.copytree(
        REPOSITORY,
        source,
        ignore=shutil.ignore_patterns(".git", ".worktrees", "__pycache__", "*.pyc", "*.pyo", "build", "dist", "*.egg-info"),
    )
    environment = dict(os.environ)
    environment.update({"GIT_AUTHOR_NAME": "Voyage Test", "GIT_AUTHOR_EMAIL": "voyage@example.invalid", "GIT_COMMITTER_NAME": "Voyage Test", "GIT_COMMITTER_EMAIL": "voyage@example.invalid"})
    for argv in (["git", "init", "-q"], ["git", "add", "."], ["git", "commit", "-q", "-m", "fixture"]):
        subprocess.run(argv, cwd=source, env=environment, check=True, text=True, capture_output=True)
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=source, check=True, text=True, capture_output=True).stdout.strip()
    return source, revision


def build_fixture(root: Path, *, epoch: int = 0) -> tuple[Path, str, Path, dict]:
    source, revision = committed_source(root)
    output = root / "artifacts"
    result = distribution_module().build_artifacts(source, output, revision=revision, source_date_epoch=epoch)
    return source, revision, output, result


def create_venv(root: Path) -> Path:
    venv = root / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, text=True, capture_output=True)
    return venv


class ArtifactBuildTests(unittest.TestCase):
    def test_cli_version_matches_module_and_package_metadata(self) -> None:
        expected = re.search(r'^__version__\s*=\s*["\']([^"\']+)', (REPOSITORY / "src" / "voyage_skill" / "__init__.py").read_text(encoding="utf-8"), re.MULTILINE).group(1)
        env = sanitized_environment()
        with tempfile.TemporaryDirectory() as directory:
            cwd = Path(directory)
            script = run_black_box([sys.executable, str(REPOSITORY / "scripts" / "voyage.py"), "--version"], cwd=cwd, env=env, timeout=10)
            module_env = dict(env)
            module_env["PYTHONPATH"] = str(REPOSITORY / "src")
            module = run_black_box([sys.executable, "-m", "voyage_skill", "--version"], cwd=cwd, env=module_env, timeout=10)
        self.assertEqual(script.exit_code, 0, script.stderr)
        self.assertEqual(module.exit_code, 0, module.stderr)
        self.assertEqual(script.stdout.strip(), f"voyage {expected}")
        self.assertEqual(module.stdout, script.stdout)

    def test_builder_emits_wheel_and_source_archive_outside_source_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, revision = committed_source(root)
            output = root / "artifacts"
            result = run_black_box(
                [sys.executable, str(source / "scripts" / "voyage-build.py"), "--source", str(source), "--output", str(output), "--revision", revision, "--source-date-epoch", "0"],
                cwd=root,
                env=sanitized_environment(),
                timeout=30,
            )
            self.assertEqual(result.exit_code, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["revision"], revision)
            self.assertEqual({Path(payload[key]["path"]).suffix for key in ("wheel", "source")}, {".whl", ".gz"})
            self.assertTrue(all(Path(payload[key]["path"]).resolve().is_relative_to(output.resolve()) for key in ("wheel", "source")))

    def test_repeated_builds_are_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, revision = committed_source(root)
            first = distribution_module().build_artifacts(source, root / "one", revision=revision, source_date_epoch=0)
            second = distribution_module().build_artifacts(source, root / "two", revision=revision, source_date_epoch=0)
            self.assertEqual(first["wheel"]["sha256"], second["wheel"]["sha256"])
            self.assertEqual(first["source"]["sha256"], second["source"]["sha256"])

    def test_wheel_contains_only_runtime_license_metadata_and_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, _, _, built = build_fixture(Path(directory))
            wheel = Path(built["wheel"]["path"])
            inspected = distribution_module().inspect_wheel(wheel, expected_sha256=built["wheel"]["sha256"])
            names = set(inspected["files"])
            self.assertTrue(any(name.endswith(".dist-info/METADATA") for name in names))
            self.assertTrue(any(name.endswith(".dist-info/WHEEL") for name in names))
            self.assertTrue(any(name.endswith(".dist-info/RECORD") for name in names))
            self.assertTrue(any(name.endswith(".dist-info/entry_points.txt") for name in names))
            self.assertTrue(any("licenses/LICENSE" in name for name in names))
            for forbidden in ("tests/", "docs/", ".voyage/", "research", "release-manifest"):
                self.assertFalse(any(forbidden in name for name in names), forbidden)
            self.assertEqual(inspected["entrypoint"], "voyage = voyage_skill.cli:main")
            self.assertEqual(inspected["requires_dist"], [])

    def test_source_archive_is_commit_bound_and_excludes_worktree_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, revision = committed_source(root)
            (source / "uncommitted-sentinel").write_text("must not ship", encoding="utf-8")
            built = distribution_module().build_artifacts(source, root / "artifacts", revision=revision, source_date_epoch=0)
            with tarfile.open(built["source"]["path"], "r:gz") as archive:
                names = archive.getnames()
                manifest_name = next(name for name in names if name.endswith("VOYAGE-SOURCE.json"))
                manifest = json.loads(archive.extractfile(manifest_name).read())
            self.assertEqual(manifest["revision"], revision)
            self.assertFalse(any(name.endswith("uncommitted-sentinel") for name in names))


class ArtifactInstallTests(unittest.TestCase):
    def test_wheel_installs_offline_without_dependencies_in_clean_venv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, _, built = build_fixture(root)
            venv = create_venv(root)
            python = venv / "bin" / "python"
            installed = subprocess.run([str(python), "-m", "pip", "install", "--no-index", "--no-deps", built["wheel"]["path"]], text=True, capture_output=True)
            self.assertEqual(installed.returncode, 0, installed.stderr)
            metadata = subprocess.run([str(python), "-c", "import importlib.metadata as m; d=m.metadata('voyage-skill'); print(d.get_all('Requires-Dist') or [])"], text=True, capture_output=True, check=True)
            self.assertEqual(metadata.stdout.strip(), "[]")

    def test_installed_console_runs_from_unrelated_cwd_without_pythonpath(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, _, built = build_fixture(root)
            venv = create_venv(root)
            subprocess.run([str(venv / "bin" / "python"), "-m", "pip", "install", "--no-index", "--no-deps", built["wheel"]["path"]], check=True, text=True, capture_output=True)
            cwd = root / "unrelated"
            cwd.mkdir()
            result = run_black_box([str(venv / "bin" / "voyage"), "--help"], cwd=cwd, env=sanitized_environment(), timeout=10)
            self.assertEqual(result.exit_code, 0, result.stderr)
            self.assertIn("usage: voyage", result.stdout)

    def test_installed_console_and_module_report_identical_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, _, built = build_fixture(root)
            venv = create_venv(root)
            python = venv / "bin" / "python"
            subprocess.run([str(python), "-m", "pip", "install", "--no-index", "--no-deps", built["wheel"]["path"]], check=True, text=True, capture_output=True)
            cwd = root / "cwd"
            cwd.mkdir()
            console = run_black_box([str(venv / "bin" / "voyage"), "--version"], cwd=cwd, env=sanitized_environment(), timeout=10)
            module = run_black_box([str(python), "-m", "voyage_skill", "--version"], cwd=cwd, env=sanitized_environment(), timeout=10)
            self.assertEqual(console.exit_code, 0, console.stderr)
            self.assertEqual(module.exit_code, 0, module.stderr)
            self.assertEqual(console.stdout, module.stdout)

    def test_installed_cli_initializes_validates_and_recovers_external_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, _, built = build_fixture(root)
            venv = create_venv(root)
            python = venv / "bin" / "python"
            subprocess.run([str(python), "-m", "pip", "install", "--no-index", "--no-deps", built["wheel"]["path"]], check=True, text=True, capture_output=True)
            project = root / "external-project"
            project.mkdir()
            cli = str(venv / "bin" / "voyage")
            for argv in ([cli, "--root", str(project), "init", "--project-id", "external"], [cli, "--root", str(project), "validate"], [cli, "--root", str(project), "recover"]):
                result = run_black_box(argv, cwd=root, env=sanitized_environment(), timeout=15)
                self.assertEqual(result.exit_code, 0, result.stderr)
                self.assertIsInstance(json.loads(result.stdout), dict)
            self.assertEqual(json.loads(result.stdout)["project_stage"], "bootstrap")

    def test_build_and_install_leave_source_tree_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, revision = committed_source(root)
            before = tree_snapshot(source)
            built = distribution_module().build_artifacts(source, root / "artifacts", revision=revision, source_date_epoch=0)
            venv = create_venv(root)
            subprocess.run([str(venv / "bin" / "python"), "-m", "pip", "install", "--no-index", "--no-deps", built["wheel"]["path"]], check=True, text=True, capture_output=True)
            self.assertEqual(tree_snapshot(source), before)


class ArtifactBoundaryTests(unittest.TestCase):
    def test_builder_rejects_output_inside_source_tree_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, revision = committed_source(root)
            before = tree_snapshot(source)
            with self.assertRaisesRegex(Exception, "outside.*source"):
                distribution_module().build_artifacts(source, source / "dist", revision=revision, source_date_epoch=0)
            self.assertEqual(tree_snapshot(source), before)

    def test_builder_rejects_unknown_revision_and_non_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, _ = committed_source(root)
            with self.assertRaisesRegex(Exception, "revision"):
                distribution_module().build_artifacts(source, root / "bad-revision", revision="0" * 40, source_date_epoch=0)
            plain = root / "plain"
            plain.mkdir()
            with self.assertRaisesRegex(Exception, "Git repository"):
                distribution_module().build_artifacts(plain, root / "bad-repository", revision="HEAD", source_date_epoch=0)
            self.assertFalse((root / "bad-revision").exists())
            self.assertFalse((root / "bad-repository").exists())

    def test_artifact_inspector_rejects_tampered_or_incomplete_wheel(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, _, built = build_fixture(root)
            wheel = Path(built["wheel"]["path"])
            original = wheel.read_bytes()
            wheel.write_bytes(original + b"tampered")
            with self.assertRaisesRegex(Exception, "digest"):
                distribution_module().inspect_wheel(wheel, expected_sha256=built["wheel"]["sha256"])
            incomplete = root / "incomplete.whl"
            with zipfile.ZipFile(incomplete, "w") as archive:
                archive.writestr("voyage_skill/__init__.py", "__version__='0'\n")
            with self.assertRaisesRegex(Exception, "RECORD"):
                distribution_module().inspect_wheel(incomplete)

    def test_active_runbook_documents_local_build_install_verify_and_publish_stop(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("voyage-build.py", text)
        self.assertIn("--no-index", text)
        self.assertIn("--version", text)
        self.assertIn("outside the source tree", text)
        self.assertIn("User authorization", text)


if __name__ == "__main__":
    unittest.main()
