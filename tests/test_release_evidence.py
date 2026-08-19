from __future__ import annotations

import hashlib
import importlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from tests.distribution_support import run_black_box, sanitized_environment, tree_snapshot
from tests.test_distribution_artifacts import build_fixture, create_venv


REPOSITORY = Path(__file__).resolve().parents[1]
RUNBOOK = REPOSITORY / "docs" / "operations" / "runbook.md"
SKILL = REPOSITORY / "SKILL.md"
RELEASE_SCRIPT = REPOSITORY / "scripts" / "voyage-release.py"
REQUIRED_CHECKS = ("dogfood-validation", "external-journeys", "repository-tests", "skill-validation", "upgrade-recovery")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


class ReleaseEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.distribution = tempfile.TemporaryDirectory(prefix="voyage-rw201-dist-")
        cls.source, cls.revision, cls.artifacts, cls.built = build_fixture(Path(cls.distribution.name), epoch=0)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.distribution.cleanup()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="voyage-rw201-")
        self.root = Path(self.temporary.name)
        self.checks_dir = self.root / "checks"
        self.checks_path = self.make_checks()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def release_module(self):
        return importlib.import_module("voyage_skill.release")

    def make_checks(self, mutate=None) -> Path:
        self.checks_dir.mkdir(parents=True, exist_ok=True)
        totals = {
            "repository-tests": 389,
            "skill-validation": 1,
            "dogfood-validation": 3,
            "external-journeys": 19,
            "upgrade-recovery": 19,
        }
        checks = []
        for check_id in REQUIRED_CHECKS:
            output = self.checks_dir / f"{check_id}.txt"
            output.write_text(f"{check_id}: PASS ({totals[check_id]})\n", encoding="utf-8")
            checks.append({
                "id": check_id,
                "command": ["python3", "-m", "unittest", check_id],
                "exit_code": 0,
                "counts": {"total": totals[check_id], "passed": totals[check_id], "failed": 0, "skipped": 0, "unknown": 0},
                "output": {"path": output.name, "bytes": output.stat().st_size, "sha256": sha256(output)},
            })
        payload = {"schema_version": 1, "revision": self.revision, "checks": checks}
        if mutate:
            mutate(payload)
        path = self.checks_dir / "checks.json"
        path.write_bytes(canonical(payload))
        return path

    def create(self, output: Path | None = None):
        return self.release_module().create_release_evidence(
            self.source,
            self.artifacts,
            self.checks_path,
            output or self.root / "release",
            revision=self.revision,
        )

    def verify(self, result: dict, *, artifacts: Path | None = None, checks: Path | None = None):
        return self.release_module().verify_release_evidence(
            result["path"],
            self.source,
            artifacts or self.artifacts,
            checks or self.checks_path,
        )

    def rewrite_manifest(self, path: Path, mutate) -> Path:
        body = json.loads(path.read_text(encoding="utf-8"))
        body.pop("manifest_id", None)
        mutate(body)
        digest = hashlib.sha256(canonical(body)).hexdigest()
        body["manifest_id"] = f"sha256:{digest}"
        rewritten = path.parent / f"voyage-release-{digest}.json"
        rewritten.write_bytes(canonical(body))
        return rewritten

    # ST-2011
    def test_generator_emits_canonical_manifest_outside_source_tree(self) -> None:
        result = self.create()
        path = Path(result["path"])
        self.assertTrue(path.is_file())
        self.assertFalse(path.resolve().is_relative_to(self.source.resolve()))
        self.assertEqual(path.read_bytes(), canonical(json.loads(path.read_text(encoding="utf-8"))))
        self.assertRegex(path.name, r"^voyage-release-[a-f0-9]{64}\.json$")

    def test_manifest_binds_revision_version_wheel_and_source_bytes(self) -> None:
        result = self.create()
        manifest = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["revision"], self.revision)
        self.assertEqual(manifest["version"], "0.1.0")
        for kind in ("wheel", "source"):
            artifact = Path(self.built[kind]["path"])
            self.assertEqual(manifest["artifacts"][kind], {"name": artifact.name, "bytes": artifact.stat().st_size, "sha256": sha256(artifact)})

    def test_manifest_binds_interpreter_platform_and_five_complete_checks(self) -> None:
        manifest = json.loads(Path(self.create()["path"]).read_text(encoding="utf-8"))
        self.assertEqual(set(manifest["interpreter"]), {"implementation", "version", "platform"})
        self.assertEqual([item["id"] for item in manifest["checks"]], list(REQUIRED_CHECKS))
        for check in manifest["checks"]:
            self.assertEqual(check["exit_code"], 0)
            self.assertEqual(check["counts"]["total"], check["counts"]["passed"])
            self.assertEqual(sum(check["counts"][key] for key in ("failed", "skipped", "unknown")), 0)
            self.assertRegex(check["output"]["sha256"], r"^[a-f0-9]{64}$")

    def test_identical_inputs_rebuild_byte_identical_manifest_and_id(self) -> None:
        first = self.create(self.root / "one")
        second = self.create(self.root / "two")
        self.assertEqual(first["manifest_id"], second["manifest_id"])
        self.assertEqual(Path(first["path"]).read_bytes(), Path(second["path"]).read_bytes())

    def test_generation_leaves_source_tree_unchanged(self) -> None:
        before = tree_snapshot(self.source)
        self.create()
        self.assertEqual(tree_snapshot(self.source), before)

    # ST-2012
    def test_verifier_recomputes_manifest_id_artifact_and_raw_output_digests(self) -> None:
        result = self.create()
        verified = self.verify(result)
        self.assertTrue(verified["valid"])
        self.assertEqual(verified["manifest_id"], result["manifest_id"])
        self.assertEqual(verified["revision"], self.revision)
        self.assertEqual(verified["checks"], {check_id: "pass" for check_id in REQUIRED_CHECKS})

    def test_verifier_rejects_missing_or_changed_artifact(self) -> None:
        for case in ("missing", "changed", "renamed"):
            with self.subTest(case=case):
                result = self.create(self.root / f"report-{case}")
                copied = self.root / f"artifacts-{case}"
                copied.mkdir()
                for artifact in self.artifacts.iterdir():
                    if artifact.is_file():
                        (copied / artifact.name).write_bytes(artifact.read_bytes())
                wheel = next(copied.glob("*.whl"))
                if case == "missing":
                    wheel.unlink()
                elif case == "changed":
                    wheel.write_bytes(wheel.read_bytes() + b"changed")
                else:
                    wheel.rename(copied / f"renamed-{wheel.name}")
                with self.assertRaises(Exception):
                    self.verify(result, artifacts=copied)

    def test_verifier_rejects_wrong_revision_or_package_version(self) -> None:
        result = self.create()
        path = Path(result["path"])
        wrong_revision = self.rewrite_manifest(path, lambda body: body.__setitem__("revision", "f" * 40))
        with self.assertRaisesRegex(Exception, "revision|commit"):
            self.release_module().verify_release_evidence(wrong_revision, self.source, self.artifacts, self.checks_path)
        wrong_version = self.rewrite_manifest(path, lambda body: body.__setitem__("version", "9.9.9"))
        with self.assertRaisesRegex(Exception, "version"):
            self.release_module().verify_release_evidence(wrong_version, self.source, self.artifacts, self.checks_path)

    def test_generator_rejects_missing_failed_skipped_unknown_or_inconsistent_check(self) -> None:
        mutations = {
            "missing": lambda body: body["checks"].pop(),
            "failed": lambda body: body["checks"][0]["counts"].update(passed=388, failed=1),
            "skipped": lambda body: body["checks"][0]["counts"].update(passed=388, skipped=1),
            "unknown": lambda body: body["checks"][0]["counts"].update(passed=388, unknown=1),
            "exit": lambda body: body["checks"][0].update(exit_code=1),
            "total": lambda body: body["checks"][0]["counts"].update(total=390),
            "output": lambda body: body["checks"][0]["output"].update(sha256="0" * 64),
        }
        for case, mutate in mutations.items():
            with self.subTest(case=case):
                self.checks_path = self.make_checks(mutate)
                with self.assertRaises(Exception):
                    self.create(self.root / f"reject-{case}")
                self.assertFalse((self.root / f"reject-{case}").exists())

    def test_verifier_rejects_manifest_field_or_content_address_tamper(self) -> None:
        result = self.create()
        path = Path(result["path"])
        body = json.loads(path.read_text(encoding="utf-8"))
        body["checks"][0]["command"].append("--changed")
        path.write_bytes(canonical(body))
        with self.assertRaisesRegex(Exception, "content address|manifest"):
            self.verify(result)

    # ST-2013
    def test_release_script_create_and_verify_round_trip_from_unrelated_cwd(self) -> None:
        cwd = self.root / "unrelated"
        cwd.mkdir()
        output = self.root / "script-report"
        created = run_black_box([
            sys.executable, str(RELEASE_SCRIPT), "create", "--source", str(self.source), "--artifacts", str(self.artifacts),
            "--checks", str(self.checks_path), "--output", str(output), "--revision", self.revision,
        ], cwd=cwd, env=sanitized_environment(), timeout=30)
        self.assertEqual(created.exit_code, 0, created.stderr)
        result = json.loads(created.stdout)
        verified = run_black_box([
            sys.executable, str(RELEASE_SCRIPT), "verify", "--source", str(self.source), "--artifacts", str(self.artifacts),
            "--checks", str(self.checks_path), "--manifest", result["path"],
        ], cwd=cwd, env=sanitized_environment(), timeout=30)
        self.assertEqual(verified.exit_code, 0, verified.stderr)
        self.assertTrue(json.loads(verified.stdout)["valid"])

    def test_deleting_report_and_rebuilding_from_immutable_inputs_restores_same_id(self) -> None:
        first = self.create(self.root / "first")
        Path(first["path"]).unlink()
        second = self.create(self.root / "second")
        self.assertEqual(first["manifest_id"], second["manifest_id"])

    def test_runbook_documents_candidate_build_checks_verify_and_user_stop(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        for phrase in ("voyage-release.py", "repository-tests", "external-journeys", "upgrade-recovery", "skipped", "unknown", "User authorization"):
            self.assertIn(phrase, text)

    def test_skill_remains_stable_entry_and_does_not_embed_release_procedure(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("release", text.lower())
        self.assertIn("operations", text.lower())
        self.assertIn("User", text)
        self.assertNotIn("voyage-release.py create", text)
        self.assertLessEqual(len(text.splitlines()), 120)

    # ST-2014
    def test_real_built_artifacts_install_and_verify_under_release_manifest(self) -> None:
        result = self.create()
        self.assertTrue(self.verify(result)["valid"])
        venv = create_venv(self.root)
        subprocess.run([str(venv / "bin" / "python"), "-m", "pip", "install", "--no-index", "--no-deps", self.built["wheel"]["path"]], check=True, text=True, capture_output=True)
        version = subprocess.run([str(venv / "bin" / "voyage"), "--version"], check=True, text=True, capture_output=True).stdout.strip()
        self.assertEqual(version, "voyage 0.1.0")

    def test_source_archive_commit_manifest_matches_release_revision(self) -> None:
        release = json.loads(Path(self.create()["path"]).read_text(encoding="utf-8"))
        with tarfile.open(self.built["source"]["path"], "r:gz") as archive:
            name = next(item for item in archive.getnames() if item.endswith("VOYAGE-SOURCE.json"))
            source = json.loads(archive.extractfile(name).read())
        self.assertEqual((source["revision"], source["version"]), (release["revision"], release["version"]))
        self.assertEqual(source["test_material"], ["tests/fixtures/history/"])

    def test_generated_release_report_is_not_truth_or_distribution_payload(self) -> None:
        result = self.create()
        name = Path(result["path"]).name
        registry = json.loads((REPOSITORY / "docs" / "truth-registry.json").read_text(encoding="utf-8"))
        self.assertFalse(any("release" in source.get("path", "") for source in registry["sources"]))
        with zipfile.ZipFile(self.built["wheel"]["path"]) as wheel:
            self.assertNotIn(name, wheel.namelist())
        with tarfile.open(self.built["source"]["path"], "r:gz") as archive:
            self.assertFalse(any(item.endswith(name) for item in archive.getnames()))

    def test_release_tool_has_no_publish_tag_sign_or_remote_mutation_surface(self) -> None:
        result = subprocess.run([sys.executable, str(RELEASE_SCRIPT), "--help"], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("{create,verify}", result.stdout)
        for forbidden in (" upload", " publish", " tag", " sign", " notarize", " remote-release"):
            self.assertNotIn(forbidden, result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
