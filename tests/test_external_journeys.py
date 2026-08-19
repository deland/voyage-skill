from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tests.distribution_support import run_black_box, sanitized_environment
from tests.test_distribution_artifacts import build_fixture, create_venv


REVIEWED = {
    "product": """# Product contract

- Status: draft
- Version: 1

## Goals

Deliver the authorized external journey.

## Non-goals

Do not publish or deploy.

## Acceptance boundary

Accept only independently verified work.
""",
    "governance": """# Governance contract

- Status: draft
- Version: 1

## User authority

User retains final high-risk authority.

## Loop authority

Execution, quality, governance, and audit are independent.

## Risk boundary

Unknown risk selects the stricter mode.
""",
    "system": """# System contract

- Status: draft
- Version: 1

## Sources of truth

Registered active sources define truth.

## Mandatory gates

Independent quality is mandatory.

## Runtime boundary

Commands, immutable anchors, and readback define state.
""",
    "operations": """# Operations runbook

- Status: draft
- Version: 1

## Recovery

Validate and recover before resuming.

## Validation

Record pass, fail, skip, and unknown counts.

## Escalation

Escalate missing authority to User.
""",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class InstalledExternalJourneyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.distribution = tempfile.TemporaryDirectory(prefix="voyage-rw102-dist-")
        root = Path(cls.distribution.name)
        cls.source, _, _, built = build_fixture(root)
        cls.venv = create_venv(root)
        subprocess.run(
            [str(cls.venv / "bin" / "python"), "-m", "pip", "install", "--no-index", "--no-deps", built["wheel"]["path"]],
            check=True,
            text=True,
            capture_output=True,
        )
        cls.cli = cls.venv / "bin" / "voyage"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.distribution.cleanup()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="voyage-rw102-project-")
        self.workspace = Path(self.temporary.name)
        self.project = self.workspace / "project"
        self.project.mkdir()
        self.call_index = 0
        self.env = sanitized_environment()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_cli(self, *args: str, root: Path | None = None, expected: int = 0):
        self.call_index += 1
        cwd = self.workspace / "unrelated" / str(self.call_index)
        cwd.mkdir(parents=True)
        result = run_black_box(
            [str(self.cli), "--root", str(root or self.project), *args],
            cwd=cwd,
            env=self.env,
            timeout=20,
        )
        self.assertEqual(result.exit_code, expected, f"argv={result.argv}\nstdout={result.stdout}\nstderr={result.stderr}")
        return result

    def json_run(self, *args: str, root: Path | None = None, expected: int = 0) -> dict:
        result = self.run_cli(*args, root=root, expected=expected)
        return json.loads(result.stdout)

    def git(self, *args: str, root: Path | None = None) -> str:
        result = subprocess.run(
            ["git", *args], cwd=root or self.project, check=True, text=True, capture_output=True,
            env={**os.environ, "GIT_AUTHOR_NAME": "Voyage Journey", "GIT_AUTHOR_EMAIL": "journey@example.invalid", "GIT_COMMITTER_NAME": "Voyage Journey", "GIT_COMMITTER_EMAIL": "journey@example.invalid"},
        )
        return result.stdout.strip()

    def initialize_git(self) -> str:
        self.git("init", "-q")
        (self.project / "README.md").write_text("# Existing project\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-qm", "initial")
        return self.git("rev-parse", "HEAD")

    def registry(self, root: Path | None = None) -> tuple[Path, dict]:
        project = root or self.project
        manifest = json.loads((project / ".voyage" / "manifest.json").read_text(encoding="utf-8"))
        path = project / manifest["truth_registry"]
        return path, json.loads(path.read_text(encoding="utf-8"))

    def init_fresh(self, project_id: str = "fresh-project") -> list[str]:
        self.json_run("init", "--project-id", project_id)
        _, registry = self.registry()
        return [item["id"] for item in registry["sources"] if item["domain"] in REVIEWED]

    def review_drafts(self) -> None:
        _, registry = self.registry()
        for source in registry["sources"]:
            if source["domain"] in REVIEWED:
                (self.project / source["path"]).write_text(REVIEWED[source["domain"]], encoding="utf-8")

    def record_decision(self, decision_id: str, project_id: str, sources: list[str], *, actor: str = "user", loop: str = "user", action: str = "truth.activate") -> dict:
        payload = {"decision": action, "scope": {"actions": [action], "project_id": project_id, "truth_sources": sources}}
        return self.json_run(
            "event", "record", "--type", "decision.recorded", "--subject", decision_id,
            "--payload-json", json.dumps(payload), "--actor", actor, "--loop", loop,
        )

    def activate(self, sources: list[str], decision_id: str = "USER-BOOTSTRAP") -> None:
        for source_id in sources:
            self.json_run("truth", "activate", source_id, "--decision", decision_id, "--actor", "gov")

    def operational(self, project_id: str = "fresh-project") -> list[str]:
        self.initialize_git()
        sources = self.init_fresh(project_id)
        self.review_drafts()
        self.record_decision("USER-BOOTSTRAP", project_id, sources)
        self.activate(sources)
        return sources

    def write_evidence(self, name: str, document: dict, actor: str) -> dict:
        inputs = self.project / ".journey-inputs"
        inputs.mkdir(exist_ok=True)
        path = inputs / f"{name}.json"
        path.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
        return self.json_run("evidence", "record", "--file", str(path), "--actor", actor)

    def git_anchor(self, revision: str, name: str = "anchor") -> dict:
        return self.write_evidence(name, {
            "kind": "git-commit", "version": 1, "claim": "delivery-source",
            "locator": {"repository": ".", "revision": revision},
            "observed_at": datetime.now(timezone.utc).isoformat(), "producer": "dev",
        }, "dev")

    def command_evidence(self, name: str, producer: str = "dev") -> dict:
        artifacts = self.project / ".journey-artifacts"
        artifacts.mkdir(exist_ok=True)
        completed = subprocess.run(["git", "status", "--short"], cwd=self.project, text=True, capture_output=True)
        stdout = artifacts / f"{name}.stdout"
        stderr = artifacts / f"{name}.stderr"
        stdout.write_text(completed.stdout, encoding="utf-8")
        stderr.write_text(completed.stderr, encoding="utf-8")
        descriptor = lambda path: {"path": path.relative_to(self.project).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)}
        return self.write_evidence(name, {
            "kind": "command-result", "version": 1, "claim": "command-passed",
            "locator": {
                "argv": ["git", "status", "--short"], "cwd": ".", "exit_code": completed.returncode,
                "stdout": descriptor(stdout), "stderr": descriptor(stderr),
                "counts": {"total": 1, "passed": 1, "failed": 0, "skipped": 0, "unknown": 0},
            },
            "observed_at": datetime.now(timezone.utc).isoformat(), "producer": producer,
        }, producer)

    def runtime_evidence(self, name: str = "runtime") -> dict:
        return self.write_evidence(name, {
            "kind": "runtime-readback", "version": 1, "claim": "external-runtime-healthy",
            "locator": {"environment_id": "local-test", "target_version": self.git("rev-parse", "HEAD"), "fields": {"healthy": True}, "max_age_seconds": 300},
            "observed_at": datetime.now(timezone.utc).isoformat(), "producer": "probe",
        }, "probe")

    def prepare_work(self, work_id: str = "W-1", *, resource: str | None = None) -> None:
        args = ["work", "create", work_id, "--title", "External journey", "--scope", "temporary project", "--acceptance", "verified", "--risk", "standard", "--actor", "gov"]
        if resource:
            args.extend(["--resource", resource])
        self.json_run(*args)
        self.json_run("work", "authorize", work_id, "--actor", "gov")

    def complete_work(self, work_id: str = "W-1", *, resource: bool = True) -> dict:
        revision = self.git("rev-parse", "HEAD")
        resource_id = "file:shared"
        if resource:
            self.json_run("resource", "register", resource_id, "--type", "file", "--mode", "exclusive", "--conflict-key", "shared.txt", "--actor", "gov")
        self.prepare_work(work_id, resource=resource_id if resource else None)
        probe = self.command_evidence("probe", "probe")
        if resource:
            self.json_run("resource", "claim", resource_id, "--work", work_id, "--lease-id", "LEASE-1", "--evidence", probe["evidence_id"], "--actor", "dev")
        self.json_run("work", "start", work_id, "--actor", "dev")
        anchor = self.git_anchor(revision)
        execution = self.command_evidence("execution", "dev")
        quality = self.command_evidence("quality", "qa")
        self.json_run("work", "deliver", work_id, "--anchor", anchor["evidence_id"], "--evidence", execution["evidence_id"], "--actor", "dev")
        self.json_run("work", "quality", work_id, "--verdict", "pass", "--anchor", anchor["evidence_id"], "--total", "1", "--passed", "1", "--evidence", quality["evidence_id"], "--actor", "qa")
        self.json_run("gate", "record", "independent-quality", "--work", work_id, "--anchor", anchor["evidence_id"], "--total", "1", "--passed", "1", "--failed", "0", "--skipped", "0", "--unknown", "0", "--evidence", quality["evidence_id"], "--actor", "qa")
        self.json_run("work", "accept", work_id, "--actor", "gov")
        if resource:
            self.json_run("resource", "release", "LEASE-1", "--evidence", probe["evidence_id"], "--actor", "dev", "--loop", "execution")
        self.json_run("work", "close", work_id, "--actor", "gov")
        return {"revision": revision, "anchor": anchor, "execution": execution, "quality": quality, "probe": probe}

    def adopted_operational(self) -> tuple[list[str], bytes]:
        self.initialize_git()
        protected = self.project / "user-data.txt"
        protected.write_bytes(b"user-owned\x00bytes\n")
        sources = []
        for domain in REVIEWED:
            path = self.project / "project-truth" / f"{domain}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# Adopted {domain}\n\nReviewed external truth.\n", encoding="utf-8")
            sources.append({"id": f"custom-{domain}", "domain": domain, "path": path.relative_to(self.project).as_posix(), "version": "1", "status": "active"})
        registry = self.project / "configuration" / "truth.json"
        registry.parent.mkdir(parents=True)
        registry.write_text(json.dumps({"schema_version": "0.1.0", "project": "adopted-project", "sources": sources}, indent=2) + "\n", encoding="utf-8")
        before = protected.read_bytes()
        self.json_run("init", "--project-id", "adopted-project", "--truth-registry", "configuration/truth.json")
        ids = [source["id"] for source in sources]
        self.record_decision("USER-ADOPT", "adopted-project", ids)
        self.activate(ids, "USER-ADOPT")
        self.assertEqual(protected.read_bytes(), before)
        return ids, before

    # ST-1021
    def test_installed_runner_has_no_source_path_or_pythonpath(self) -> None:
        cwd = self.workspace / "location"
        cwd.mkdir()
        result = run_black_box([str(self.venv / "bin" / "python"), "-c", "import os,voyage_skill; print(os.getcwd()); print(voyage_skill.__file__); print(os.environ.get('PYTHONPATH',''))"], cwd=cwd, env=self.env, timeout=10)
        self.assertEqual(result.exit_code, 0, result.stderr)
        self.assertNotIn(str(self.source), result.stdout)
        self.assertIn("site-packages", result.stdout)

    def test_fresh_init_creates_drafts_and_bootstrap_readback(self) -> None:
        ids = self.init_fresh()
        status = self.json_run("truth", "status")
        self.assertEqual(status["project_stage"], "bootstrap")
        self.assertEqual(set(status["missing_domains"]), set(REVIEWED))
        self.assertEqual(len(ids), 4)

    def test_reviewed_drafts_require_user_decision_before_activation(self) -> None:
        sources = self.init_fresh()
        self.review_drafts()
        before = (self.project / ".voyage" / "ledger" / "events.jsonl").read_bytes()
        result = self.run_cli("truth", "activate", sources[0], "--decision", "MISSING", "--actor", "gov", expected=2)
        self.assertIn("User decision", result.stderr)
        self.assertEqual((self.project / ".voyage" / "ledger" / "events.jsonl").read_bytes(), before)

    def test_four_required_truth_domains_activate_from_exact_user_scope(self) -> None:
        sources = self.init_fresh()
        self.review_drafts()
        self.record_decision("USER-BOOTSTRAP", "fresh-project", sources)
        self.activate(sources)
        status = self.json_run("truth", "status")
        self.assertEqual(status["project_stage"], "operational")
        self.assertEqual(status["missing_domains"], [])

    def test_cold_validate_truth_status_and_recover_agree_after_activation(self) -> None:
        self.operational()
        validate = self.json_run("validate")
        truth = self.json_run("truth", "status")
        recover = self.json_run("recover")
        self.assertTrue(validate["valid"])
        self.assertEqual(truth["project_id"], recover["project_id"])
        self.assertEqual(truth["project_stage"], recover["project_stage"])
        self.assertEqual(truth["ledger_head"], recover["ledger_head"])

    # ST-1022
    def test_git_commit_anchor_and_command_evidence_are_verified_from_project(self) -> None:
        self.operational()
        revision = self.git("rev-parse", "HEAD")
        anchor = self.git_anchor(revision)
        command = self.command_evidence("execution")
        self.assertEqual(anchor["status"], "valid")
        self.assertEqual(command["status"], "valid")
        shown = self.json_run("evidence", "show", anchor["evidence_id"])
        self.assertEqual(shown["document"]["locator"]["revision"], revision)

    def test_runtime_readback_and_resource_probe_are_real_typed_evidence(self) -> None:
        self.operational()
        runtime = self.runtime_evidence()
        probe = self.command_evidence("probe", "probe")
        self.assertEqual((runtime["kind"], runtime["status"]), ("runtime-readback", "valid"))
        self.assertEqual((probe["kind"], probe["status"]), ("command-result", "valid"))

    def test_exclusive_resource_claim_and_release_round_trip(self) -> None:
        self.operational()
        self.complete_work()
        resources = self.json_run("resource", "list")
        self.assertEqual(resources["active_leases"], [])
        self.assertEqual(resources["definitions"][0]["id"], "file:shared")

    def test_independent_quality_and_gate_reference_exact_delivery_commit(self) -> None:
        self.operational()
        result = self.complete_work(resource=False)
        state = self.json_run("status", "--full")
        work = state["works"]["W-1"]
        self.assertEqual(work["delivery"]["anchor"], result["anchor"]["evidence_id"])
        self.assertEqual(work["quality"]["actor"], "qa")
        self.assertEqual(state["gates"]["W-1"]["independent-quality"]["counts"], {"total": 1, "passed": 1, "failed": 0, "skipped": 0, "unknown": 0})

    def test_installed_cli_completes_and_cold_recovers_closed_work(self) -> None:
        self.operational()
        self.complete_work()
        recovered = self.json_run("recover")
        item = next(item for item in recovered["work"] if item["id"] == "W-1")
        self.assertEqual(item["status"], "closed")
        self.assertEqual(item["next_safe_action"], "none")

    # ST-1023
    def test_adopt_existing_git_project_with_custom_registry(self) -> None:
        ids, _ = self.adopted_operational()
        manifest = json.loads((self.project / ".voyage" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["project_id"], "adopted-project")
        self.assertEqual(manifest["truth_registry"], "configuration/truth.json")
        self.assertEqual(len(ids), 4)

    def test_adoption_preserves_preexisting_user_files_byte_for_byte(self) -> None:
        _, before = self.adopted_operational()
        self.assertEqual((self.project / "user-data.txt").read_bytes(), before)
        self.assertEqual((self.project / "README.md").read_text(encoding="utf-8"), "# Existing project\n")

    def test_custom_truth_paths_activate_and_validate_without_defaults(self) -> None:
        self.adopted_operational()
        self.assertTrue(self.json_run("validate")["valid"])
        self.assertFalse((self.project / "docs" / "voyage").exists())
        status = self.json_run("truth", "status")
        self.assertEqual({item["path"] for item in status["sources"]}, {f"project-truth/{domain}.md" for domain in REVIEWED})

    def test_adopted_project_cold_recovery_uses_persisted_identity_and_registry(self) -> None:
        self.adopted_operational()
        recovered = self.json_run("recover")
        self.assertEqual(recovered["project_id"], "adopted-project")
        self.assertEqual(recovered["truth_registry"], "configuration/truth.json")
        self.assertEqual(recovered["project_stage"], "operational")

    # ST-1024
    def test_bootstrap_rejects_work_authorization_without_ledger_mutation(self) -> None:
        self.init_fresh()
        self.json_run("work", "create", "W-BOOT", "--title", "Blocked", "--scope", "bootstrap", "--acceptance", "never", "--actor", "gov")
        ledger = self.project / ".voyage" / "ledger" / "events.jsonl"
        before = ledger.read_bytes()
        result = self.run_cli("work", "authorize", "W-BOOT", "--actor", "gov", expected=2)
        self.assertIn("operational", result.stderr)
        self.assertEqual(ledger.read_bytes(), before)

    def test_wrong_user_decision_scope_rejects_activation_atomically(self) -> None:
        sources = self.init_fresh()
        self.review_drafts()
        self.record_decision("USER-WRONG", "another-project", sources)
        ledger = self.project / ".voyage" / "ledger" / "events.jsonl"
        registry, _ = self.registry()
        before = (ledger.read_bytes(), registry.read_bytes())
        result = self.run_cli("truth", "activate", sources[0], "--decision", "USER-WRONG", "--actor", "gov", expected=2)
        self.assertIn("project", result.stderr)
        self.assertEqual((ledger.read_bytes(), registry.read_bytes()), before)

    def test_nonexistent_or_mismatched_commit_anchor_rejects_delivery_atomically(self) -> None:
        self.operational()
        self.prepare_work()
        self.json_run("work", "start", "W-1", "--actor", "dev")
        invalid = self.git_anchor("f" * 40, "missing-anchor")
        execution = self.command_evidence("execution")
        ledger = self.project / ".voyage" / "ledger" / "events.jsonl"
        before = ledger.read_bytes()
        result = self.run_cli("work", "deliver", "W-1", "--anchor", invalid["evidence_id"], "--evidence", execution["evidence_id"], "--actor", "dev", expected=2)
        self.assertIn("anchor is invalid", result.stderr)
        self.assertEqual(ledger.read_bytes(), before)

    def test_executor_self_review_rejects_quality_atomically(self) -> None:
        self.operational()
        self.prepare_work()
        self.json_run("work", "start", "W-1", "--actor", "dev")
        revision = self.git("rev-parse", "HEAD")
        anchor = self.git_anchor(revision)
        execution = self.command_evidence("execution")
        self.json_run("work", "deliver", "W-1", "--anchor", anchor["evidence_id"], "--evidence", execution["evidence_id"], "--actor", "dev")
        ledger = self.project / ".voyage" / "ledger" / "events.jsonl"
        before = ledger.read_bytes()
        result = self.run_cli("work", "quality", "W-1", "--verdict", "pass", "--anchor", anchor["evidence_id"], "--total", "1", "--passed", "1", "--evidence", execution["evidence_id"], "--actor", "dev", expected=2)
        self.assertIn("executor cannot issue", result.stderr)
        self.assertEqual(ledger.read_bytes(), before)

    def test_exclusive_resource_conflict_rejects_second_claim_atomically(self) -> None:
        self.operational()
        self.json_run("resource", "register", "file:shared", "--type", "file", "--mode", "exclusive", "--conflict-key", "shared.txt", "--actor", "gov")
        self.prepare_work("W-1", resource="file:shared")
        self.prepare_work("W-2", resource="file:shared")
        probe = self.command_evidence("probe", "probe")
        self.json_run("resource", "claim", "file:shared", "--work", "W-1", "--lease-id", "LEASE-1", "--evidence", probe["evidence_id"], "--actor", "dev-a")
        ledger = self.project / ".voyage" / "ledger" / "events.jsonl"
        before = ledger.read_bytes()
        result = self.run_cli("resource", "claim", "file:shared", "--work", "W-2", "--lease-id", "LEASE-2", "--evidence", probe["evidence_id"], "--actor", "dev-b", expected=2)
        self.assertIn("conflict", result.stderr)
        self.assertEqual(ledger.read_bytes(), before)
        leases = self.json_run("resource", "list")["active_leases"]
        self.assertEqual([lease["lease_id"] for lease in leases], ["LEASE-1"])


if __name__ == "__main__":
    unittest.main()
