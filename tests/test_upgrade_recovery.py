from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import voyage_skill.core as core
from tests.distribution_support import run_black_box, sanitized_environment, tree_snapshot
from tests.support import operational_project, typed_command_evidence
from tests.test_distribution_artifacts import build_fixture, create_venv


REPOSITORY = Path(__file__).resolve().parents[1]
HISTORY = REPOSITORY / "tests" / "fixtures" / "history"
CATALOG = HISTORY / "catalog.json"
RUNBOOK = REPOSITORY / "docs" / "operations" / "runbook.md"
SYSTEM = REPOSITORY / "docs" / "system" / "graph.md"


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class UpgradeRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.distribution = tempfile.TemporaryDirectory(prefix="voyage-rw103-dist-")
        dist = Path(cls.distribution.name)
        cls.source, _, _, cls.built = build_fixture(dist)
        cls.venv = create_venv(dist)
        subprocess.run(
            [str(cls.venv / "bin" / "python"), "-m", "pip", "install", "--no-index", "--no-deps", cls.built["wheel"]["path"]],
            check=True, text=True, capture_output=True,
        )
        cls.cli = cls.venv / "bin" / "voyage"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.distribution.cleanup()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="voyage-rw103-")
        self.root = Path(self.temporary.name)
        self.calls = 0
        self.env = sanitized_environment()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_cli(self, project: Path, *args: str, expected: int = 0):
        self.calls += 1
        cwd = self.root / "unrelated" / str(self.calls)
        cwd.mkdir(parents=True, exist_ok=True)
        result = run_black_box([str(self.cli), "--root", str(project), *args], cwd=cwd, env=self.env, timeout=20)
        self.assertEqual(result.exit_code, expected, f"argv={result.argv}\nstdout={result.stdout}\nstderr={result.stderr}")
        return result

    def json_cli(self, project: Path, *args: str, expected: int = 0) -> dict:
        return json.loads(self.run_cli(project, *args, expected=expected).stdout)

    def fixture(self, fixture_id: str) -> Path:
        source = HISTORY / fixture_id / "project"
        target = self.root / fixture_id
        shutil.copytree(source, target)
        return target

    def catalog(self) -> dict:
        return json.loads(CATALOG.read_text(encoding="utf-8"))

    def append_user_decision(self, project: Path, decision_id: str, action: str, project_id: str) -> None:
        payload = {"decision": action, "scope": {"actions": [action], "project_id": project_id, "truth_sources": ["*"]}}
        self.json_cli(
            project, "event", "record", "--type", "decision.recorded", "--subject", decision_id,
            "--payload-json", json.dumps(payload), "--actor", "user", "--loop", "user",
        )

    # ST-1031
    def test_fixture_catalog_is_versioned_and_lists_exact_supported_contracts(self) -> None:
        catalog = self.catalog()
        self.assertEqual(catalog["schema_version"], 1)
        self.assertEqual([item["id"] for item in catalog["fixtures"]], ["v0.1-explicit", "v0.1-legacy"])
        for item in catalog["fixtures"]:
            self.assertEqual(set(item), {"id", "source_version", "project_stage", "compatibility", "files"})
            self.assertIn(item["compatibility"], {"read-compatible", "user-migratable"})
            self.assertTrue(item["files"])

    def test_fixture_catalog_sha256_matches_every_historical_byte(self) -> None:
        for item in self.catalog()["fixtures"]:
            fixture_root = HISTORY / item["id"] / "project"
            listed = [entry["path"] for entry in item["files"]]
            actual = sorted(path.relative_to(fixture_root).as_posix() for path in fixture_root.rglob("*") if path.is_file())
            self.assertEqual(listed, sorted(listed))
            self.assertEqual(listed, actual)
            for entry in item["files"]:
                self.assertRegex(entry["sha256"], r"^[a-f0-9]{64}$")
                self.assertEqual(digest(fixture_root / entry["path"]), entry["sha256"])

    def test_installed_reader_validates_and_recovers_supported_legacy_fixture(self) -> None:
        project = self.fixture("v0.1-legacy")
        before = tree_snapshot(project)
        self.assertTrue(self.json_cli(project, "validate")["valid"])
        recovered = self.json_cli(project, "recover")
        self.assertEqual(recovered["project_stage"], "legacy-bootstrap")
        self.assertTrue(recovered["bootstrap"]["legacy"])
        self.assertEqual(recovered["bootstrap"]["unverified_active_sources"], ["governance", "operations", "product", "system"])
        self.assertEqual(recovered["bootstrap"]["sources"][0]["activation_verified"], False)
        self.assertEqual(tree_snapshot(project), before)

    def test_legacy_fixture_migration_requires_exact_user_decision_and_appends_only(self) -> None:
        project = self.fixture("v0.1-legacy")
        ledger = project / ".voyage" / "ledger" / "events.jsonl"
        original = ledger.read_bytes()
        before = tree_snapshot(project)
        self.run_cli(project, "truth", "migrate", "--decision", "MISSING", "--actor", "gov", expected=2)
        self.assertEqual(tree_snapshot(project), before)
        self.append_user_decision(project, "USER-MIGRATE", "truth.migrate", "legacy-fixture")
        decision_prefix = ledger.read_bytes()
        self.json_cli(project, "truth", "migrate", "--decision", "USER-MIGRATE", "--actor", "gov")
        self.assertTrue(ledger.read_bytes().startswith(decision_prefix))
        self.assertTrue(decision_prefix.startswith(original))
        self.assertEqual(self.json_cli(project, "recover")["project_stage"], "operational")

    def test_installed_reader_accepts_explicit_current_fixture_without_migration(self) -> None:
        project = self.fixture("v0.1-explicit")
        before = tree_snapshot(project)
        self.assertTrue(self.json_cli(project, "validate")["valid"])
        self.assertEqual(self.json_cli(project, "recover")["project_stage"], "operational")
        self.run_cli(project, "truth", "migrate", "--decision", "MISSING", "--actor", "gov", expected=2)
        self.assertEqual(tree_snapshot(project), before)

    # ST-1032
    def test_future_manifest_schema_fails_closed_without_mutation(self) -> None:
        project = self.fixture("v0.1-explicit")
        manifest = project / ".voyage" / "manifest.json"
        body = json.loads(manifest.read_text(encoding="utf-8"))
        body["schema_version"] = "99.0.0"
        manifest.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
        before = tree_snapshot(project)
        result = self.json_cli(project, "validate", expected=1)
        self.assertFalse(result["valid"])
        self.assertTrue(any("unsupported manifest schema" in item for item in result["errors"]))
        self.run_cli(project, "recover", expected=2)
        self.assertEqual(tree_snapshot(project), before)

    def test_future_event_or_evidence_version_fails_closed_without_promotion(self) -> None:
        project = self.fixture("v0.1-explicit")
        evidence = project / "future-evidence.json"
        evidence.write_text(json.dumps({
            "kind": "runtime-readback", "version": 99, "claim": "future",
            "locator": {"environment_id": "test", "target_version": "future", "fields": {"ok": True}, "max_age_seconds": 300},
            "observed_at": datetime.now(timezone.utc).isoformat(), "producer": "future",
        }), encoding="utf-8")
        before = tree_snapshot(project)
        result = self.run_cli(project, "evidence", "record", "--file", str(evidence), "--actor", "probe", expected=2)
        self.assertIn("version", result.stderr)
        self.assertEqual(tree_snapshot(project), before)

    def test_started_init_marker_resumes_idempotently_with_one_initial_event(self) -> None:
        project = self.root / "interrupted"
        marker = project / ".voyage" / "init-state.json"
        marker.parent.mkdir(parents=True)
        marker.write_text(json.dumps({
            "schema_version": 1, "status": "in-progress", "project_id": "interrupted",
            "truth_registry": "docs/voyage/truth-registry.json", "registry_mode": "generated",
            "phase": "started", "next_safe_action": "rerun",
        }, indent=2) + "\n", encoding="utf-8")
        self.json_cli(project, "init", "--project-id", "interrupted")
        ledger = project / ".voyage" / "ledger" / "events.jsonl"
        events = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([event["type"] for event in events], ["project.initialized"])
        before = tree_snapshot(project)
        self.run_cli(project, "init", "--project-id", "interrupted", expected=2)
        self.assertEqual(tree_snapshot(project), before)

    def test_mismatched_init_resume_arguments_leave_partial_tree_unchanged(self) -> None:
        project = self.root / "mismatch"
        marker = project / ".voyage" / "init-state.json"
        marker.parent.mkdir(parents=True)
        marker.write_text(json.dumps({
            "schema_version": 1, "status": "in-progress", "project_id": "expected",
            "truth_registry": "docs/voyage/truth-registry.json", "registry_mode": "generated",
            "phase": "started", "next_safe_action": "rerun",
        }, indent=2) + "\n", encoding="utf-8")
        before = tree_snapshot(project)
        self.run_cli(project, "init", "--project-id", "different", expected=2)
        self.assertEqual(tree_snapshot(project), before)

    def test_separate_processes_recover_identical_head_stage_and_next_actions(self) -> None:
        project = self.fixture("v0.1-explicit")
        results = [self.json_cli(project, "recover") for _ in range(3)]
        projection = lambda item: (item["project_id"], item["project_stage"], item["ledger_head"], [(work["id"], work["next_safe_action"]) for work in item["work"]])
        self.assertEqual([projection(item) for item in results], [projection(results[0])] * 3)

    # ST-1033
    def test_truncated_ledger_tail_is_deterministic_json_error_without_traceback(self) -> None:
        project = self.fixture("v0.1-explicit")
        ledger = project / ".voyage" / "ledger" / "events.jsonl"
        ledger.write_bytes(ledger.read_bytes() + b'{"event_id":')
        before = tree_snapshot(project)
        first = self.json_cli(project, "validate", expected=1)
        second = self.json_cli(project, "validate", expected=1)
        self.assertEqual(first["errors"], second["errors"])
        failed = self.run_cli(project, "recover", expected=2)
        self.assertNotIn("Traceback", failed.stderr)
        self.assertEqual(tree_snapshot(project), before)

    def test_hash_valid_but_invalid_event_payload_fails_without_state_mutation(self) -> None:
        project = self.fixture("v0.1-explicit")
        ledger = project / ".voyage" / "ledger" / "events.jsonl"
        events = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        events[0]["payload"]["project_stage"] = "future-stage"
        previous = None
        for event in events:
            event["prev_hash"] = previous
            body = {key: value for key, value in event.items() if key != "hash"}
            event["hash"] = hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()
            previous = event["hash"]
        ledger.write_text("".join(canonical(item) + "\n" for item in events), encoding="utf-8")
        before = tree_snapshot(project)
        result = self.json_cli(project, "validate", expected=1)
        self.assertTrue(any("project_stage" in item or "initial project stage" in item for item in result["errors"]))
        self.assertEqual(tree_snapshot(project), before)

    def test_tampered_or_missing_consumed_evidence_blocks_recovery_without_mutation(self) -> None:
        for case in ("tampered", "missing"):
            with self.subTest(case=case):
                project = self.root / case
                paths = operational_project(project, f"evidence-{case}")
                subprocess.run(["git", "init", "-q", str(project)], check=True)
                subprocess.run(["git", "-C", str(project), "add", "."], check=True)
                subprocess.run(["git", "-C", str(project), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"], check=True)
                revision = subprocess.run(["git", "-C", str(project), "rev-parse", "HEAD"], check=True, text=True, capture_output=True).stdout.strip()
                anchor = core.record_evidence(paths, {"kind": "git-commit", "version": 1, "claim": "delivery-source", "locator": {"repository": ".", "revision": revision}, "observed_at": datetime.now(timezone.utc).isoformat(), "producer": "dev"}, actor="dev")["evidence_id"]
                execution = typed_command_evidence(paths, name=f"execution-{case}", producer="dev")
                core.append_event(paths, actor="gov", loop="governance", event_type="work.created", subject="W-1", risk="standard", payload={"title": "Damaged evidence", "scope": "test", "acceptance": ["verified"]})
                core.append_event(paths, actor="gov", loop="governance", event_type="work.authorized", subject="W-1", risk="standard")
                core.append_event(paths, actor="dev", loop="execution", event_type="work.started", subject="W-1", risk="standard")
                core.append_event(paths, actor="dev", loop="execution", event_type="work.delivered", subject="W-1", risk="standard", anchor=anchor, evidence=[execution])
                evidence_path = paths.evidence / "sha256" / f"{execution.split(':', 1)[1]}.json"
                if case == "tampered":
                    document = json.loads(evidence_path.read_text(encoding="utf-8"))
                    document["claim"] = "changed"
                    evidence_path.write_text(json.dumps(document), encoding="utf-8")
                else:
                    evidence_path.unlink()
                before = tree_snapshot(project)
                self.run_cli(project, "recover", expected=2)
                self.assertEqual(tree_snapshot(project), before)

    def test_expired_stateful_lease_is_unknown_with_minimum_recovery_scope(self) -> None:
        project = self.root / "expired"
        paths = operational_project(project, "expired-fixture")
        core.register_resource(paths, actor="gov", resource_id="session:one", resource_type="session", mode="exclusive", conflict_key="session-one")
        core.append_event(paths, actor="gov", loop="governance", event_type="work.created", subject="W-1", risk="standard", payload={"title": "Expired", "scope": "test", "acceptance": ["safe"], "required_resources": ["session:one"]})
        core.append_event(paths, actor="gov", loop="governance", event_type="work.authorized", subject="W-1", risk="standard")
        probe = typed_command_evidence(paths, name="expired-probe", producer="probe")
        core.append_event(paths, actor="dev", loop="execution", event_type="resource.claimed", subject="session:one", risk="standard", evidence=[probe], payload={"resource_id": "session:one", "lease_id": "LEASE-OLD", "work_id": "W-1", "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()})
        before = tree_snapshot(project)
        recovered = self.json_cli(project, "recover")
        facts = [item for item in recovered["unknown"] if item["subject"] == "session:one"]
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["blocking_scope"], "resource:session:one/lease:LEASE-OLD")
        self.assertEqual(recovered["active_leases"][0]["lease_id"], "LEASE-OLD")
        self.assertEqual(tree_snapshot(project), before)

    def test_unsupported_lock_backend_blocks_write_before_ledger_mutation(self) -> None:
        project = self.root / "lock"
        paths = operational_project(project, "lock-fixture")
        before = paths.ledger.read_bytes()
        self.assertEqual(core.validate_project(paths), [])
        with mock.patch.object(core, "_fcntl", None):
            capability = core.runtime_capabilities()["write_lock"]
            self.assertFalse(capability["append_safe"])
            with self.assertRaisesRegex(core.VoyageError, "unsupported"):
                core.append_event(paths, actor="gov", loop="governance", event_type="work.created", subject="W-LOCK", risk="standard", payload={"title": "No lock", "scope": "test", "acceptance": ["safe"]})
        self.assertEqual(paths.ledger.read_bytes(), before)

    # ST-1034
    def test_compatibility_policy_names_supported_migrate_and_reject_classes(self) -> None:
        text = SYSTEM.read_text(encoding="utf-8")
        for phrase in ("read-compatible", "user-migratable", "damaged", "unknown-future", "no automatic repair"):
            self.assertIn(phrase, text)

    def test_runbook_documents_fixture_readback_migration_and_no_rewrite_rules(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        for phrase in ("historical fixture", "truth migrate", "validate", "recover", "append-only prefix", "unknown-future"):
            self.assertIn(phrase, text)

    def test_aggregate_negative_matrix_leaves_authoritative_tree_byte_identical(self) -> None:
        mutations = ("future-schema", "truncated-ledger", "invalid-graph")
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                project = self.fixture("v0.1-explicit")
                project = Path(shutil.move(str(project), str(self.root / f"matrix-{mutation}")))
                if mutation == "future-schema":
                    target = project / ".voyage" / "manifest.json"
                    body = json.loads(target.read_text(encoding="utf-8")); body["schema_version"] = "99.0.0"
                    target.write_text(json.dumps(body), encoding="utf-8")
                elif mutation == "truncated-ledger":
                    target = project / ".voyage" / "ledger" / "events.jsonl"
                    target.write_bytes(target.read_bytes() + b"{")
                else:
                    target = project / ".voyage" / "graph.json"
                    body = json.loads(target.read_text(encoding="utf-8")); body["node_types"].append(body["node_types"][0])
                    target.write_text(json.dumps(body), encoding="utf-8")
                before = tree_snapshot(project)
                self.run_cli(project, "validate", expected=1)
                self.run_cli(project, "recover", expected=2)
                self.assertEqual(tree_snapshot(project), before)

    def test_historical_fixtures_are_test_only_not_truth_or_distribution_payload(self) -> None:
        registry = json.loads((REPOSITORY / "docs" / "truth-registry.json").read_text(encoding="utf-8"))
        self.assertFalse(any("fixtures/history" in source.get("path", "") for source in registry["sources"]))
        with zipfile.ZipFile(self.built["wheel"]["path"]) as wheel:
            self.assertFalse(any("fixtures/history" in name for name in wheel.namelist()))
        with tarfile.open(self.built["source"]["path"], "r:gz") as archive:
            manifest_name = next(name for name in archive.getnames() if name.endswith("VOYAGE-SOURCE.json"))
            manifest = json.loads(archive.extractfile(manifest_name).read())
        self.assertIn("tests/fixtures/history/", manifest["test_material"])


if __name__ == "__main__":
    unittest.main()
